(() => {
    const header = document.querySelector('header');
    if (!header) return;

    const movementThreshold = 8;
    const topThreshold = 20;
    const interactionPause = 600;
    let lastScrollY = Math.max(window.scrollY, 0);
    let ignoreScrollUntil = 0;
    let ticking = false;

    function keepHeaderOpenDuringInteraction() {
        header.classList.remove('header-hidden');
        lastScrollY = Math.max(window.scrollY, 0);
        ignoreScrollUntil = performance.now() + interactionPause;
    }

    function closeCategoryMenus() {
        document.querySelectorAll('.dropdown-content.show').forEach((dropdown) => {
            dropdown.classList.remove('show');
        });
        document.querySelectorAll('.category-btn.active').forEach((button) => {
            button.classList.remove('active');
        });
    }

    function updateHeader() {
        const currentScrollY = Math.max(window.scrollY, 0);
        const movement = currentScrollY - lastScrollY;

        if (performance.now() < ignoreScrollUntil) {
            lastScrollY = currentScrollY;
            ticking = false;
            return;
        }

        if (currentScrollY <= topThreshold) {
            header.classList.remove('header-hidden');
            lastScrollY = currentScrollY;
        } else if (Math.abs(movement) >= movementThreshold) {
            if (movement > 0) {
                header.classList.add('header-hidden');
                closeCategoryMenus();
            } else {
                header.classList.remove('header-hidden');
            }
            lastScrollY = currentScrollY;
        }

        ticking = false;
    }

    window.addEventListener('scroll', () => {
        if (!ticking) {
            window.requestAnimationFrame(updateHeader);
            ticking = true;
        }
    }, { passive: true });

    header.addEventListener('pointerdown', keepHeaderOpenDuringInteraction, { passive: true });
    header.addEventListener('click', keepHeaderOpenDuringInteraction);
})();
