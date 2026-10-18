/* LUCUS editorial pagination: enhanced desktop reading, continuous mobile/print fallback. */
(() => {
  "use strict";
  const root = document.querySelector("[data-lucus-reader]");
  if (!root) return;
  const pages = Array.from(root.querySelectorAll("[data-lucus-sheet]"));
  const controls = root.querySelector("[data-lucus-controls]");
  if (!controls || pages.length <= 1) return;

  const pagination = root.querySelector("[data-lucus-pagination]");
  const previous = root.querySelector("[data-lucus-previous]");
  const next = root.querySelector("[data-lucus-next]");
  const status = root.querySelector("[data-lucus-status]");
  const continuousInput = root.querySelector("[data-lucus-continuous]");
  const wideScreen = window.matchMedia("(min-width: 900px)");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const deepLink = /^#lucus-seite-(\\d+)$/.exec(window.location.hash);
  let current = deepLink ? Math.min(pages.length - 1, Math.max(0, Number(deepLink[1]) - 1)) : 0;

  function update() {
    const paged = wideScreen.matches && !continuousInput.checked;
    root.classList.add("lucus__reader--enhanced");
    controls.hidden = !wideScreen.matches;
    pagination.hidden = !paged;
    pages.forEach((page, index) => { page.hidden = paged && index !== current; });
    previous.disabled = current === 0;
    next.disabled = current === pages.length - 1;
    status.textContent = "Seite " + (current + 1) + " von " + pages.length;
  }

  function show(index) {
    current = Math.min(pages.length - 1, Math.max(0, index));
    update();
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#lucus-seite-" + (current + 1));
    }
    root.scrollIntoView({ block: "start", behavior: reducedMotion.matches ? "auto" : "smooth" });
  }

  previous.addEventListener("click", () => show(current - 1));
  next.addEventListener("click", () => show(current + 1));
  continuousInput.addEventListener("change", update);
  if (wideScreen.addEventListener) wideScreen.addEventListener("change", update);
  else wideScreen.addListener(update);
  update();
})();