/* LUCUS: automatic pagination by measured, rendered element heights. */
(() => {
  "use strict";
  const root = document.querySelector("[data-lucus-reader]");
  if (!root) return;
  const source = root.querySelector("[data-lucus-source]");
  const output = root.querySelector("[data-lucus-pages]");
  const controls = root.querySelector("[data-lucus-controls]");
  const prev = root.querySelector("[data-lucus-previous]");
  const next = root.querySelector("[data-lucus-next]");
  const status = root.querySelector("[data-lucus-status]");
  const pagination = root.querySelector(".lucus__pagination");
  const continuous = root.querySelector("[data-lucus-continuous]");
  if (!source || !output || !controls) return;

  const desktop = window.matchMedia("(min-width: 900px)");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const originalBlocks = Array.from(source.children);
  // Only one copy of a fragment ID may exist in the active document.
  // Original IDs belong to the source in continuous/mobile mode, to the
  // rendered spread in paginated mode.
  const sourceAnchors = Array.from(source.querySelectorAll("[id]"))
    .map(element => ({ element, id: element.id }));
  function restoreSourceAnchors() {
    sourceAnchors.forEach(({ element, id }) => { element.id = id; });
  }
  function moveAnchorsToPages() {
    sourceAnchors.forEach(({ element }) => { element.removeAttribute("id"); });
  }
  let pages = [];
  let current = 0;
  let resizeJob = 0;

  function clearPages() {
    output.hidden = true;
    output.replaceChildren();
    source.hidden = false;
    restoreSourceAnchors();
    // On wide screens this remains available even when reading continuously.
    controls.hidden = !desktop.matches || originalBlocks.length < 2;
    pagination.hidden = true;
    pages = [];
  }

  function build() {
    clearPages();
    if (!desktop.matches || continuous.checked || originalBlocks.length < 2) return;
    // Keep pages within a reasonable reading height while honoring browser zoom.
    const target = Math.max(460, Math.min(790, Math.round(window.innerHeight * 0.72)));
    const measure = document.createElement("div");
    measure.className = "lucus__page-columns";
    measure.style.position = "absolute";
    measure.style.visibility = "hidden";
    measure.style.width = source.getBoundingClientRect().width + "px";
    measure.style.pointerEvents = "none";
    root.appendChild(measure);

    const columns = [];
    function newColumn() {
      const col = document.createElement("div");
      col.className = "lucus__page-column";
      measure.replaceChildren(col);
      columns.push([]);
      return col;
    }
    let col = newColumn();
    try {
      for (let i = 0; i < originalBlocks.length; i++) {
        const node = originalBlocks[i];
        const tag = node.tagName;
        // Headings should not be orphaned: measure them with their first paragraph.
        const group = [node];
        if (/^H[2-6]$/.test(tag) && i + 1 < originalBlocks.length) {
          group.push(originalBlocks[++i]);
        }
        const appendGroup = () => group.forEach(el => {
          const clone = el.cloneNode(true);
          // Avoid duplicate ID anchors in paginated content.
          clone.removeAttribute("id");
          clone.querySelectorAll("[id]").forEach(n => n.removeAttribute("id"));
          col.appendChild(clone);
        });
        appendGroup();
        if (col.getBoundingClientRect().height > target && columns[columns.length - 1].length) {
          group.forEach(() => col.lastElementChild.remove());
          col = newColumn();
          appendGroup();
        }
        columns[columns.length - 1].push(...group);
      }
    } finally {
      measure.remove();
    }

    for (let i = 0; i < columns.length; i += 2) {
      const page = document.createElement("section");
      page.className = "lucus__page";
      page.id = "lucus-seite-" + (i / 2 + 1);
      const heading = document.createElement("div");
      heading.className = "lucus__page-heading";
      heading.setAttribute("aria-hidden", "true");
      heading.innerHTML = "<span>De Rebus Humanis</span><span>Seite " + (i / 2 + 1) + "</span>";
      const spread = document.createElement("div");
      spread.className = "lucus__page-columns";
      for (const elements of columns.slice(i, i + 2)) {
        const column = document.createElement("div");
        column.className = "lucus__page-column";
        for (const el of elements) column.appendChild(el.cloneNode(true));
        spread.appendChild(column);
      }
      page.append(heading, spread);
      output.appendChild(page);
    }
    pages = Array.from(output.children);
    if (!pages.length) return;
    current = Math.min(current, pages.length - 1);
    moveAnchorsToPages();
    source.hidden = true;
    output.hidden = false;
    controls.hidden = false;
    pagination.hidden = pages.length <= 1;
    display();
    followFragment(false);
  }

  function display() {
    pages.forEach((page, i) => { page.hidden = i !== current; });
    prev.disabled = current === 0;
    next.disabled = current === pages.length - 1;
    status.textContent = "Seite " + (current + 1) + " von " + pages.length;
  }

  // Fragment links (including Kramdown heading IDs) should expose the
  // appropriate page before scrolling to the target.
  function followFragment(scroll) {
    if (output.hidden || !pages.length || !window.location.hash) return;
    let id;
    try { id = decodeURIComponent(window.location.hash.slice(1)); }
    catch (error) { return; }
    for (let index = 0; index < pages.length; index++) {
      const page = pages[index];
      const target = page.id === id ? page :
        Array.from(page.querySelectorAll("[id]")).find(el => el.id === id);
      if (!target) continue;
      if (current !== index) {
        current = index;
        display();
      }
      if (scroll) {
        window.requestAnimationFrame(() => target.scrollIntoView({
          block: "start",
          behavior: "auto"
        }));
      }
      return;
    }
  }

  function navigate(delta) {
    current = Math.max(0, Math.min(pages.length - 1, current + delta));
    display();
    root.scrollIntoView({block:"start",behavior:reduceMotion.matches ? "instant" : "smooth"});
  }

  prev.addEventListener("click", () => navigate(-1));
  next.addEventListener("click", () => navigate(1));
  continuous.addEventListener("change", build);
  window.addEventListener("hashchange", () => followFragment(true));
  function schedule() {
    window.clearTimeout(resizeJob);
    resizeJob = window.setTimeout(build, 180);
  }
  window.addEventListener("resize", schedule);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(schedule);
  build();
  followFragment(true);
})();
