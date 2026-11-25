/* Homepage quick search ("Find a doctor" / "Find a service" cards in the hero).
   Data: /data/search-index.json (built by tools/build_pages.py from data/*.json and data/search-terms.json).
   Without JavaScript, or if the index fails to load, each card is a plain form that submits to
   /doctors/?q= or /services/?q=. */
(function () {
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

        var today = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'Asia/Manila' }).format(new Date());
        var n = index.doctors.filter(function (d) { return d.days.indexOf(today) !== -1; }).length;
        var todayEl = root.querySelector('[data-pdh-today]');
        if (todayEl && WEEKDAYS[today]) {
            todayEl.innerHTML = '<span><strong>' + n + '</strong> ' + (n === 1 ? 'doctor' : 'doctors') + ' in clinic today, ' +
                WEEKDAYS[today] + '</span> <a href="/doctors/?day=' + today + '">View today’s schedules</a>';
        }

        var open = index.services.filter(function (s) { return s.cat === 'service' && s.open247; }).length;
        var openEl = root.querySelector('[data-pdh-open247]');
        if (openEl) {
            openEl.innerHTML = '<span><strong>' + open + '</strong> medical services open 24/7</span> ' +
                '<a href="/services/?cat=service&amp;open=24-7">View 24/7 services</a>';
        }
    }

    [].forEach.call(root.querySelectorAll('form[data-kind]'), setup);

    fetch('/data/search-index.json')
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) {
            index = prepare(data);
            fillStats();
            [].forEach.call(root.querySelectorAll('form[data-kind] input[name="q"]'), function (input) {
                if (input.value.trim()) input.dispatchEvent(new Event('input'));
            });
        })
        .catch(function () { /* keep the plain forms working */ });
})();
