/* Services directory: filters the pre-rendered service cards in services/index.html, which are grouped by
   patient need. Without JavaScript every card stays visible. Filters are mirrored in the URL (?q=&need=&open=24-7).
   Searches for an ambiguous word (e.g. "ultrasound") also show a short note that explains the different matches. */
(function () {
    var form = document.querySelector('[data-pdh-services]');
    if (!form) return;

    var cards = [].slice.call(document.querySelectorAll('[data-pdh-results] .pdh-svc'));
    var groups = [].slice.call(document.querySelectorAll('[data-group-section]'));
    var notes = [].slice.call(document.querySelectorAll('[data-clarify]'));
    var count = document.querySelector('[data-pdh-count]');
    var empty = document.querySelector('[data-pdh-empty]');
    var timer;

    // Lowercase and strip accents; mirrors fold() in tools/build_pages.py.
    function fold(text) {
        return (text || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    }

    function render() {
        var q = fold(form.elements.q.value).trim();
        var terms = q.split(/\s+/).filter(Boolean);
        var need = form.elements.need.value;
        var open = form.elements.open.checked;
        var hits = 0;
        cards.forEach(function (card) {
            var d = card.dataset;
            var ok = (!need || d.group === need) && (!open || d.open === '24-7') &&
                terms.every(function (t) { return d.search.indexOf(t) !== -1; });
            card.hidden = !ok;
            if (ok) hits++;
        });
        groups.forEach(function (g) { g.hidden = !g.querySelector('.pdh-svc:not([hidden])'); });
        notes.forEach(function (n) {
            n.hidden = !q || !n.getAttribute('data-clarify').split('|').some(function (t) {
                return (' ' + q + ' ').indexOf(' ' + t + ' ') !== -1;
            });
        });
        count.textContent = hits === 1 ? '1 service or facility' : hits + ' services and facilities';
        empty.hidden = hits !== 0;
    }

    function update() {
        render();
        var params = new URLSearchParams();
        if (form.elements.q.value) params.set('q', form.elements.q.value);
        if (form.elements.need.value) params.set('need', form.elements.need.value);
        if (form.elements.open.checked) params.set('open', '24-7');
        var qs = params.toString();
        history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
    }

    var params = new URLSearchParams(location.search);
    if (params.get('q')) form.elements.q.value = params.get('q');
    if ([].some.call(form.elements.need.options, function (o) { return o.value && o.value === params.get('need'); })) {
        form.elements.need.value = params.get('need');
    }
    form.elements.open.checked = params.get('open') === '24-7';

    form.addEventListener('submit', function (ev) { ev.preventDefault(); update(); });
    form.elements.q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(update, 150); });
    form.elements.need.addEventListener('change', update);
    form.elements.open.addEventListener('change', update);
    form.addEventListener('reset', function () { setTimeout(update, 0); });

    render();
})();
