/* Services directory: filters the pre-rendered service cards in services/index.html.
   Without JavaScript every card stays visible. Filters are mirrored in the URL (?q=&cat=&open=24-7);
   deep links like /services/#hemodialysis-center work with or without it. */
(function () {
    var form = document.querySelector('[data-pdh-services]');
    if (!form) return;

    var cards = [].slice.call(document.querySelectorAll('[data-pdh-results] .pdh-svc'));
    var count = document.querySelector('[data-pdh-count]');
    var empty = document.querySelector('[data-pdh-empty]');
    var timer;

    // Lowercase and strip accents; mirrors fold() in tools/build_pages.py.
    function fold(text) {
        return (text || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    }

    function render() {
        var terms = fold(form.elements.q.value).split(/\s+/).filter(Boolean);
        var cat = form.elements.cat.value;
        var open = form.elements.open.checked;
        var hits = 0;
        cards.forEach(function (card) {
            var d = card.dataset;
            var ok = (!cat || d.cat === cat) && (!open || d.open === '24-7') &&
                terms.every(function (t) { return d.search.indexOf(t) !== -1; });
            card.hidden = !ok;
            if (ok) hits++;
        });
        count.textContent = hits === 1 ? '1 service or facility' : hits + ' services and facilities';
        empty.hidden = hits !== 0;
    }

    function update() {
        render();
        var params = new URLSearchParams();
        if (form.elements.q.value) params.set('q', form.elements.q.value);
        if (form.elements.cat.value) params.set('cat', form.elements.cat.value);
        if (form.elements.open.checked) params.set('open', '24-7');
        var qs = params.toString();
        history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
    }

    var params = new URLSearchParams(location.search);
    if (params.get('q')) form.elements.q.value = params.get('q');
    if ([].some.call(form.elements.cat.options, function (o) { return o.value && o.value === params.get('cat'); })) {
        form.elements.cat.value = params.get('cat');
    }
    form.elements.open.checked = params.get('open') === '24-7';

    form.addEventListener('submit', function (ev) { ev.preventDefault(); update(); });
    form.elements.q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(update, 150); });
    form.elements.cat.addEventListener('change', update);
    form.elements.open.addEventListener('change', update);
    form.addEventListener('reset', function () { setTimeout(update, 0); });

    render();
})();
