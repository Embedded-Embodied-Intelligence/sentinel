/* Sentinel v2 (WP15, ADR-0033): the few behaviours HTMX does not cover. The theme switch applies
   at once and keeps the cookie the server reads; the rest is added per screen below. No library,
   no network beyond this site. */
(function () {
  "use strict";

  function setTheme(value) {
    document.documentElement.setAttribute("data-theme", value);
    document.cookie = "sentinel_theme=" + value + "; path=/; max-age=31536000; samesite=lax";
    document.querySelectorAll("[data-theme-set]").forEach(function (link) {
      if (link.getAttribute("data-theme-set") === value) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    });
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-theme-set]");
    if (link) {
      event.preventDefault();
      setTheme(link.getAttribute("data-theme-set"));
      return;
    }
    // A button that opens a panel in place (reject, adjust) and the panel's own cancel button.
    var toggle = event.target.closest("[data-toggle]");
    if (toggle) {
      var panel = document.getElementById(toggle.getAttribute("data-toggle"));
      if (!panel) return;
      var open = panel.hidden;
      panel.hidden = !open;
      document.querySelectorAll('[data-toggle="' + panel.id + '"][aria-expanded]').forEach(function (b) {
        b.setAttribute("aria-expanded", open ? "true" : "false");
      });
      if (open) {
        var first = panel.querySelector("input, select, textarea, button");
        if (first) first.focus();
      }
    }
  });

  // "Inny powód" reveals the text box with the microphone (section 8.4).
  document.addEventListener("change", function (event) {
    var radio = event.target;
    if (radio.name !== "reason") return;
    var form = radio.closest("form");
    var box = form && form.querySelector("[data-other-box]");
    if (box) box.hidden = !form.querySelector("[data-other]:checked");
  });
})();
