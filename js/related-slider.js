document.addEventListener("DOMContentLoaded", () => {

    const slider = document.querySelector(".related-slider");
    const scroll = document.querySelector(".related-scroll");

    if (!slider || !scroll) return;

    /*==========================================
        カード複製（HTMLはそのまま）
    ==========================================*/

    [...slider.children].forEach(card => {
        slider.appendChild(card.cloneNode(true));
    });

    /*==========================================
        自動スクロール
    ==========================================*/

    let auto = true;
    const speed = 0.4;

    function animate() {

        if (auto) {

            scroll.scrollLeft += speed;

            if (scroll.scrollLeft >= slider.scrollWidth / 2) {
                scroll.scrollLeft = 0;
            }

        }

        requestAnimationFrame(animate);

    }

    animate();

    /*==========================================
        PC ドラッグ
    ==========================================*/

    let isDown = false;
    let startX;
    let startScrollLeft;

    scroll.addEventListener("mousedown", (e) => {

        auto = false;
        isDown = true;

        startX = e.pageX;
        startScrollLeft = scroll.scrollLeft;

        scroll.style.cursor = "grabbing";

    });

    window.addEventListener("mousemove", (e) => {

        if (!isDown) return;

        const walk = e.pageX - startX;

        scroll.scrollLeft = startScrollLeft - walk;

    });

    window.addEventListener("mouseup", () => {

        if (!isDown) return;

        isDown = false;
        scroll.style.cursor = "";

        setTimeout(() => {
            auto = true;
        }, 1000);

    });

    /*==========================================
        スマホ スワイプ
    ==========================================*/

    let touchStartX = 0;
    let touchStartScroll = 0;

    scroll.addEventListener("touchstart", (e) => {

        auto = false;

        touchStartX = e.touches[0].clientX;
        touchStartScroll = scroll.scrollLeft;

    }, { passive: true });

    scroll.addEventListener("touchmove", (e) => {

        const move = e.touches[0].clientX - touchStartX;

        scroll.scrollLeft = touchStartScroll - move;

    }, { passive: true });

    scroll.addEventListener("touchend", () => {

        setTimeout(() => {
            auto = true;
        }, 1000);

    });

});