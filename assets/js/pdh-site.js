/* Site-wide behaviour (every page):
   - the header turns compact once the page has scrolled (html.pdh-scrolled);
   - the header's logo-teal ends exactly where the logo ends (--pdh-logo-end), so the logo's own teal box
     melts into the bar at every screen width and header size. */
(function () {
    'use strict';
    var root = document.documentElement, ticking = false;
    var nav = document.querySelector('.header .global-navigation');
    var logo = nav && nav.querySelector('.nav__logo img');

    function fitTeal() {
        if (!logo) return;
        var end = logo.getBoundingClientRect().right - nav.getBoundingClientRect().left;
        if (end > 0) nav.style.setProperty('--pdh-logo-end', Math.round(end) + 'px');
    }
    function update() {
        ticking = false;
        root.classList.toggle('pdh-scrolled', window.scrollY > 40);
    }
    window.addEventListener('scroll', function () {
        if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    window.addEventListener('resize', fitTeal);
    if (logo) {
        logo.addEventListener('load', fitTeal);
        logo.addEventListener('transitionend', fitTeal);  // the logo shrinks/grows with the compact header
        // keep it glued while the logo animates between sizes
        logo.addEventListener('transitionrun', function () {
            var start = performance.now();
            (function follow(now) { fitTeal(); if (now - start < 450) requestAnimationFrame(follow); })(start);
        });
    }
    update();
    fitTeal();
})();
