// related-slider.js (複数スライダー共通対応版)
document.addEventListener("DOMContentLoaded", () => {
  const scrolls = document.querySelectorAll(".related-scroll");
  if (!scrolls.length) return;

  scrolls.forEach((scroll) => {
    const slider = scroll.querySelector(".related-slider");
    if (!slider) return;

    // 要素の二重複製を防止しつつ無限ループ用にクローン追加
    if (!slider.dataset.cloned) {
      const children = Array.from(slider.children);
      children.forEach((child) => slider.appendChild(child.cloneNode(true)));
      slider.dataset.cloned = "true";
    }

    let x = 0;
    let auto = true;
    const speed = 0.4;
    let drag = false;
    let startX = 0;
    let startPos = 0;
    let v = 0;
    let lastX = 0;
    let lastT = 0;
    let inertia = false;
    let isMoved = false;

    let timerId = null;

    const getLimit = () => slider.scrollWidth / 2;

    function norm() {
      const limit = getLimit();
      if (limit <= 0) return;
      while (x > 0) x -= limit;
      while (-x >= limit) x += limit;
    }

    function frame() {
      if (auto && !drag && !inertia) {
        x -= speed;
        norm();
      }
      if (inertia) {
        x += v;
        v *= 0.95;
        if (Math.abs(v) < 0.1) {
          inertia = false;
        }
        norm();
      }

      slider.style.transform = `translateX(${x}px)`;
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    function down(px) {
      drag = true;
      auto = false;
      inertia = false;
      isMoved = false;
      startX = px;
      startPos = x;
      lastX = px;
      lastT = performance.now();
      scroll.classList.add("dragging");
      clearTimeout(timerId);
    }

    function move(px) {
      if (!drag) return;
      const now = performance.now();
      const diff = px - startX;

      if (Math.abs(diff) > 5) {
        isMoved = true;
      }

      x = startPos + diff;
      v = ((px - lastX) / Math.max(1, now - lastT)) * 16;
      lastX = px;
      lastT = now;
    }

    function up() {
      if (!drag) return;
      drag = false;
      inertia = true;
      scroll.classList.remove("dragging");

      timerId = setTimeout(() => {
        auto = true;
      }, 2500);
    }

    // --- 各スライダーごとのイベント登録 ---
    scroll.addEventListener("dragstart", (e) => e.preventDefault());

    // マウス操作 (PC)
    scroll.addEventListener("mousedown", (e) => down(e.clientX));
    window.addEventListener("mousemove", (e) => {
      if (drag) move(e.clientX);
    });
    window.addEventListener("mouseup", up);

    // タッチ操作 (モバイル)
    scroll.addEventListener("touchstart", (e) => down(e.touches[0].clientX), {
      passive: true,
    });

    window.addEventListener(
      "touchmove",
      (e) => {
        if (drag) {
          e.preventDefault();
          move(e.touches[0].clientX);
        }
      },
      { passive: false }
    );

    window.addEventListener("touchend", up);

    // ドラッグ操作時の誤タップ防止
    scroll.addEventListener(
      "click",
      (e) => {
        if (isMoved) {
          e.preventDefault();
          e.stopPropagation();
          isMoved = false;
        }
      },
      true
    );
  });
});