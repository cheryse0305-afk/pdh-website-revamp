/* Kriss, the PDH concierge (prototype). The launcher is created by this script, so nothing shows without JS.
   Replies come from /api/chat (Claude, grounded in data/*.json) when the server has an API key; otherwise
   ("guided" mode) they are built here from /data/search-index.json and /data/contacts.json.
   Emergency and crisis phrases always get the hotline card first, in both modes.
   The conversation is kept in sessionStorage so it survives moving between pages. */
(function () {
    'use strict';

    var STORE = 'pdh-kriss-v1';
    var MAX_HISTORY = 12;
    var MAX_CHARS = 600;
    var MAPS = 'https://www.google.com/maps/search/?api=1&query=Para%C3%B1aque+Doctors+Hospital%2C+175+Do%C3%B1a+Soledad+Ave%2C+Para%C3%B1aque';
    var DAY_CODES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    var DAY_NAMES = { Mon: 'Monday', Tue: 'Tuesday', Wed: 'Wednesday', Thu: 'Thursday', Fri: 'Friday', Sat: 'Saturday', Sun: 'Sunday' };
    var DAY_WORDS = {
        monday: 'Mon', mon: 'Mon', lunes: 'Mon', tuesday: 'Tue', tue: 'Tue', tues: 'Tue', martes: 'Tue',
        wednesday: 'Wed', wed: 'Wed', miyerkules: 'Wed', miyerkoles: 'Wed', thursday: 'Thu', thu: 'Thu', thurs: 'Thu', huwebes: 'Thu',
        friday: 'Fri', fri: 'Fri', biyernes: 'Fri', saturday: 'Sat', sat: 'Sat', sabado: 'Sat', sunday: 'Sun', sun: 'Sun', linggo: 'Sun'
    };
    var CHIPS = [
        ['Find a doctor', 'I want to find a doctor'],
        ['Doctors in clinic today', 'Which doctors are in clinic today?'],
        ['Book an appointment', 'How do I book an appointment?'],
        ['HMO coverage', 'Which HMOs do you accept?'],
        ['Services & floors', 'Where can I find your services?'],
        ['Contact numbers', 'What are your contact numbers?']
    ];
    var WELCOME = "Kumusta! Ako si **Kriss**, ang virtual concierge ng PDH. I can help you find a doctor, check clinic schedules, " +
        'find services and floors, check HMO coverage, and guide you through booking an appointment. What can I help you with?';

    var state = load() || { mode: 'unknown', msgs: [], open: false };
    var data = null, dataPromise = null, busy = false;
    var root, launcher, panel, log, chips, form, input, sendBtn, statusEl;

    // ------------------------------------------------------------------ storage

    function load() {
        try { var s = JSON.parse(sessionStorage.getItem(STORE)); return s && Array.isArray(s.msgs) ? s : null; } catch (e) { return null; }
    }

    function save() {
        try { sessionStorage.setItem(STORE, JSON.stringify(state)); } catch (e) { /* private mode: chat still works for this page */ }
    }

    // ------------------------------------------------------------------ text helpers

    function norm(text) {
        return (text || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/['’]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
    }

    function esc(text) {
        return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function has(q, phrase) {
        return !!phrase && (' ' + q + ' ').indexOf(' ' + phrase + ' ') !== -1;
    }

    function hasAny(q, phrases) {
        return phrases.some(function (p) { return has(q, p); });
    }

    function tel(number) {
        var digits = String(number).replace(/[^\d+]/g, '');
        return 'tel:' + (digits.charAt(0) === '0' ? '+63' + digits.slice(1) : digits);
    }

    // Links allowed in replies: site paths, phone numbers and the few external sites PDH uses.
    var SAFE_URL = /^(\/[^\s"'<>]*|tel:\+?[\d-]+|https:\/\/(pdh\.com\.ph|m\.me|docs\.google\.com|www\.google\.com\/maps)[^\s"'<>]*)$/;

    function inline(text) {
        var out = esc(text).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        return out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (m, label, url) {
            var raw = url.replace(/&amp;/g, '&');
            if (!SAFE_URL.test(raw)) return label;
            var ext = /^https:/.test(raw) ? ' target="_blank" rel="noopener"' : '';
            return '<a href="' + esc(raw) + '"' + ext + '>' + label + '</a>';
        });
    }

    // Minimal Markdown: paragraphs, "-" / "1." lists, **bold** and [links](url).
    function render(md) {
        var html = '', list = null;
        String(md).split(/\n/).forEach(function (line) {
            var t = line.trim(), m = t.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
            if (m) {
                if (!list) { list = /^\d/.test(t) ? 'ol' : 'ul'; html += '<' + list + '>'; }
                html += '<li>' + inline(m[1]) + '</li>';
                return;
            }
            if (list) { html += '</' + list + '>'; list = null; }
            if (t) html += '<p>' + inline(t.replace(/^#+\s*/, '')) + '</p>';
        });
        if (list) html += '</' + list + '>';
        return html;
    }

    function manilaDay(offset) {
        var d = new Date(Date.now() + (offset || 0) * 864e5);
        var name = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Manila', weekday: 'short' }).format(d);
        return DAY_CODES.indexOf(name) !== -1 ? name : DAY_CODES[d.getDay()];
    }

    // ------------------------------------------------------------------ data (guided mode + safety phrases)

    function getData() {
        if (!dataPromise) {
            dataPromise = Promise.all([
                fetch('/data/search-index.json').then(function (r) { return r.json(); }),
                fetch('/data/contacts.json').then(function (r) { return r.json(); })
            ]).then(function (res) {
                var d = res[0];
                d.contacts = res[1].items[0];
                d.specialties.forEach(function (s) { s._label = norm(s.label); s._terms = s.terms.map(norm); });
                d.services.forEach(function (s) { s._name = norm(s.name); s._terms = s.terms.map(norm); });
                d.doctors.forEach(function (doc) {
                    var parts = doc.n.split(',');
                    doc._last = norm(parts[0]);
                    doc._first = norm(parts[1] || '').split(' ')[0] || '';
                });
                d.emergency._phrases = d.emergency.phrases.map(norm);
                d.crisis._phrases = d.crisis.phrases.map(norm);
                d.hmo._partners = d.hmo.partners.map(function (p) {
                    var n = norm(p), first = n.split(' ')[0];
                    return { name: p, keys: [n].concat(first.length >= 5 && first !== n ? [first] : []) };
                });
                data = d;
                return d;
            }).catch(function (e) { dataPromise = null; throw e; });
        }
        return dataPromise;
    }

    function safetyCard(q) {
        if (hasAny(q, data.crisis._phrases)) {
            return data.crisis.message + '\n' + data.crisis.hotlines.map(function (h) {
                return '- ' + h.name + ': [' + h.number + '](tel:' + h.tel.replace(/^tel:/, '') + ')';
            }).join('\n') + '\n- PDH Emergency Room (Ground Floor, open 24/7): [' + data.emergency.hotline.mobile + '](' + data.emergency.hotline.tel + ')';
        }
        if (hasAny(q, data.emergency._phrases)) {
            return '**If this is an emergency, please don\'t wait.** Come to the PDH Emergency Room (Ground Floor, open 24/7), ' +
                'call the ER at [' + data.emergency.hotline.mobile + '](' + data.emergency.hotline.tel + '), or dial [911](tel:911).';
        }
        return null;
    }

    // ------------------------------------------------------------------ guided answers

    function hotline(id) {
        return data.contacts.hotlines.filter(function (h) { return h.id === id; })[0];
    }

    function infoLine() {
        var info = hotline('information-services');
        return info ? 'call Information Services at [' + info.mobile + '](' + tel(info.mobile) + ')'
            : 'call PDH at [' + data.appointments.label + '](' + data.appointments.tel + ')';
    }

    function doctorLine(d) {
        var sched = d.sch || (d.oc ? 'On call' : 'Schedule not listed');
        return '- [' + d.n + '](/doctors/' + d.id + '/) – ' + (d.s || d.d || 'General') + ' · ' + sched;
    }

    function findDay(q) {
        if (hasAny(q, ['today', 'ngayon', 'now', 'tonight', 'mamaya'])) return manilaDay(0);
        if (hasAny(q, ['tomorrow', 'bukas'])) return manilaDay(1);
        var words = q.split(' ');
        for (var i = 0; i < words.length; i++) if (DAY_WORDS[words[i]]) return DAY_WORDS[words[i]];
        return null;
    }

    function findSpecialty(q) {
        var best = null, bestScore = 0;
        data.specialties.forEach(function (s) {
            var score = has(q, s._label) ? 100 : 0;
            s._terms.forEach(function (t) { if (has(q, t)) score = Math.max(score, 80 + Math.min(t.length, 19)); });
            if (score > bestScore) { best = s; bestScore = score; }
        });
        return best;
    }

    // generic: skip matches on words like "clinic" (the question is about doctors, not the OPD floor)
    function findServices(q, generic) {
        return data.services.map(function (s) {
            var score = has(q, s._name) ? 100 : 0;
            s._terms.forEach(function (t) {
                if (t.length > 2 && has(q, t) && !(generic && /^clinics?$/.test(t))) score = Math.max(score, 80 + Math.min(t.length, 19));
            });
            return { s: s, score: score };
        }).filter(function (r) { return r.score; }).sort(function (a, b) { return b.score - a.score; }).slice(0, 2)
            .map(function (r) { return r.s; });
    }

    // A surname counts when it follows "dr"/"doc", comes with the first name, or is long and nothing else matched
    // (so "doktor sa mata" means an eye doctor, not Dr. Mata).
    function findDoctors(q, otherMatch) {
        var hits = data.doctors.filter(function (d) {
            if (!d._last || !has(q, d._last)) return false;
            if (/\b(dr|dra|doc|doctor|doktor)\s+$/.test((' ' + q + ' ').split(' ' + d._last + ' ')[0] + ' ')) return true;
            if (d._first && d._first.length > 2 && has(q, d._first)) return true;
            return !otherMatch && d._last.length >= 5;
        });
        hits.sort(function (a, b) { return (has(q, b._first) ? 1 : 0) - (has(q, a._first) ? 1 : 0); });
        return hits;
    }

    function findPartner(q) {
        for (var i = 0; i < data.hmo._partners.length; i++) {
            var p = data.hmo._partners[i];
            if (p.keys.some(function (k) { return has(q, k); })) return p.name;
        }
        return null;
    }

    function serviceAnswer(s) {
        var lines = ['**' + s.name + '**'];
        if (s.loc) lines.push('- Location: ' + s.loc + ' ([floor directory](/directory/?q=' +
            encodeURIComponent(s.name).replace(/\(/g, '%28').replace(/\)/g, '%29') + '))');
        if (s.hours) lines.push('- Hours: ' + s.hours.replace(/\s*\n\s*/g, '; '));
        lines.push('- [More about ' + s.name + '](/services/#' + s.id + ')');
        return lines.join('\n');
    }

    function specialtyAnswer(spec, day) {
        var docs = spec.ix.map(function (i) { return data.doctors[i]; });
        var url = spec.url;
        if (day) {
            docs = docs.filter(function (d) { return d.days.indexOf(day) !== -1; });
            url += '&day=' + day;
        }
        if (!docs.length) {
            return 'I couldn\'t find ' + spec.label + ' doctors with a listed clinic on ' + DAY_NAMES[day] + '. ' +
                '[See all ' + spec.count + ' ' + spec.label + ' doctors](' + spec.url + ') for their schedules, or ' + infoLine() + '.';
        }
        var head = docs.length + ' ' + spec.label + (docs.length === 1 ? ' doctor' : ' doctors') +
            (day ? ' with clinic on ' + DAY_NAMES[day] : ' at PDH') + (docs.length > 5 ? ', for example:' : ':');
        return head + '\n' + docs.slice(0, 5).map(doctorLine).join('\n') +
            (docs.length > 5 ? '\n[See all ' + docs.length + ' in the Doctor Finder](' + url + ')' : '');
    }

    function appointmentAnswer() {
        return 'PDH doesn\'t have online booking yet, but here\'s how to set an appointment:\n' +
            '1. Find your doctor and their clinic days in the [Doctor Finder](/doctors/).\n' +
            '2. Call the appointment line at [' + data.appointments.label + '](' + data.appointments.tel + ') to book.\n' +
            '3. Using an HMO? Request approval first with the [HMO online approval form](' + data.hmo.approval_url + ').\n' +
            'Clinic schedules can change, so it\'s best to confirm when you call.';
    }

    function guided(text) {
        var q = norm(text);
        var words = q.split(' ');
        if (!q) return null;
        if (words.length <= 4 && hasAny(q, ['hi', 'hello', 'hey', 'helo', 'kumusta', 'kamusta', 'good morning', 'good afternoon', 'good evening', 'magandang umaga', 'magandang hapon', 'magandang gabi'])) {
            return 'Kumusta! Ano ang maitutulong ko? You can ask about doctors, clinic schedules, services, HMOs or appointments, in English or Filipino.';
        }
        if (words.length <= 5 && hasAny(q, ['thanks', 'thank you', 'salamat', 'ty', 'thank u'])) {
            return 'You\'re welcome! Is there anything else I can help you with?';
        }

        var day = findDay(q);
        var spec = findSpecialty(q);
        var services = findServices(q, !!day || hasAny(q, ['doctor', 'doctors', 'doktor']));
        var partner = findPartner(q);
        var doctors = findDoctors(q, !!(spec || services.length || partner));
        var wantsAppt = hasAny(q, ['appointment', 'appointments', 'appt', 'book', 'booking', 'reserve', 'consult', 'consultation', 'check up', 'checkup', 'magpatingin', 'magpa appointment', 'pa appointment', 'magpa schedule', 'pa schedule']);
        var wantsHmo = hasAny(q, ['hmo', 'hmos', 'insurance', 'accredited', 'coverage', 'covered', 'loa', 'approval', 'tanggap', 'accept', 'healthcard', 'health card']);
        var wantsContact = hasAny(q, ['contact', 'number', 'numbers', 'hotline', 'hotlines', 'phone', 'telephone', 'telepono', 'numero', 'email', 'landline', 'call']);
        var wantsAddress = hasAny(q, ['address', 'directions', 'direction', 'direksyon', 'map', 'located', 'location of pdh', 'where is pdh', 'where are you', 'saan kayo', 'how to get', 'paano pumunta']);
        var wantsUnknown = hasAny(q, ['price', 'prices', 'cost', 'rate', 'rates', 'magkano', 'how much', 'fee', 'fees', 'presyo', 'visiting', 'bisita', 'visitor', 'visitors', 'parking', 'result', 'results']);
        var wantsDoctor = hasAny(q, ['doctor', 'doctors', 'doktor', 'dr', 'specialist', 'clinic', 'in clinic']);

        var parts = [];
        if (wantsUnknown) {
            parts.push('I don\'t have information on prices, rates, visiting rules or results yet. For those, please ' + infoLine() + '.');
        }
        if (partner) {
            parts.push('Yes, **' + partner + '** is listed among PDH\'s HMO partners. To use it, request approval with the [HMO online approval form](' + data.hmo.approval_url + ')' +
                (data.hmo.hub ? ' or call the HMO Hub at [' + data.hmo.hub.mobile + '](' + data.hmo.hub.tel + ')' : '') + '.');
        } else if (wantsHmo && !spec && !doctors.length) {
            parts.push('PDH works with ' + data.hmo.partners.length + ' HMO partners, including ' + data.hmo.partners.slice(0, 8).join(', ') +
                ' and more. Tell me your HMO and I\'ll check, or see the logos on the [homepage](/#pdh-partners-title).\n' +
                'Before your visit, request approval with the [HMO online approval form](' + data.hmo.approval_url + ')' +
                (data.hmo.hub ? ' or call the HMO Hub at [' + data.hmo.hub.mobile + '](' + data.hmo.hub.tel + ')' : '') + '.');
        }
        if (doctors.length) {
            parts.push((doctors.length === 1 ? 'Here\'s the doctor I found:' : 'I found ' + doctors.length + ' doctors with that name:') + '\n' +
                doctors.slice(0, 5).map(doctorLine).join('\n') + '\nClinic schedules can change, so please call to confirm.');
        } else if (spec) {
            parts.push(specialtyAnswer(spec, day));
        } else if (day && (wantsDoctor || wantsAppt)) {
            var count = data.doctors.filter(function (d) { return d.days.indexOf(day) !== -1; }).length;
            parts.push(count + ' doctors have a listed clinic on ' + DAY_NAMES[day] + '. [See them in the Doctor Finder](/doctors/?day=' + day + '), ' +
                'or tell me the specialty you need (for example heart, children, skin or eyes) and I\'ll narrow it down.');
        }
        services.forEach(function (s) { if (parts.length < 3) parts.push(serviceAnswer(s)); });
        if (wantsAppt) parts.push(appointmentAnswer());

        if (!parts.length) {
            if (wantsContact) {
                parts.push('Here are PDH\'s hotlines:\n' + data.contacts.hotlines.map(function (h) {
                    return '- ' + h.name + ': [' + h.mobile + '](' + tel(h.mobile) + ')';
                }).join('\n') + '\n- Appointments: [' + data.appointments.label + '](' + data.appointments.tel + ')');
            } else if (wantsAddress) {
                parts.push('PDH is at ' + data.contacts.address + '. [Open in Google Maps](' + MAPS + ').');
            } else if (wantsDoctor) {
                parts.push('Sure! Which specialty do you need? For example ' + data.specialties.slice(0, 6).map(function (s) {
                    return '[' + s.label + '](' + s.url + ')';
                }).join(', ') + '. You can also search all ' + data.doctors.length + ' doctors by name, specialty or day in the [Doctor Finder](/doctors/).');
            } else if (hasAny(q, ['service', 'services', 'facility', 'facilities', 'floor', 'floors', 'where'])) {
                parts.push('You can browse every service with its floor and hours on the [Services page](/services/), or use the [floor-by-floor directory](/directory/). ' +
                    'Tell me what you\'re looking for (for example X-ray, laboratory, dialysis or pharmacy) and I\'ll point you there.');
            } else {
                parts.push('Sorry, I couldn\'t find an answer to that in PDH\'s information. Try asking about a doctor, a specialty, a service, an HMO or appointments, or ' + infoLine() + '.');
            }
        }
        return parts.join('\n\n');
    }

    // ------------------------------------------------------------------ AI

    function askAI() {
        var history = state.msgs.filter(function (m) { return m.role === 'user' || m.role === 'assistant'; })
            .slice(-MAX_HISTORY).map(function (m) { return { role: m.role, content: m.text.slice(0, m.role === 'user' ? MAX_CHARS : 2500) }; });
        while (history.length && history[0].role !== 'user') history.shift();
        // Merge consecutive same-role turns (e.g. a safety card followed by a reply) so the API sees strict alternation.
        var merged = [];
        history.forEach(function (m) {
            var last = merged[merged.length - 1];
            if (last && last.role === m.role) last.content = (last.content + '\n\n' + m.content).slice(-2500);
            else merged.push({ role: m.role, content: m.content });
        });
        return fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: merged })
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (body) { return { status: r.status, body: body }; });
        });
    }

    // ------------------------------------------------------------------ UI

    var ICON_CHAT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4h0A1.5 1.5 0 0 1 4 14.5z"/><path d="M12 6.5v6M9 9.5h6"/></svg>';
    var ICON_CLOSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    var ICON_SEND = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12l16-8-6 16-2.5-6.5z"/></svg>';
    var AVATAR = '<span class="pdh-kriss__avatar" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/></svg></span>';

    function build() {
        root = document.createElement('div');
        root.className = 'pdh-kriss';
        root.innerHTML =
            '<button type="button" class="pdh-kriss__launcher" aria-expanded="false" aria-controls="pdh-kriss-panel">' + ICON_CHAT +
            '<span class="pdh-kriss__launch-text"><strong>Ask Kriss</strong><span>PDH concierge</span></span></button>' +
            '<section class="pdh-kriss__panel" id="pdh-kriss-panel" role="dialog" aria-labelledby="pdh-kriss-title" aria-describedby="pdh-kriss-notice" hidden>' +
            '<header class="pdh-kriss__head">' + AVATAR +
            '<div class="pdh-kriss__title"><h2 id="pdh-kriss-title">Kriss</h2><p data-kriss-status>PDH concierge · Prototype</p></div>' +
            '<button type="button" class="pdh-kriss__close" aria-label="Close chat">' + ICON_CLOSE + '</button></header>' +
            '<p class="pdh-kriss__notice" id="pdh-kriss-notice"><strong>Prototype.</strong> Answers use information from pdh.com.ph that PDH hasn\'t verified yet, and aren\'t medical advice. ' +
            'Emergency? Call <a href="tel:+639215720589">0921 572 0589</a> or <a href="tel:911">911</a>.</p>' +
            '<div class="pdh-kriss__log" role="log" aria-live="polite" aria-label="Conversation with Kriss"></div>' +
            '<div class="pdh-kriss__chips" role="group" aria-label="Suggested questions"></div>' +
            '<form class="pdh-kriss__form" novalidate><label class="pdh-kriss__sr" for="pdh-kriss-input">Message Kriss</label>' +
            '<textarea id="pdh-kriss-input" rows="1" maxlength="' + MAX_CHARS + '" placeholder="Ask about doctors, services, HMOs…" autocomplete="off"></textarea>' +
            '<button type="submit" class="pdh-kriss__send" aria-label="Send">' + ICON_SEND + '</button></form>' +
            '<p class="pdh-kriss__foot">Please don\'t share personal medical details. To talk to PDH staff, call <a href="tel:+63287760644">8776-0644</a>.</p>' +
            '</section>';
        document.body.appendChild(root);
        launcher = root.querySelector('.pdh-kriss__launcher');
        panel = root.querySelector('.pdh-kriss__panel');
        log = root.querySelector('.pdh-kriss__log');
        chips = root.querySelector('.pdh-kriss__chips');
        form = root.querySelector('form');
        input = root.querySelector('textarea');
        sendBtn = root.querySelector('.pdh-kriss__send');
        statusEl = root.querySelector('[data-kriss-status]');

        CHIPS.forEach(function (c) {
            var b = document.createElement('button');
            b.type = 'button';
            b.textContent = c[0];
            b.addEventListener('click', function () { send(c[1]); });
            chips.appendChild(b);
        });

        launcher.addEventListener('click', function () { setOpen(panel.hidden); });
        root.querySelector('.pdh-kriss__close').addEventListener('click', function () { setOpen(false); });
        panel.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });
        form.addEventListener('submit', function (e) { e.preventDefault(); send(input.value); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(input.value); }
        });
        input.addEventListener('input', grow);

        showMode();
        state.msgs.forEach(function (m) { append(m.role, m.text, false); });
        if (!state.msgs.length) append('assistant', WELCOME, false);
        chips.hidden = state.msgs.length > 0;
        if (state.open && window.matchMedia('(min-width: 64em)').matches) setOpen(true, true);
    }

    function grow() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }

    function showMode() {
        statusEl.textContent = 'PDH concierge · Prototype' +
            (state.mode === 'ai' ? ' · AI answers' : state.mode === 'guided' ? ' · Guided answers' : '');
    }

    function setOpen(open, quiet) {
        panel.hidden = !open;
        launcher.setAttribute('aria-expanded', String(open));
        root.classList.toggle('is-open', open);
        document.documentElement.classList.toggle('pdh-kriss-open', open);
        state.open = open;
        save();
        if (open) {
            getData().catch(function () {});
            log.scrollTop = log.scrollHeight;
            if (!quiet) input.focus();
        } else if (!quiet) {
            launcher.focus();
        }
    }

    function append(role, text, store) {
        var row = document.createElement('div');
        row.className = 'pdh-kriss__msg pdh-kriss__msg--' + role;
        var bubble = document.createElement('div');
        bubble.className = 'pdh-kriss__bubble';
        if (role === 'user') bubble.textContent = text;
        else bubble.innerHTML = render(text);
        if (role !== 'user') {
            var who = document.createElement('span');
            who.className = 'pdh-kriss__sr';
            who.textContent = role === 'alert' ? 'Important: ' : 'Kriss: ';
            bubble.insertBefore(who, bubble.firstChild);
        }
        row.appendChild(bubble);
        log.appendChild(row);
        log.scrollTop = log.scrollHeight;
        if (store) {
            state.msgs.push({ role: role, text: text });
            state.msgs = state.msgs.slice(-40);
            save();
        }
        return row;
    }

    function typing(on) {
        var el = log.querySelector('.pdh-kriss__typing');
        if (on && !el) {
            el = document.createElement('div');
            el.className = 'pdh-kriss__msg pdh-kriss__msg--assistant pdh-kriss__typing';
            el.innerHTML = '<div class="pdh-kriss__bubble"><span class="pdh-kriss__sr">Kriss is typing</span><i></i><i></i><i></i></div>';
            log.appendChild(el);
            log.scrollTop = log.scrollHeight;
        } else if (!on && el) {
            el.parentNode.removeChild(el);
        }
    }

    function setBusy(on) {
        busy = on;
        sendBtn.disabled = on;
        log.setAttribute('aria-busy', String(on));
        typing(on);
    }

    function send(text) {
        text = String(text || '').trim().slice(0, MAX_CHARS);
        if (!text || busy) return;
        input.value = '';
        grow();
        chips.hidden = true;
        append('user', text, true);
        setBusy(true);

        getData().then(function () {
            var card = safetyCard(norm(text));
            if (card) append('alert', card, true);
            if (state.mode === 'guided') return reply(guided(text), card);
            return askAI().then(function (res) {
                if (res.status === 200 && res.body && res.body.reply) {
                    if (state.mode !== 'ai') { state.mode = 'ai'; showMode(); }
                    return reply(res.body.reply);
                }
                // No AI on this deployment (no key, or a static server without /api): switch to guided answers.
                if (res.status === 503 && res.body.code === 'not_configured' || [403, 404, 405, 501].indexOf(res.status) !== -1) {
                    state.mode = 'guided';
                    showMode();
                }
                return reply(guided(text), card);
            }, function () {
                return reply(guided(text), card);  // offline or network error: answer from the local data
            });
        }).catch(function () {
            reply('Sorry, I couldn\'t load PDH\'s information just now. Please try again, or call Information Services at [0998 520 7295](tel:+639985207295).');
        }).then(function () {
            setBusy(false);
            save();
        });
    }

    function reply(text, card) {
        setBusy(false);
        // When a safety card already answered, skip the guided "couldn't find" fallback underneath it.
        if (card && /^Sorry, I couldn't find/.test(text || '')) return;
        if (text) append('assistant', text, true);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
    else build();
})();
