// Sentinel pages (WP9b, WP10; ADR-0025, ADR-0027). HTMX does the requests; this file does what a
// page must do by itself: form rows, the drawer, toasts, disclosures that close, live date and
// rule hints, the check-in's count of changes, the unsaved-changes bar, the "after tasks" picker,
// the chart's tooltip, and one request at a time from a form.
(function () {
  "use strict";
  let counter = 1000;
  const root = document.documentElement;
  const days = (root.dataset.weekdays || "").split(",");
  const months = (root.dataset.months || "").split(",");

  // ---- form rows
  function refreshCount(name) {
    const count = document.getElementById(name + "-count");
    const list = document.getElementById(name + "-list");
    if (count && list) count.textContent = "(" + list.querySelectorAll("[data-row]").length + ")";
  }

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-leave]")) leaving = true;
    const add = event.target.closest("[data-add-row]");
    if (add) {
      const name = add.getAttribute("data-add-row");
      const template = document.getElementById(name + "-template");
      const list = document.getElementById(name + "-list");
      if (!template || !list) return;
      counter += 1;
      const holder = document.createElement("div");
      holder.innerHTML = template.innerHTML.split("__i__").join(String(counter)).trim();
      const row = holder.firstElementChild;
      list.appendChild(row);
      if (window.htmx) window.htmx.process(row);
      const first = row.querySelector("input:not([type=hidden]), select, textarea");
      if (first) first.focus();
      refreshCount(name);
      countChanges();
      return;
    }
    const remove = event.target.closest("[data-remove-row]");
    if (remove) {
      const row = remove.closest("[data-row]");
      const section = row && row.closest("section");
      const list = row && row.parentElement;
      if (row) row.remove();
      const next = section && section.querySelector("[data-add-row]");
      if (next) next.focus();
      if (list && list.id) refreshCount(list.id.replace("-list", ""));
      countChanges();
      return;
    }
    const reveal = event.target.closest("[data-reveal]");
    if (reveal) {
      const panel = document.getElementById(reveal.getAttribute("data-reveal"));
      if (panel) {
        panel.hidden = !panel.hidden;
        reveal.setAttribute("aria-expanded", String(!panel.hidden));
        const first = !panel.hidden && panel.querySelector("button, a, input");
        if (first) first.focus();
      }
      return;
    }
    const show = event.target.closest("[data-reveal-field]");
    if (show) {
      const input = document.getElementById(show.getAttribute("data-reveal-field"));
      if (input) {
        const hidden = input.type === "password";
        input.type = hidden ? "text" : "password";
        show.textContent = hidden ? show.dataset.hide : show.dataset.show;
      }
      return;
    }
    const exit = event.target.closest("[data-exit-form]");
    if (exit) {
      // "Save and exit" sits outside the form, so that Enter in a field never means it.
      const form = document.getElementById(exit.getAttribute("data-exit-form"));
      if (form) {
        const action = document.createElement("input");
        action.type = "hidden";
        action.name = "action";
        action.value = "exit";
        form.prepend(action);
        form.requestSubmit();
      }
      return;
    }
    const closer = event.target.closest("[data-close-details]");
    if (closer) {
      const details = closer.closest("details");
      if (details) {
        details.open = false;
        details.querySelector("summary").focus();
      }
      return;
    }
    const closeToast = event.target.closest("[data-toast-close]");
    if (closeToast) {
      dismissToast(closeToast.closest("[data-toast]"));
      return;
    }
    if (event.target.closest("[data-drawer-open]")) {
      openDrawer();
      return;
    }
    if (event.target.closest("[data-drawer-close]")) closeDrawer();
    // A click outside closes an open popover cell.
    document.querySelectorAll("details.pop[open]").forEach(function (open) {
      if (!open.contains(event.target)) open.open = false;
    });
  });

  // ---- values that follow an input
  function echoDate(input) {
    const echo = document.querySelector('[data-echo-for="' + input.id + '"]');
    if (!echo) return;
    const value = input.value ? new Date(input.value + "T12:00:00") : null;
    if (!value || isNaN(value)) {
      echo.textContent = "";
      return;
    }
    const weekday = days[(value.getDay() + 6) % 7];
    echo.textContent = weekday + " " + value.getDate() + " " + months[value.getMonth()] + " " + value.getFullYear();
  }

  function checkRule() {
    const rule = document.querySelector("[data-deadline-rule]");
    if (!rule) return;
    const start = document.getElementById(rule.dataset.start);
    const deadline = document.getElementById(rule.dataset.deadline);
    rule.classList.remove("bad");
    rule.textContent = "";
    if (!start || !deadline || !start.value || !deadline.value) return;
    const span = (new Date(deadline.value) - new Date(start.value)) / 86400000;
    if (span < 0) {
      rule.classList.add("bad");
      rule.textContent = "✕ " + rule.dataset.bad;
      return;
    }
    const weeks = Math.max(1, Math.round(span / 7));
    const last = weeks % 10;
    const few = last >= 2 && last <= 4 && (weeks % 100 < 12 || weeks % 100 > 14);
    const word = weeks === 1 ? rule.dataset.one : few ? rule.dataset.few : rule.dataset.many;
    rule.textContent = "✓ " + rule.dataset.ok.replace("{weeks}", word.replace("{n}", weeks));
  }

  document.addEventListener("input", function (event) {
    const target = event.target;
    if (!target.matches) return;
    if (target.matches("input[type=range]")) {
      const number = document.getElementById(target.id + "-num");
      if (number) number.value = target.value;
    } else if (target.matches("input[data-range-for]")) {
      const range = document.getElementById(target.dataset.rangeFor);
      if (range) range.value = Math.min(99, Math.max(0, Number(target.value) || 0));
    } else if (target.matches("input[type=date]")) {
      echoDate(target);
      checkRule();
    } else if (target.matches("[data-crew-input]")) {
      summariseCrew(target.closest("details"));
    }
    countChanges();
    markUnsaved();
  });

  document.addEventListener("change", function (event) {
    if (event.target.matches && event.target.matches("[data-after-box]")) applyAfter(event.target);
    countChanges();
    markUnsaved();
  });

  // ---- the check-in's count of changes and the label of its button
  function changeCount(form) {
    let changes = form.querySelectorAll("#away-list [data-row], #grow-list [data-row], #new-list [data-row]").length;
    form.querySelectorAll("input[name^=msg_]:checked").forEach(function () {
      changes += 1;
    });
    form.querySelectorAll("fieldset.task-row").forEach(function (row) {
      const inputs = row.querySelectorAll("input[type=radio], input[type=range]");
      for (const input of inputs) {
        const moved = input.type === "radio" ? input.checked !== input.defaultChecked : input.value !== input.defaultValue;
        if (moved) {
          changes += 1;
          break;
        }
      }
    });
    return changes;
  }

  function countChanges() {
    const form = document.getElementById("checkin-form");
    if (!form) return;
    const changes = changeCount(form);
    const label = form.querySelector("[data-save-label]");
    const count = form.querySelector("[data-change-count]");
    if (!label) return;
    label.textContent = changes ? label.dataset.some : label.dataset.none;
    if (count) {
      const last = changes % 10;
      const few = last >= 2 && last <= 4 && (changes % 100 < 12 || changes % 100 > 14);
      const word = changes === 1 ? count.dataset.one : few ? count.dataset.few : count.dataset.many;
      count.textContent = changes ? word.replace("{n}", changes) : count.dataset.zero;
    }
  }

  // ---- leaving a half-filled form: the browser asks first
  let leaving = false;

  function hasUnsaved() {
    const bar = document.querySelector("[data-unsaved-bar]");
    if (bar && !bar.hidden) return true;
    const form = document.getElementById("checkin-form");
    if (!form) return false;
    const message = form.querySelector("#message");
    return changeCount(form) > 0 || Boolean(form.querySelector("[data-focus]")) || Boolean(message && message.value.trim());
  }

  window.addEventListener("beforeunload", function (event) {
    if (leaving || !hasUnsaved()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  window.addEventListener("pageshow", function () {
    leaving = false;
  });

  // ---- the bar of unsaved changes (project settings)
  function markUnsaved() {
    const bar = document.querySelector("[data-unsaved-bar]");
    if (!bar) return;
    const form = bar.closest("form");
    let dirty = false;
    form.querySelectorAll("input, select, textarea").forEach(function (field) {
      if (field.type === "hidden") return;
      if (field.type === "radio" || field.type === "checkbox") dirty = dirty || field.checked !== field.defaultChecked;
      else if (field.tagName === "SELECT") dirty = dirty || Array.from(field.options).some(function (o) { return o.selected !== o.defaultSelected; });
      else dirty = dirty || field.value !== field.defaultValue;
    });
    bar.hidden = !dirty;
  }

  document.addEventListener("reset", function () {
    setTimeout(markUnsaved);
  });

  // ---- the task table: people of a task and the tasks it comes after
  function summariseCrew(details) {
    if (!details) return;
    const parts = [];
    details.querySelectorAll("[data-crew-input]").forEach(function (input) {
      const n = parseInt(input.value, 10);
      if (n > 0) parts.push(n + " × " + input.dataset.role);
    });
    details.querySelector(".pop-value").textContent = parts.join(", ") || details.dataset.empty;
  }

  function buildAfter(details) {
    const body = details.querySelector("[data-after-body]");
    const hidden = details.querySelector("input[data-after-value]");
    const row = Number(details.dataset.row);
    const chosen = hidden.value.split(/[^0-9]+/).filter(Boolean).map(Number);
    body.textContent = "";
    document.querySelectorAll("input[name=task_name]").forEach(function (name, index) {
      if (index + 1 === row) return;
      const label = document.createElement("label");
      label.className = "check";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = String(index + 1);
      box.checked = chosen.includes(index + 1);
      box.setAttribute("data-after-box", "");
      label.appendChild(box);
      label.appendChild(document.createTextNode(" " + (index + 1) + ". " + (name.value || "—")));
      body.appendChild(label);
    });
  }

  function applyAfter(box) {
    const details = box.closest("details");
    const hidden = details.querySelector("input[data-after-value]");
    const boxes = details.querySelectorAll("[data-after-box]:checked");
    hidden.value = Array.from(boxes).map(function (b) { return b.value; }).join(", ");
    const names = Array.from(boxes).map(function (b) {
      return document.querySelectorAll("input[name=task_name]")[Number(b.value) - 1].value || b.value;
    });
    details.querySelector(".pop-value").textContent = names.join(", ") || details.dataset.empty;
  }

  document.addEventListener("toggle", function (event) {
    const details = event.target;
    if (!(details instanceof HTMLDetailsElement) || !details.open) return;
    if (details.matches("[data-after-picker]")) buildAfter(details);
    if (details.classList.contains("pop")) {
      document.querySelectorAll("details.pop[open]").forEach(function (open) {
        if (open !== details) open.open = false;
      });
    }
  }, true);

  // ---- toasts: one at a time, gone after 6 s (10 s with an action), paused on hover or focus
  function dismissToast(toast) {
    if (toast) toast.remove();
  }

  function startToast(toast) {
    let left = toast.hasAttribute("data-long") ? 10000 : 6000;
    let began = Date.now();
    let timer = setTimeout(function () { dismissToast(toast); }, left);
    function pause() {
      clearTimeout(timer);
      left -= Date.now() - began;
    }
    function resume() {
      began = Date.now();
      timer = setTimeout(function () { dismissToast(toast); }, Math.max(left, 1500));
    }
    toast.addEventListener("mouseenter", pause);
    toast.addEventListener("mouseleave", resume);
    toast.addEventListener("focusin", pause);
    toast.addEventListener("focusout", resume);
  }

  // ---- the drawer of the small-screen menu
  const FOCUSABLE = "a[href], button:not([disabled]), input, select, textarea";

  function openDrawer() {
    const drawer = document.getElementById("sidebar");
    const scrim = document.querySelector(".scrim");
    if (!drawer) return;
    drawer.classList.add("open");
    if (scrim) scrim.hidden = false;
    document.querySelector("[data-drawer-open]").setAttribute("aria-expanded", "true");
    const first = drawer.querySelector(FOCUSABLE);
    if (first) first.focus();
  }

  function closeDrawer() {
    const drawer = document.getElementById("sidebar");
    const scrim = document.querySelector(".scrim");
    const opener = document.querySelector("[data-drawer-open]");
    if (!drawer || !drawer.classList.contains("open")) return;
    drawer.classList.remove("open");
    if (scrim) scrim.hidden = true;
    if (opener) {
      opener.setAttribute("aria-expanded", "false");
      opener.focus();
    }
  }

  document.addEventListener("keydown", function (event) {
    const drawer = document.getElementById("sidebar");
    const opened = drawer && drawer.classList.contains("open");
    if (event.key === "Escape") {
      if (opened) closeDrawer();
      document.querySelectorAll("details.pop[open]").forEach(function (open) {
        open.open = false;
        open.querySelector("summary").focus();
      });
      hideTip();
    }
    if (event.key === "Tab" && opened) {
      const items = drawer.querySelectorAll(FOCUSABLE);
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  // ---- the chart: a tooltip and a highlighted row on hover or focus
  function hideTip() {
    document.querySelectorAll(".gantt .is-active").forEach(function (active) {
      active.classList.remove("is-active");
    });
    document.querySelectorAll(".gantt-tip").forEach(function (tip) {
      tip.hidden = true;
    });
  }

  function showTip(row, name) {
    const gantt = row.closest(".gantt");
    const tip = gantt.querySelector(".gantt-tip");
    hideTip();
    gantt.querySelectorAll('[data-row="' + row.dataset.row + '"]').forEach(function (part) {
      part.classList.add("is-active");
    });
    if (!name.dataset.tip) return;
    tip.textContent = name.dataset.tip;
    tip.hidden = false;
    const box = name.getBoundingClientRect();
    const below = box.bottom + tip.offsetHeight + 8 < window.innerHeight;
    tip.style.left = Math.max(8, Math.min(box.left, window.innerWidth - tip.offsetWidth - 8)) + "px";
    tip.style.top = (below ? box.bottom + 4 : box.top - tip.offsetHeight - 4) + "px";
  }

  function tipEvent(event) {
    if (!event.target.closest) return;
    const row = event.target.closest(".gantt [data-row]");
    if (!row) {
      if (event.type === "focusin") hideTip();
      return;
    }
    const name = row.closest(".gantt").querySelector('.gantt-names [data-row="' + row.dataset.row + '"]');
    if (name) showTip(row, name);
  }
  document.addEventListener("mouseover", tipEvent);
  document.addEventListener("focusin", tipEvent);
  document.addEventListener("mouseout", function (event) {
    if (event.target.closest && event.target.closest(".gantt [data-row]")) hideTip();
  });
  document.addEventListener("scroll", hideTip, true);

  function scrollGantt(scope) {
    // On a small screen the chart opens a week before today (docs/design/brief.md, 3.15).
    scope.querySelectorAll(".gantt-scroll[data-open-at]").forEach(function (box) {
      const svg = box.querySelector(".gantt-plot");
      if (svg) box.scrollLeft = (Number(box.dataset.openAt) / 100) * svg.getBoundingClientRect().width;
    });
  }

  // ---- one request at a time from a form: the submitter shows it is busy
  document.addEventListener("htmx:beforeRequest", function (event) {
    const form = event.detail.elt;
    if (!form.matches || !form.matches("form")) return;
    const submitter = event.detail.requestConfig && event.detail.requestConfig.triggeringEvent && event.detail.requestConfig.triggeringEvent.submitter;
    form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (button) {
      button.disabled = true;
      if (button === submitter) button.setAttribute("aria-busy", "true");
    });
    if (form.id === "checkin-form" || form.querySelector("[data-unsaved-bar]")) leaving = true;
  });
  document.addEventListener("htmx:afterRequest", function (event) {
    const form = event.detail.elt;
    if (!form.matches || !form.matches("form")) return;
    const xhr = event.detail.xhr;
    if (!(xhr && xhr.getResponseHeader("HX-Redirect"))) leaving = false;
    if (!form.isConnected) return;
    form.querySelectorAll("button[disabled], button[aria-busy]").forEach(function (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    });
  });

  // ---- after a page or a fragment arrives
  function arrive(scope) {
    if (scope !== document) {
      const alert = scope.querySelector && scope.querySelector("[data-focus]");
      if (alert) alert.focus();
    }
    if (scope.querySelectorAll) {
      scope.querySelectorAll("[data-toast]").forEach(startToast);
      scope.querySelectorAll("input[type=date]").forEach(echoDate);
      scrollGantt(scope);
    }
    checkRule();
    countChanges();
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    arrive(event.detail.target);
  });
  document.addEventListener("htmx:oobAfterSwap", function (event) {
    if (event.detail.target && event.detail.target.querySelectorAll) scrollGantt(event.detail.target);
  });
  arrive(document);
})();
