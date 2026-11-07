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
    }
  });
})();
