// Sentinel pages (WP9b, ADR-0025): adding and removing form rows, the value of share-done
// sliders and moving the focus to a refused form's message. HTMX does everything else.
(function () {
  "use strict";
  let counter = 1000;

  document.addEventListener("click", function (event) {
    const add = event.target.closest("[data-add-row]");
    if (add) {
      const name = add.getAttribute("data-add-row");
      const template = document.getElementById(name + "-template");
      const list = document.getElementById(name + "-list");
      if (!template || !list) return;
      counter += 1;
      const html = template.innerHTML.split("__i__").join(String(counter));
      const holder = document.createElement("div");
      holder.innerHTML = html.trim();
      const row = holder.firstElementChild;
      list.appendChild(row);
      if (window.htmx) window.htmx.process(row);
      const first = row.querySelector("input:not([type=hidden]), select, textarea");
      if (first) first.focus();
      return;
    }
    const remove = event.target.closest("[data-remove-row]");
    if (remove) {
      const row = remove.closest("[data-row]");
      const section = row && row.closest("section");
      if (row) row.remove();
      const next = section && section.querySelector("[data-add-row]");
      if (next) next.focus();
    }
  });

  document.addEventListener("input", function (event) {
    const slider = event.target;
    if (slider.matches && slider.matches("input[type=range]")) {
      const out = document.getElementById(slider.id + "-out");
      if (out) out.value = slider.value + " %";
    }
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    const alert = event.detail.target.querySelector && event.detail.target.querySelector("[data-focus]");
    if (alert) alert.focus();
  });
})();
