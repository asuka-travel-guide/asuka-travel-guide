// related-slider.js
document.addEventListener("DOMContentLoaded", () => {
  const scroll = document.querySelector(".related-scroll");
  const slider = document.querySelector(".related-slider");
  if (!scroll || !slider) return;

  // 要素の複製（無限ループ用）
  [...slider.children].forEach((c) => slider.appendChild(c.cloneNode(true)));

  let x = 0,
    auto = true,
    speed = 0.4,
    drag = false,
    startX = 0,
    startPos = 0,
    v = 0,
    lastX = 0,
    lastT = 0,
    inertia = false,
    isMoved = false; // ドラッグとクリックの判別用

  let timerId = null;

  const limit = () => slider.scrollWidth / 2;

  function norm() {
    const l = limit();
    while (x > 0) x -= l;
    while (-x >= l) x += l;
  }

  function frame() {
    if (auto && !drag && !inertia) {
      x -= speed;
      norm();
    }
    if (inertia) {
      x += v;
      v *= 0.95; // 減衰率
      if (Math.abs(v) < 0.1) {
        inertia = false;
      }
    }
    norm();
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
    clearTimeout(timerId); // 自動再生再開タイマーをリセット
  }

  function move(px) {
    if (!drag) return;
    const now = performance.now();
    const diff = px - startX;

    // 5px以上動いたら「ドラッグ操作」とみなす
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

    // 2.5秒後に自動再生を再開（連続操作してもタイマーが重複しないように管理）
    timerId = setTimeout(() => {
      auto = true;
    }, 2500);
  }

  // --- イベント登録 ---


  // ブラウザ標準のドラッグ動作を抑止
  scroll.addEventListener("dragstart", (e) => e.preventDefault());

  // マウスイベント
  scroll.addEventListener("mousedown", (e) => down(e.clientX));
  window.addEventListener("mousemove", (e) => move(e.clientX));
  window.addEventListener("mouseup", up);

  // タッチイベント（window全体で移動・終了を拾う）
  scroll.addEventListener("touchstart", (e) => down(e.touches[0].clientX), {
    passive: true,
  });
  window.addEventListener(
    "touchmove",
    (e) => {
      if (drag) move(e.touches[0].clientX);
    },
    { passive: true }
  );
  window.addEventListener("touchend", up);

  // ドラッグ中の誤タップ防止（クリックイベントのキャンセル）
  scroll.addEventListener(
    "click",
    (e) => {
      if (isMoved) {
        e.preventDefault();
        e.stopPropagation();
      }
    },
    true
  );
});