/* Doctor Finder: filters the pre-rendered doctor cards in doctors/index.html.
   Without JavaScript the full list stays visible. Filters are mirrored in the URL (?q=&dept=&spec=&day=). */
(function () {
    var form = document.querySelector('[data-pdh-finder]');
    if (!form) return;

    var script = document.currentScript || document.querySelector('script[src$="pdh-doctors.js"]');
    var pageSize = parseInt(script && script.getAttribute('data-page-size'), 10) || 24;
    var cards = [].slice.call(document.querySelectorAll('[data-pdh-results] .pdh-doc'));
    var count = document.querySelector('[data-pdh-count]');
    var empty = document.querySelector('[data-pdh-empty]');
    var more = document.querySelector('[data-pdh-more]');
    var fields = ['q', 'dept', 'spec', 'day'];
    var shown = pageSize;
    var timer;

    // Lowercase and strip accents; mirrors fold() in tools/build_doctor_pages.py.
    function fold(text) {
        return (text || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    }

    function values() {
        var v = {};
        fields.forEach(function (name) { v[name] = form.elements[name].value; });
        return v;
    }

    function matches(card, v, terms) {
        var d = card.dataset;
        if (v.dept && d.dept !== v.dept) return false;
        if (v.spec && d.spec !== v.spec) return false;
        if (v.day === 'oncall' && !d.oncall) return false;
        if (v.day && v.day !== 'oncall' && (' ' + d.days + ' ').indexOf(' ' + v.day + ' ') === -1) return false;
        return terms.every(function (t) { return d.search.indexOf(t) !== -1; });
    }

    function render() {
        var v = values();
        var terms = fold(v.q).split(/\s+/).filter(Boolean);
        var hits = 0;
        cards.forEach(function (card) {
            var ok = matches(card, v, terms);
            if (ok) hits++;
            card.hidden = !ok || hits > shown;
        });
        count.textContent = hits === 1 ? '1 doctor' : hits + ' doctors';
        empty.hidden = hits !== 0;
        more.hidden = hits <= shown;
        if (!more.hidden) more.textContent = 'Show more doctors (' + (hits - shown) + ' more)';
    }

    function syncUrl() {
        var v = values();
        var params = new URLSearchParams();
        fields.forEach(function (name) { if (v[name]) params.set(name, v[name]); });
        var qs = params.toString();
        history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
    }

    function update() {
        shown = pageSize;
        render();
        syncUrl();
    }

    // Restore filters from the URL (e.g. /doctors/?spec=Cardiology).
    var params = new URLSearchParams(location.search);
    fields.forEach(function (name) {
        var value = params.get(name);
        var el = form.elements[name];
        if (value === null) return;
        if (el.tagName === 'SELECT' && ![].some.call(el.options, function (o) { return o.value === value; })) return;
        el.value = value;
    });

    form.addEventListener('submit', function (ev) { ev.preventDefault(); update(); });
    form.elements.q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(update, 150); });
    ['dept', 'spec', 'day'].forEach(function (name) { form.elements[name].addEventListener('change', update); });
    form.addEventListener('reset', function () { setTimeout(update, 0); });
    more.addEventListener('click', function () {
        var firstNew = cards.filter(function (c) { return !c.hidden; }).length;
        shown += pageSize;
        render();
        var next = cards.filter(function (c) { return !c.hidden; })[firstNew];
        if (next) next.querySelector('a').focus();
    });

    render();
})();
