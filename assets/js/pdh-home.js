/* Homepage: hero quick search (doctor/service tabs), "In clinic today" and HMO tiles, and the
   click-to-play "Our Story" video.
   Data: /data/search-index.json (built by tools/build_pages.py from data/*.json and data/search-terms.json).
   Without JavaScript, or if the index fails to load, each search tab is a plain form that submits to
   /doctors/?q= or /services/?q=, the HMO tile links to the approval form and the video opens on Vimeo. */
(function () {
    var reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setupVideo();
    setupSlides();
    setupTilt();
    var root = document.querySelector('[data-pdh-quickfind]');
    if (!root) return;

    var WEEKDAYS = { Mon: 'Monday', Tue: 'Tuesday', Wed: 'Wednesday', Thu: 'Thursday', Fri: 'Friday', Sat: 'Saturday', Sun: 'Sunday' };
    var index = null;

    // Lowercase, strip accents and punctuation ("Can't" -> "cant", "X-ray" -> "x ray").
    function norm(text) {
        return (text || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/['’]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
    }

    function esc(text) {
        return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function hasPhrase(q, phrase) {
        return (' ' + q + ' ').indexOf(' ' + phrase + ' ') !== -1;
    }

    // How well a query matches one vocabulary term (0 = no match).
    function termScore(q, term) {
        if (!term) return 0;
        if (term === q) return 100;
        if (hasPhrase(q, term)) return 90;                           // "my heart hurts" contains "heart"
        if (q.length >= 3 && term.indexOf(q) === 0) return 75;       // typing "card" -> "cardio"
        return 0;
    }

    function labelScore(q, label) {
        if (label === q) return 100;
        if (q.length >= 2 && (label.indexOf(q) === 0 || label.indexOf(' ' + q) !== -1)) return 85;
        return 0;
    }

    function prepare(data) {
        data.specialties.forEach(function (s) {
            s._label = norm(s.label);
            s._terms = s.terms.map(norm);
        });
        data.services.forEach(function (s) {
            s._name = norm(s.name);
            s._terms = s.terms.map(norm);
            s._offered = norm(s.offered.join(' '));
        });
        data.doctors.forEach(function (d) { d._name = norm(d.n); });
        data.emergency._phrases = data.emergency.phrases.map(norm);
        data.crisis._phrases = data.crisis.phrases.map(norm);
        return data;
    }

    function rank(items, scoreFn, limit) {
        return items.map(function (item) { return { item: item, score: scoreFn(item) }; })
            .filter(function (r) { return r.score > 0; })
            .sort(function (a, b) { return b.score - a.score; })
            .slice(0, limit);
    }

    function search(q) {
        var tokens = q.split(' ');
        var specialties = rank(index.specialties, function (s) {
            return Math.max(labelScore(q, s._label), Math.max.apply(null, s._terms.map(function (t) { return termScore(q, t); })));
        }, 3);
        var services = rank(index.services, function (s) {
            var best = Math.max(labelScore(q, s._name), Math.max.apply(null, [0].concat(s._terms.map(function (t) { return termScore(q, t); }))));
            if (!best && q.length >= 4 && s._offered.indexOf(q) !== -1) best = 60;  // a specific test, e.g. "urinalysis"
            return best;
        }, 4);
        var doctors = q.length < 2 ? [] : rank(index.doctors, function (d) {
            var words = d._name.split(' ');
            return tokens.every(function (t) { return words.some(function (w) { return w.indexOf(t) === 0; }); }) ? 70 : 0;
        }, 50);
        return { specialties: specialties, services: services, doctors: doctors };
    }

    function serviceSummary(s) {
        var parts = [];
        if (s.loc) parts.push(s.loc);
        if (s.hours) {
            var first = s.hours.split('\n')[0];
            // Multi-part schedules start with a sub-heading ("Echo:"), so don't show that as the hours.
            parts.push(/:\s*$/.test(first) ? 'Hours vary by test' : first);
        }
        return parts.join(' · ');
    }

    function group(label, rows) {
        return rows.length ? '<div class="pdh-qf__group"><p class="pdh-qf__label">' + label + '</p><ul>' + rows.join('') + '</ul></div>' : '';
    }

    function specialtyRow(r) {
        var s = r.item;
        return '<li><a href="' + esc(s.url) + '"><strong>' + esc(s.label) + '</strong><span>' + s.count +
            (s.count === 1 ? ' doctor' : ' doctors') + '</span></a></li>';
    }

    function serviceRow(r) {
        var s = r.item;
        return '<li><a href="/services/#' + esc(s.id) + '"><strong>' + esc(s.name) + '</strong><span>' +
            esc(serviceSummary(s)) + '</span></a></li>';
    }

    function doctorRow(r) {
        var d = r.item;
        var spec = d.s || d.d || 'Specialty not listed';
        return '<li><a href="/doctors/' + esc(d.id) + '/"><strong>' + esc(d.n) + '</strong><span>' + esc(spec) + '</span></a></li>';
    }

    function alertHtml(q) {
        if (index.crisis._phrases.some(function (p) { return hasPhrase(q, p); })) {
            var lines = index.crisis.hotlines.map(function (h) {
                return '<a class="pdh-qf__alert-call" href="tel:' + esc(h.tel) + '">' + esc(h.name) + ': ' + esc(h.number) + '</a>';
            }).join('');
            return { kind: 'crisis', html: '<p><strong>' + esc(index.crisis.message) + '</strong></p>' + lines +
                '<p class="pdh-qf__alert-small">If you are in immediate danger, call our Emergency Room at <a href="' +
                esc(index.emergency.hotline.tel) + '">' + esc(index.emergency.hotline.mobile) + '</a> or dial 911.</p>' };
        }
        if (index.emergency._phrases.some(function (p) { return hasPhrase(q, p); })) {
            return { kind: 'emergency', html: '<p><strong>' + esc(index.emergency.message) + '</strong></p>' +
                '<a class="pdh-qf__alert-call" href="' + esc(index.emergency.hotline.tel) + '">Call the ER: ' +
                esc(index.emergency.hotline.mobile) + '</a><p class="pdh-qf__alert-small">Or dial 911.</p>' };
        }
        return null;
    }

    function setup(form) {
        var kind = form.getAttribute('data-kind');
        var input = form.elements.q;
        var panel = form.querySelector('[data-pdh-panel]');
        var alertBox = form.querySelector('[data-pdh-alert]');
        var shownAlert = '';
        var last = null;

        function close() {
            panel.hidden = true;
            input.setAttribute('aria-expanded', 'false');
        }

        function update() {
            if (!index) return;
            var q = norm(input.value);
            var alert = q ? alertHtml(q) : null;
            var alertKey = alert ? alert.kind : '';
            if (alertKey !== shownAlert) {           // only touch the live region when the alert changes
                alertBox.className = 'pdh-qf__alert' + (alert ? ' pdh-qf__alert--' + alert.kind : '');
                alertBox.innerHTML = alert ? alert.html : '';
                shownAlert = alertKey;
            }
            if (q.length < 2) { last = null; close(); return; }

            last = search(q);
            var docs = last.doctors.slice(0, 4).map(doctorRow);
            if (last.doctors.length > 4) {
                docs.push('<li><a href="/doctors/?q=' + encodeURIComponent(input.value.trim()) + '"><strong>See all ' +
                    last.doctors.length + ' matching doctors</strong></a></li>');
            }
            var specs = group('Specialties', last.specialties.map(specialtyRow));
            var services = group(kind === 'service' ? 'Where to go' : 'Services', last.services.slice(0, kind === 'service' ? 4 : 2).map(serviceRow));
            var html = kind === 'service' ? services + group('Specialists', last.specialties.slice(0, 2).map(specialtyRow))
                : specs + group('Doctors', docs) + services;
            if (!html && alert) { close(); return; }  // the safety banner is the answer; no "no matches" noise
            if (!html) {
                html ='<p class="pdh-qf__none">No matches for “' + esc(input.value.trim()) + '”. Call <a href="' +
                    esc(index.appointments.tel) + '">' + esc(index.appointments.label) + '</a> and we’ll help you find the right ' +
                    (kind === 'service' ? 'department' : 'doctor') + '.</p>';
            }
            panel.innerHTML = html;
            panel.hidden = false;
            input.setAttribute('aria-expanded', 'true');
        }

        // Search button / Enter: go to the best match instead of a plain text search.
        form.addEventListener('submit', function (ev) {
            if (!index || !input.value.trim()) return;  // native submit to /doctors/ or /services/
            ev.preventDefault();
            var raw = input.value.trim();
            var r = last || search(norm(raw));
            var top = function (list) { return list.length && list[0].score >= 75 ? list[0].item : null; };
            var url;
            if (kind === 'service') {
                url = top(r.services) ? '/services/#' + top(r.services).id : '/services/?q=' + encodeURIComponent(raw);
            } else if (r.doctors.length === 1) {
                url = '/doctors/' + r.doctors[0].item.id + '/';
            } else if (top(r.specialties) && !r.doctors.length) {
                url = top(r.specialties).url;
            } else if (!r.doctors.length && top(r.services)) {
                url = '/services/#' + top(r.services).id;
            } else {
                url = '/doctors/?q=' + encodeURIComponent(raw);
            }
            location.href = url;
        });

        var timer;
        input.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(update, 120); });
        input.addEventListener('focus', function () { if (input.value.trim().length >= 2) update(); });
        input.addEventListener('keydown', function (ev) {
            if (ev.key === 'ArrowDown' && !panel.hidden) {
                var first = panel.querySelector('a');
                if (first) { ev.preventDefault(); first.focus(); }
            } else if (ev.key === 'Escape') {
                close();
            }
        });
        panel.addEventListener('keydown', function (ev) {
            var links = [].slice.call(panel.querySelectorAll('a'));
            var i = links.indexOf(document.activeElement);
            if (ev.key === 'ArrowDown' && i < links.length - 1) { ev.preventDefault(); links[i + 1].focus(); }
            else if (ev.key === 'ArrowUp') { ev.preventDefault(); (i > 0 ? links[i - 1] : input).focus(); }
            else if (ev.key === 'Escape') { close(); input.focus(); }
        });
        form.addEventListener('focusout', function () {
            setTimeout(function () { if (!form.contains(document.activeElement)) close(); }, 0);
        });
    }

    function fillStats() {
        var counts = {};
        index.departments.concat(index.specialties).forEach(function (x) { counts[x.url] = x.count; });
        [].forEach.call(root.querySelectorAll('[data-pdh-chip-count]'), function (span) {
            var href = span.parentNode.getAttribute('href');
            if (counts[href] != null) span.textContent = counts[href];
        });

        // "In clinic today" card: today's count plus a clickable 7-day chart, by the day in the Philippines.
        var today = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'Asia/Manila' }).format(new Date());
        var perDay = {};
        Object.keys(WEEKDAYS).forEach(function (day) {
            perDay[day] = index.doctors.filter(function (d) { return d.days.indexOf(day) !== -1; }).length;
        });
        var countEl = document.querySelector('[data-pdh-today-count]');
        if (countEl && WEEKDAYS[today]) {
            countEl.innerHTML = '<strong data-pdh-countup="' + perDay[today] + '">' + perDay[today] + '</strong> ' +
                (perDay[today] === 1 ? 'doctor' : 'doctors') + ' <span>&middot; ' + WEEKDAYS[today] + '</span>';
            var link = document.querySelector('[data-pdh-today-link]');
            link.href = '/doctors/?day=' + today;
            link.textContent = 'View today’s schedules';
        }
        var week = document.querySelector('[data-pdh-week]');
        if (week) {
            var max = Math.max.apply(null, Object.keys(perDay).map(function (k) { return perDay[k]; })) || 1;
            week.innerHTML = Object.keys(WEEKDAYS).map(function (day) {
                var n = perDay[day];
                return '<li' + (day === today ? ' class="is-today"' : '') + '><a href="/doctors/?day=' + day + '" aria-label="' +
                    WEEKDAYS[day] + ': ' + n + (n === 1 ? ' doctor' : ' doctors') + ' in clinic' + (day === today ? ' (today)' : '') + '">' +
                    '<span class="pdh-week__bar" style="--h:' + Math.max(6, Math.round(n / max * 100)) + '%"></span>' +
                    '<span class="pdh-week__day">' + day.charAt(0) + '</span></a></li>';
            }).join('');
        }

        // Trust row: real doctor photos plus totals.
        var faces = document.querySelector('[data-pdh-faces]');
        if (faces && index.faces) {
            faces.innerHTML = index.faces.map(function (f) {
                return '<img src="' + esc(f.photo) + '" alt="" width="44" height="44" loading="lazy" decoding="async">';
            }).join('');
        }
        var trust = document.querySelector('[data-pdh-trust-text]');
        if (trust) {
            trust.innerHTML = '<strong>' + index.doctors.length + ' doctors</strong> across ' + index.specialty_count +
                ' specialties <a href="/doctors/">Meet them</a>';
        }
        var open = document.querySelector('[data-pdh-open247]');
        if (open) {
            var n247 = index.services.filter(function (s) { return s.cat === 'service' && s.open247; }).length;
            open.textContent = n247;
            open.setAttribute('data-pdh-countup', n247);
        }
        countUp();
    }

    // Numbers roll up from zero once, unless the visitor prefers reduced motion.
    function countUp() {
        if (reducedMotion) return;
        [].forEach.call(document.querySelectorAll('[data-pdh-countup]'), function (el) {
            var target = parseInt(el.getAttribute('data-pdh-countup'), 10);
            var start = null;
            function step(ts) {
                if (start === null) start = ts;
                var p = Math.min(1, (ts - start) / 900);
                el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
                if (p < 1) requestAnimationFrame(step);
            }
            requestAnimationFrame(step);
        });
    }

    // Tabs: "Find a doctor" / "Find a service" (WAI-ARIA tabs pattern, arrow keys move between tabs).
    function setupTabs() {
        var tabs = [].slice.call(root.querySelectorAll('[role="tab"]'));
        function select(tab, focus) {
            tabs.forEach(function (t) {
                var on = t === tab;
                t.setAttribute('aria-selected', on ? 'true' : 'false');
                t.tabIndex = on ? 0 : -1;
                document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
            });
            if (focus) tab.focus();
        }
        tabs.forEach(function (tab, i) {
            tab.addEventListener('click', function () {
                select(tab, false);
                document.getElementById(tab.getAttribute('aria-controls')).querySelector('input[name="q"]').focus();
            });
            tab.addEventListener('keydown', function (ev) {
                var next = ev.key === 'ArrowRight' ? tabs[(i + 1) % tabs.length] : ev.key === 'ArrowLeft' ? tabs[(i - 1 + tabs.length) % tabs.length] : null;
                if (next) { ev.preventDefault(); select(next, true); }
            });
        });
        var start = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0] || tabs[0];
        if (start) select(start, false);
    }

    // "Is my HMO accepted?" tile: checks the published partner list. Never says "not accepted";
    // anything not on the list is referred to the HMO Hub.
    function setupHmo() {
        var form = document.querySelector('[data-pdh-hmo]');
        if (!form || !index.hmo) return;
        var input = form.querySelector('input');
        var out = form.querySelector('[data-pdh-hmo-result]');
        var initial = out.innerHTML;
        var list = document.getElementById(input.getAttribute('list'));
        list.innerHTML = index.hmo.partners.map(function (n) { return '<option value="' + esc(n) + '">'; }).join('');
        var partners = index.hmo.partners.map(function (n) { return { name: n, words: norm(n).split(' ') }; });
        var hub = index.hmo.hub ? ' Call our HMO Hub at <a href="' + esc(index.hmo.hub.tel) + '">' + esc(index.hmo.hub.mobile) + '</a>' : ' Call our HMO Hub';

        function check() {
            var q = norm(input.value);
            if (q.length < 2) { out.innerHTML = initial; return; }
            var tokens = q.split(' ');
            var hits = partners.filter(function (p) {
                return tokens.every(function (t) { return p.words.some(function (w) { return w.indexOf(t) === 0; }); });
            });
            if (hits.length === 1 || (hits.length && norm(hits[0].name) === q)) {
                out.innerHTML = '<strong class="pdh-hmo__yes">Yes, ' + esc(hits[0].name) + ' is one of our HMO partners.</strong> ' +
                    '<a href="' + esc(index.hmo.approval_url) + '" target="_blank" rel="noopener">Request HMO approval online</a>';
            } else if (hits.length) {
                out.textContent = 'Keep typing: ' + hits.map(function (h) { return h.name; }).join(', ');
            } else if (q.length >= 3) {
                out.innerHTML = '“' + esc(input.value.trim()) + '” isn’t on our published partner list.' + hub + ' to check your coverage.';
            }
        }
        input.addEventListener('input', check);
        input.addEventListener('change', check);
        form.addEventListener('submit', function (ev) { ev.preventDefault(); check(); });
    }

    setupTabs();
    [].forEach.call(root.querySelectorAll('form[data-kind]'), setup);

    fetch('/data/search-index.json')
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) {
            index = prepare(data);
            fillStats();
            setupHmo();
            [].forEach.call(root.querySelectorAll('form[data-kind] input[name="q"]'), function (input) {
                if (input.value.trim()) input.dispatchEvent(new Event('input'));
            });
        })
        .catch(function () { /* keep the plain forms working */ });

    // Hero core-values slideshow: cross-fades every 6 s; pauses on hover/focus, when the tab is hidden,
    // or via the pause button (WCAG 2.2.2). With reduced motion it never advances on its own.
    function setupSlides() {
        var box = document.querySelector('[data-pdh-slides]');
        if (!box) return;
        var slides = [].slice.call(box.querySelectorAll('img[data-value]'));
        var dots = [].slice.call(box.querySelectorAll('.pdh-arch__dot'));
        var title = box.querySelector('[data-pdh-slide-title]');
        var desc = box.querySelector('[data-pdh-slide-desc]');
        var pause = box.querySelector('[data-pdh-pause]');
        var current = 0, timer = null, paused = reducedMotion, hovering = false;

        function show(i) {
            current = (i + slides.length) % slides.length;
            slides.forEach(function (img, n) {
                img.classList.toggle('is-active', n === current);
                if (n === (current + 1) % slides.length) img.loading = 'eager';  // preload the next slide
            });
            dots.forEach(function (d, n) {
                d.classList.toggle('is-active', n === current);
                if (n === current) d.setAttribute('aria-current', 'true'); else d.removeAttribute('aria-current');
            });
            title.textContent = slides[current].getAttribute('data-value');
            desc.textContent = slides[current].getAttribute('data-desc');
        }
        function schedule() {
            clearTimeout(timer);
            if (!paused && !hovering && !document.hidden) timer = setTimeout(function () { show(current + 1); schedule(); }, 6000);
        }
        function setPaused(value) {
            paused = value;
            box.classList.toggle('is-paused', paused);
            pause.setAttribute('aria-label', paused ? 'Play slideshow' : 'Pause slideshow');
            pause.innerHTML = paused
                ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>'
                : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z"/></svg>';
            schedule();
        }
        dots.forEach(function (d, n) { d.addEventListener('click', function () { show(n); schedule(); }); });
        pause.addEventListener('click', function () { setPaused(!paused); });
        box.addEventListener('mouseenter', function () { hovering = true; schedule(); });
        box.addEventListener('mouseleave', function () { hovering = false; schedule(); });
        box.addEventListener('focusin', function () { hovering = true; schedule(); });
        box.addEventListener('focusout', function () { hovering = false; schedule(); });
        document.addEventListener('visibilitychange', schedule);
        setPaused(paused);
    }

    // Subtle 3D tilt of the hero photo and its floating cards toward the cursor (desktop mouse only).
    function setupTilt() {
        var el = document.querySelector('[data-pdh-tilt]');
        if (!el || reducedMotion || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
        var frame = null;
        el.classList.add('is-tiltable');
        el.addEventListener('pointermove', function (ev) {
            var r = el.getBoundingClientRect();
            var x = (ev.clientX - r.left) / r.width - 0.5;
            var y = (ev.clientY - r.top) / r.height - 0.5;
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(function () {
                el.style.setProperty('--tilt-x', (-y * 6).toFixed(2) + 'deg');
                el.style.setProperty('--tilt-y', (x * 6).toFixed(2) + 'deg');
            });
        });
        el.addEventListener('pointerleave', function () {
            cancelAnimationFrame(frame);
            el.style.setProperty('--tilt-x', '0deg');
            el.style.setProperty('--tilt-y', '0deg');
        });
    }

    // "Our Story": load the Vimeo player only when the visitor presses play (no autoplaying video,
    // no Vimeo requests or data use until then). With sound, since the visitor chose to watch.
    function setupVideo() {
        [].forEach.call(document.querySelectorAll('[data-pdh-video]'), function (box) {
            var link = box.querySelector('a');
            link.addEventListener('click', function (ev) {
                ev.preventDefault();
                var frame = document.createElement('iframe');
                frame.src = 'https://player.vimeo.com/video/' + box.getAttribute('data-pdh-video') + '?autoplay=1&dnt=1&title=0&byline=0&portrait=0';
                frame.title = 'Alagang PDH Ako video';
                frame.allow = 'autoplay; fullscreen; picture-in-picture';
                frame.allowFullscreen = true;
                box.replaceChildren(frame);
                frame.focus();
            });
        });
    }
})();
