// Sentinel pages (WP9b, WP10; ADR-0025, ADR-0027). HTMX does the requests; this file does what a
// page must do by itself: form rows, the drawer, toasts, disclosures that close, live date and
// rule hints, the check-in's count of changes, the unsaved-changes bar, the "after tasks" picker,
// the chart's tooltip, one request at a time from a form, and (WP14) the tasks read from a
// message filling their rows and a recording for a message box.
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
      syncGrowth();
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

  function noteBeforeStart(input) {
    const note = document.querySelector("[data-before-start]");
    if (note && input.id === "date") note.hidden = !input.value || input.value >= note.dataset.beforeStart;
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
      savedAs(target.closest("fieldset.task-row"));
    } else if (target.matches("input[data-range-for]")) {
      const range = document.getElementById(target.dataset.rangeFor);
      if (range) range.value = Math.min(99, Math.max(0, Number(target.value) || 0));
      savedAs(target.closest("fieldset.task-row"));
    } else if (target.matches("input[type=date]")) {
      echoDate(target);
      checkRule();
      noteBeforeStart(target);
      if (target.id === "date") followDate(target);
      if (target.matches("[data-follow-date]")) target.dataset.edited = "1";
    } else if (target.matches("[data-crew-input]")) {
      summariseCrew(target.closest("details"));
    }
    countChanges();
    markUnsaved();
  });

  document.addEventListener("change", function (event) {
    if (event.target.matches && event.target.matches("[data-after-box]")) applyAfter(event.target);
    if (event.target.matches && event.target.matches("input[data-range-for]")) {
      // What the slider took is what will be saved: "150" reads 99 at once.
      const range = document.getElementById(event.target.dataset.rangeFor);
      if (range) event.target.value = range.value;
    }
    syncGrowth();
    countChanges();
    markUnsaved();
  });

  // ---- growth: a task marked as in progress in this check-in can grow too (QA-21)
  function syncGrowth() {
    // Since WP12 a task not started may grow too (a new estimate): every task listed is accepted.
  }

  // ---- a form not saved yet keeps what was typed across the language switch (WP12, B1): the
  // fields go to this tab's session storage on the switch and come back once, on the next page
  const KEPT = "sentinel.kept-form";
  document.addEventListener("click", function (event) {
    const link = event.target.closest && event.target.closest('a[href^="/lang/"]');
    const form = document.querySelector("form[data-keep-on-language]");
    if (!link || !form) return;
    const values = {};
    form.querySelectorAll("input, select, textarea").forEach(function (field) {
      if (!field.name || field.type === "hidden" || field.type === "file") return;
      values[field.name] = field.type === "checkbox" || field.type === "radio" ? field.checked : field.value;
    });
    try {
      sessionStorage.setItem(KEPT, JSON.stringify({ form: form.id, values: values }));
    } catch (error) {
      // without storage the form starts empty, as before
    }
  });

  function restoreKept() {
    let kept = null;
    try {
      kept = JSON.parse(sessionStorage.getItem(KEPT) || "null");
      sessionStorage.removeItem(KEPT);
    } catch (error) {
      return;
    }
    const form = kept && document.getElementById(kept.form);
    if (!form) return;
    form.querySelectorAll("input, select, textarea").forEach(function (field) {
      if (!(field.name in kept.values) || field.type === "hidden") return;
      if (field.type === "checkbox" || field.type === "radio") field.checked = kept.values[field.name];
      else field.value = kept.values[field.name];
    });
    const more = form.querySelector("details");
    if (more && Object.keys(kept.values).length) more.open = more.open || more.querySelector("input:not([type=hidden])") !== null && Array.from(more.querySelectorAll("input")).some(function (f) { return f.value && f.value !== f.defaultValue; });
  }

  // ---- a name near its length limit says how much fits (WP12, B18: names were cut silently)
  function countCharacters(input) {
    const max = Number(input.getAttribute("maxlength"));
    if (!max || max < 60 || input.type === "hidden") return;
    let note = input.nextElementSibling;
    if (!note || !note.matches("[data-char-count]")) {
      note = document.createElement("span");
      note.className = "caption char-count";
      note.setAttribute("data-char-count", "");
      note.setAttribute("aria-live", "polite");
      input.insertAdjacentElement("afterend", note);
    }
    const n = input.value.length;
    note.hidden = n < max - 20;
    const template = n >= max ? root.dataset.counterFull : root.dataset.counter;
    note.textContent = (template || "{n}/{max}").split("{n}").join(n).split("{max}").join(max);
  }

  document.addEventListener("input", function (event) {
    const field = event.target;
    if (!field.matches) return;
    if (field.matches("input[maxlength]")) countCharacters(field);
    // A field's error goes once it is filled in (WP12, B21: "Podaj nazwę projektu" stayed).
    if (field.matches("[aria-invalid=true]") && field.value.trim()) {
      field.removeAttribute("aria-invalid");
      const error = field.id && document.getElementById(field.id + "-error");
      if (error) error.hidden = true;
    }
  });

  // ---- Enter in a field presses its own button, not the form's first one (WP12, B11: Enter in
  // the role field pressed "fewer" of the first role and cleared the field)
  document.addEventListener("keydown", function (event) {
    const field = event.target;
    if (event.key !== "Enter" || !field.matches || !field.matches("input[data-enter]")) return;
    const button = field.form && field.form.querySelector('button[value="' + field.dataset.enter + '"]');
    if (!button) return;
    event.preventDefault();
    button.click();
  });

  // ---- progress is kept in whole days: what a share will be saved as (WP12, B13)
  function savedAs(row) {
    if (!row || !row.dataset.units) return;
    const hint = row.querySelector("[data-saved-as]");
    const range = row.querySelector("input[type=range]");
    if (!hint || !range) return;
    const total = Number(row.dataset.units);
    const unit = Number(row.dataset.unit) || 1;
    const typed = Number(range.value);
    const units = Math.floor((typed / 100) * total + 0.5 + 1e-9);
    const saved = Math.round((100 * units) / total);
    const number = function (value) {
      return (Math.round(value * 10) / 10).toLocaleString(root.lang || "en");
    };
    const text = saved === typed ? hint.dataset.plain : hint.dataset.template;
    hint.textContent = text
      .replace("{typed}", typed)
      .replace("{saved}", saved)
      .replace("{done}", number(units / unit))
      .replace("{total}", number(total / unit));
  }

  // ---- "finished on" follows the report's date until it is changed by hand (WP12, B16)
  function followDate(input) {
    const form = input.closest("form");
    if (!form || !input.value) return;
    form.querySelectorAll("input[data-follow-date]").forEach(function (finish) {
      if (finish.dataset.edited !== "1") finish.value = input.value;
    });
  }

  // ---- the check-in's count of changes and the label of its button: a task row counts when it
  // differs from the saved state, which a page shown again after a refused save keeps (B12)
  function changeCount(form) {
    let changes = form.querySelectorAll("#away-list [data-row], #grow-list [data-row], #new-list [data-row]").length;
    // A task read from a message is counted by its row, which it fills (WP14).
    form.querySelectorAll("input[name^=msg_]:not([name=msg_task]):checked").forEach(function () {
      changes += 1;
    });
    form.querySelectorAll("fieldset.task-row").forEach(function (row) {
      const status = row.querySelector("input[type=radio]:checked");
      const range = row.querySelector("input[type=range]");
      if (row.dataset.savedStatus !== undefined && status) {
        const moved = status.value !== row.dataset.savedStatus ||
          (status.value === "in_progress" && range && range.value !== row.dataset.savedPercent);
        if (moved) changes += 1;
        return;
      }
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

  // A report being saved is not left without a word (WP12, B10): Back during the request.
  let saving = false;
  document.addEventListener("htmx:beforeRequest", function (event) {
    if (event.target.id === "checkin-form") saving = true;
  });
  document.addEventListener("htmx:afterRequest", function (event) {
    if (event.target.id !== "checkin-form") return;
    saving = false;
    const xhr = event.detail && event.detail.xhr;
    if (xhr && (xhr.getResponseHeader("HX-Redirect") || xhr.getResponseHeader("HX-Location"))) leaving = true;
  });

  window.addEventListener("beforeunload", function (event) {
    if (leaving || (!saving && !hasUnsaved())) return;
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

  // ---- a task read from a message fills its row of the check-in (WP14): ticking it, or choosing
  // it in a question, sets the row's status, share, finish and start; unticking it puts back what
  // the row had
  function taskRow(key) {
    return document.querySelector('#checkin-form fieldset.task-row[data-task="' + CSS.escape(key) + '"]');
  }

  function rowState(row) {
    const status = row.querySelector("input[type=radio]:checked");
    const value = function (selector) {
      const field = row.querySelector(selector);
      return field ? field.value : "";
    };
    return {
      status: status ? status.value : "",
      percent: value("input[type=range]"),
      finish: value("input[name^=finish_]"),
      start: value("input[name^=start_]"),
    };
  }

  function setRow(row, state) {
    const radio = row.querySelector('input[type=radio][value="' + state.status + '"]');
    if (radio && !radio.disabled) {
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (state.percent !== null && state.percent !== undefined && state.percent !== "") {
      row.querySelectorAll("input[type=range], input[data-range-for]").forEach(function (field) {
        field.value = state.percent;
      });
      savedAs(row);
    }
    const finish = row.querySelector("input[name^=finish_]");
    if (finish && state.finish) {
      finish.value = state.finish;
      finish.dataset.edited = "1";
      echoDate(finish);
    }
    const start = row.querySelector("input[name^=start_]");
    if (start) {
      start.value = state.start || "";
      const more = start.closest("details");
      if (more && state.start) more.open = true;
      echoDate(start);
    }
    const hidden = row.closest("details.more-tasks");
    if (hidden) hidden.open = true;
  }

  function fillRow(key, report) {
    const row = key && taskRow(key);
    if (!row) return;
    if (report) {
      if (!row.dataset.beforeMessage) row.dataset.beforeMessage = JSON.stringify(rowState(row));
      const percent = report.status === "in_progress" ? Math.round(report.percent || 0) : null;
      setRow(row, { status: report.status, percent: percent, finish: report.finish, start: report.start });
      row.classList.add("from-message");
    } else if (row.dataset.beforeMessage) {
      setRow(row, JSON.parse(row.dataset.beforeMessage));
      delete row.dataset.beforeMessage;
      row.classList.remove("from-message");
    }
  }

  function applyTaskItem(field) {
    if (field.tagName === "SELECT") {
      Array.from(field.options).forEach(function (option) {
        if (option.value && !option.selected) fillRow(option.dataset.taskItem, null);
      });
      const chosen = field.selectedOptions[0];
      if (chosen && chosen.value) fillRow(chosen.dataset.taskItem, JSON.parse(chosen.value));
    } else {
      fillRow(field.dataset.taskItem, field.checked ? JSON.parse(field.value) : null);
    }
  }

  document.addEventListener("change", function (event) {
    if (event.target.matches && event.target.matches("[name=msg_task]")) applyTaskItem(event.target);
  });

  // ---- a recording for a message box (WP14, ADR-0031): the microphone shows only where the
  // browser can record; the audio goes to the server, which has Groq's Whisper write it out and
  // keeps neither the audio nor the text; the text goes into the box to be read and corrected.
  // Nothing goes to the AI until the person processes the message.
  const RECORDING_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];

  function canRecord() {
    return Boolean(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }

  function csrfToken() {
    try {
      return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRF-Token"] || "";
    } catch (error) {
      return "";
    }
  }

  function clock(seconds) {
    const whole = Math.floor(seconds);
    return Math.floor(whole / 60) + ":" + String(whole % 60).padStart(2, "0");
  }

  function setupVoice(box) {
    if (box.dataset.ready || !canRecord()) return; // without it the box is for typing only
    box.dataset.ready = "1";
    box.hidden = false;
    const start = box.querySelector("[data-voice-start]");
    const stop = box.querySelector("[data-voice-stop]");
    const live = box.querySelector("[data-voice-live]");
    const timer = box.querySelector("[data-voice-timer]");
    const status = box.querySelector("[data-voice-status]");
    const limit = Number(box.dataset.voiceLimit) || 90;
    let recorder = null;
    let stream = null;
    let chunks = [];
    let began = 0;
    let ticking = null;
    let cutoff = null;
    let atLimit = false;
    const say = function (text, bad) {
      status.textContent = text || "";
      status.classList.toggle("is-bad", Boolean(bad));
    };
    const release = function () {
      clearInterval(ticking);
      clearTimeout(cutoff);
      if (stream) stream.getTracks().forEach(function (track) { track.stop(); });
      stream = null;
      live.hidden = true;
      start.hidden = false;
    };
    const finish = function () {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    };
    async function send() {
      const seconds = (Date.now() - began) / 1000;
      const blob = new Blob(chunks, { type: (recorder && recorder.mimeType) || "audio/webm" });
      chunks = [];
      release();
      start.disabled = true;
      start.setAttribute("aria-busy", "true");
      say(box.dataset.msgSending);
      try {
        const response = await fetch(box.dataset.voiceUrl, {
          method: "POST",
          body: blob,
          credentials: "same-origin",
          headers: {
            "Content-Type": blob.type.split(";")[0] || "audio/webm",
            "X-CSRF-Token": csrfToken(),
            "X-Recording-Seconds": seconds.toFixed(1),
          },
        });
        let data = {};
        try {
          data = await response.json();
        } catch (error) {
          data = {};
        }
        if (!response.ok || typeof data.text !== "string") {
          say(data.error || box.dataset.msgFailed, true);
          return;
        }
        const field = document.getElementById(box.dataset.voiceTarget);
        if (field) {
          field.value = field.value.trim() ? field.value.trim() + "\n" + data.text : data.text;
          field.dispatchEvent(new Event("input", { bubbles: true }));
          field.focus();
        }
        say((atLimit ? box.dataset.msgLimit + " " : "") + box.dataset.msgDone);
      } catch (error) {
        say(box.dataset.msgFailed, true);
      } finally {
        start.disabled = false;
        start.removeAttribute("aria-busy");
      }
    }
    start.addEventListener("click", async function () {
      say("");
      start.disabled = true;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (error) {
        start.disabled = false;
        const missing = error && (error.name === "NotFoundError" || error.name === "OverconstrainedError");
        say(missing ? box.dataset.msgNoMic : box.dataset.msgDenied, true);
        return;
      }
      const type = RECORDING_TYPES.find(function (candidate) { return MediaRecorder.isTypeSupported(candidate); });
      try {
        recorder = new MediaRecorder(stream, type ? { mimeType: type, audioBitsPerSecond: 32000 } : {});
      } catch (error) {
        release();
        start.disabled = false;
        say(box.dataset.msgFailed, true);
        return;
      }
      chunks = [];
      atLimit = false;
      recorder.addEventListener("dataavailable", function (event) {
        if (event.data && event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("stop", send);
      recorder.start(1000);
      began = Date.now();
      start.disabled = false;
      start.hidden = true;
      live.hidden = false;
      timer.textContent = clock(0);
      say(box.dataset.msgRecording);
      stop.focus();
      ticking = setInterval(function () { timer.textContent = clock((Date.now() - began) / 1000); }, 250);
      cutoff = setTimeout(function () {
        atLimit = true;
        finish();
      }, limit * 1000);
    });
    stop.addEventListener("click", finish);
  }

  // ---- after a page or a fragment arrives
  function arrive(scope) {
    if (scope !== document) {
      const alert = scope.querySelector && scope.querySelector("[data-focus]");
      // A row just added takes the focus (WP12 test: the new row of the task table did not).
      const added = !alert && scope.querySelector && scope.querySelector("[autofocus]");
      if (alert) alert.focus();
      else if (added) added.focus();
    }
    if (scope.querySelectorAll) {
      scope.querySelectorAll("[data-toast]").forEach(startToast);
      scope.querySelectorAll("input[type=date]").forEach(echoDate);
      scope.querySelectorAll("fieldset.task-row").forEach(savedAs);
      scrollGantt(scope);
    }
    // A job's result replaces the job (outerHTML), so its swap names the element it removed: a
    // review just read and a microphone are found in the page, and each is handled once (WP14).
    document.querySelectorAll("[data-voice]").forEach(setupVoice);
    document.querySelectorAll("[data-fresh-review]").forEach(function (review) {
      review.removeAttribute("data-fresh-review");
      review.querySelectorAll("input[name=msg_task]:checked").forEach(applyTaskItem);
    });
    checkRule();
    syncGrowth();
    countChanges();
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    arrive(event.detail.target);
  });
  document.addEventListener("htmx:oobAfterSwap", function (event) {
    if (event.detail.target && event.detail.target.querySelectorAll) scrollGantt(event.detail.target);
  });
  restoreKept();
  arrive(document);
})();
