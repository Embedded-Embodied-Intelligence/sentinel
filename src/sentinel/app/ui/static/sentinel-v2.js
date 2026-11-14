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
        var first = panel.querySelector("input:not([type=hidden]), select, textarea, button");
        if (first) first.focus();
      }
    }
  });

  // A link that opens a panel elsewhere on the page and brings it into view ("Dodaj ręcznie").
  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-open]");
    if (!opener) return;
    var panel = document.getElementById(opener.getAttribute("data-open"));
    if (!panel) return;
    event.preventDefault();
    panel.hidden = false;
    document.querySelectorAll('[data-toggle="' + panel.id + '"][aria-expanded]').forEach(function (b) {
      b.setAttribute("aria-expanded", "true");
    });
    panel.scrollIntoView({ block: "start" });
    var first = panel.querySelector("input:not([type=hidden]), select, textarea, button");
    if (first) first.focus({ preventScroll: true });
  });

  // The calendar link (section 8.9): shown with this page's own address, copied on request.
  document.querySelectorAll("[data-origin-fix]").forEach(function (input) {
    try {
      var url = new URL(input.value);
      input.value = window.location.origin + url.pathname + url.search;
    } catch (e) { /* keep the server's address */ }
  });
  document.addEventListener("click", function (event) {
    var printer = event.target.closest("[data-print]");
    if (printer) { window.print(); return; }
    var button = event.target.closest("[data-copy]");
    if (!button) return;
    var input = document.getElementById(button.getAttribute("data-copy"));
    if (!input) return;
    var status = button.parentNode.querySelector("[data-copy-status]");
    var done = function () { if (status) status.textContent = button.getAttribute("data-copied"); };
    input.select();
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(input.value).then(done, function () { document.execCommand("copy"); done(); });
    } else {
      document.execCommand("copy");
      done();
    }
  });

  // A dot of "Szansa w czasie" opens its entry of the log as it scrolls to it (section 8.6).
  document.addEventListener("click", function (event) {
    var dot = event.target.closest && event.target.closest("[data-open-entry]");
    if (!dot) return;
    var entry = document.getElementById(dot.getAttribute("data-open-entry"));
    var details = entry && entry.querySelector("details");
    if (details) details.open = true;
  });

  // The fields of a panel inside a form that are not the form's own (the per-task form in the
  // report) do not recompute what the form shows.
  document.querySelectorAll("[data-quiet]").forEach(function (panel) {
    panel.addEventListener("change", function (event) { event.stopPropagation(); });
  });

  // "Inny powód" reveals the text box with the microphone (section 8.4).
  document.addEventListener("change", function (event) {
    var radio = event.target;
    if (radio.name !== "reason") return;
    var form = radio.closest("form");
    var box = form && form.querySelector("[data-other-box]");
    if (box) box.hidden = !form.querySelector("[data-other]:checked");
  });

  // ---- the report (section 8.3)

  function changed(element) {
    var form = element && element.closest ? element.closest("form") : null;
    if (form) form.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function insertAt(box, text) {
    var start = box.selectionStart, end = box.selectionEnd;
    var before = box.value.slice(0, start);
    if (before && !/\s$/.test(before)) text = " " + text;
    box.value = before + text + box.value.slice(end);
    var caret = before.length + text.length;
    box.focus();
    box.setSelectionRange(caret, caret);
    box.dispatchEvent(new Event("input", { bubbles: true }));
  }

  document.addEventListener("click", function (event) {
    var hint = event.target.closest("[data-hint]");
    if (hint) {
      var box = hint.closest("form").querySelector("textarea");
      if (box) insertAt(box, hint.getAttribute("data-hint"));
      return;
    }
    var all = event.target.closest("[data-tick-all]");
    if (all) {
      var form = all.closest("form");
      form.querySelectorAll("[data-card] input[type=checkbox]").forEach(function (c) { c.checked = true; });
      changed(all);
      return;
    }
    var remove = event.target.closest("[data-remove-card]");
    if (remove) {
      var card = remove.closest("[data-card]");
      var owner = card.closest("form");
      card.remove();
      if (owner) owner.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    var planned = event.target.closest("[data-planned]");
    if (planned) {
      var used = planned.closest("form").querySelector("[data-planned-used]");
      if (used) used.value = "1";
    }
  });

  // A card's ✎ fields rewrite the report its checkbox carries.
  document.addEventListener("change", function (event) {
    var input = event.target;
    var name = input.getAttribute && input.getAttribute("data-edit");
    if (!name) return;
    var box = document.getElementById(input.getAttribute("data-for"));
    if (!box) return;
    var report = JSON.parse(box.value);
    if (input.type === "number") {
      var number = parseFloat(input.value);
      if (isNaN(number)) return;
      report[name] = name === "duration" ? Math.max(1, Math.round(number)) : number;
    } else {
      report[name] = input.value || null;
    }
    box.value = JSON.stringify(report);
    box.checked = true;
  });

  document.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    if (!target || !target.closest) return;
    var group = target.closest("[data-cards]") || (target.matches && target.matches("[data-cards]") ? target : null);
    if (!group) return;
    if (group.querySelector("[data-cards-loaded]")) {
      var form = group.closest("form");
      var empty = form && form.querySelector("[data-cards-empty]");
      if (empty) empty.hidden = true;
      document.body.dispatchEvent(new Event("cards"));
    }
  });

  // ---- the voice component (section 9)

  var CAP_S = 300, WARN_S = 270, PREVIEW_MS = 3000;
  var active = null;

  function csrf() {
    try { return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRF-Token"] || ""; }
    catch (e) { return ""; }
  }

  function clock(seconds) {
    var s = Math.floor(seconds);
    return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }

  function send(rec, blob, preview) {
    var url = rec.url + (rec.url.indexOf("?") < 0 ? "?" : "&") + (preview ? "preview=1" : "preview=0");
    return fetch(url, {
      method: "POST",
      body: blob,
      credentials: "same-origin",
      headers: {
        "Content-Type": blob.type || "audio/webm",
        "X-CSRF-Token": csrf(),
        "X-Recording-Seconds": String(Math.round((Date.now() - rec.began) / 100) / 10)
      }
    }).then(function (response) {
      return response.json().then(function (body) { return { ok: response.ok, status: response.status, body: body }; });
    });
  }

  function mirror(rec) {
    rec.ghost.textContent = "";
    rec.ghost.appendChild(document.createTextNode(rec.before));
    var span = document.createElement("span");
    span.className = "voice-preview";
    span.textContent = rec.preview ? (rec.before && !/\s$/.test(rec.before) ? " " : "") + rec.preview : " ";
    rec.ghost.appendChild(span);
    rec.ghost.appendChild(document.createTextNode(rec.after));
  }

  function setStatus(rec, key) {
    rec.status.textContent = key ? rec.status.getAttribute("data-" + key) || key : "";
  }

  function finish(rec, keep) {
    clearInterval(rec.timer);
    clearInterval(rec.ticker);
    if (rec.audio) rec.audio.close();
    rec.stream.getTracks().forEach(function (track) { track.stop(); });
    rec.panel.hidden = true;
    rec.ghost.hidden = true;
    rec.box.hidden = false;
    rec.start.hidden = false;
    active = null;
    if (!keep) {
      rec.box.value = rec.before + rec.after;
      setStatus(rec, "");
      rec.box.focus();
    }
  }

  function accept(rec) {
    if (rec.done) return;
    rec.done = true;
    rec.recorder.onstop = function () {
      var blob = new Blob(rec.chunks, { type: rec.recorder.mimeType || "audio/webm" });
      finish(rec, true);
      rec.box.value = rec.before + rec.after;
      setStatus(rec, "writing");
      send(rec, blob, false).then(function (result) {
        if (!result.ok || !result.body.text) {
          rec.status.textContent = (result.body && result.body.error) || rec.status.getAttribute("data-failed");
          return;
        }
        var text = result.body.text.trim();
        var spacer = rec.before && !/\s$/.test(rec.before) ? " " : "";
        rec.box.value = rec.before + spacer + text + rec.after;
        var caret = (rec.before + spacer + text).length;
        rec.box.focus();
        rec.box.setSelectionRange(caret, caret);
        rec.box.dispatchEvent(new Event("input", { bubbles: true }));
        setStatus(rec, "done");
      }).catch(function () { setStatus(rec, "failed"); });
    };
    rec.recorder.stop();
  }

  function cancel(rec) {
    if (rec.done) return;
    rec.done = true;
    rec.recorder.onstop = null;
    try { rec.recorder.stop(); } catch (e) { /* already stopped */ }
    finish(rec, false);
  }

  function previewTick(rec) {
    if (rec.inflight || rec.done || !rec.chunks.length) return;
    rec.inflight = true;
    var blob = new Blob(rec.chunks, { type: rec.recorder.mimeType || "audio/webm" });
    send(rec, blob, true).then(function (result) {
      rec.inflight = false;
      if (rec.done) return;
      if (result.ok && result.body.text) {
        rec.preview = result.body.text.trim();
        mirror(rec);
        if (rec.status.textContent === rec.status.getAttribute("data-preview-off")) setStatus(rec, "");
      } else {
        setStatus(rec, "preview-off");
      }
    }).catch(function () { rec.inflight = false; if (!rec.done) setStatus(rec, "preview-off"); });
  }

  function startRecording(button) {
    if (active) return;
    var root = button.closest("[data-voice-box]");
    var box = root.querySelector("textarea");
    var status = root.querySelector("[data-voice-status]");
    if (!navigator.mediaDevices || !window.MediaRecorder) { status.textContent = status.getAttribute("data-failed"); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var type = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"].find(function (t) {
        return MediaRecorder.isTypeSupported(t);
      });
      var recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      var ghost = root.querySelector("[data-voice-ghost]");
      if (!ghost) {
        ghost = document.createElement("div");
        ghost.className = "input voice-ghost";
        ghost.setAttribute("data-voice-ghost", "");
        ghost.setAttribute("aria-hidden", "true");
        box.parentNode.insertBefore(ghost, box.nextSibling);
      }
      var rec = {
        url: button.getAttribute("data-voice-url"), box: box, status: status, ghost: ghost,
        panel: root.querySelector("[data-voice-rec]"), start: button, stream: stream,
        recorder: recorder, chunks: [], began: Date.now(), inflight: false, done: false,
        before: box.value.slice(0, box.selectionStart), after: box.value.slice(box.selectionEnd),
        preview: "", audio: null
      };
      active = rec;
      recorder.ondataavailable = function (e) { if (e.data && e.data.size) rec.chunks.push(e.data); };
      recorder.start(1000);
      rec.panel.hidden = false;
      button.hidden = true;
      ghost.style.minHeight = box.offsetHeight + "px";
      box.hidden = true;
      ghost.hidden = false;
      mirror(rec);
      setStatus(rec, "");
      var time = rec.panel.querySelector("[data-voice-time]");
      var level = rec.panel.querySelector("[data-voice-level]");
      try {
        var Context = window.AudioContext || window.webkitAudioContext;
        rec.audio = new Context();
        var analyser = rec.audio.createAnalyser();
        analyser.fftSize = 512;
        rec.audio.createMediaStreamSource(stream).connect(analyser);
        var data = new Uint8Array(analyser.fftSize);
        rec.ticker = setInterval(function () {
          analyser.getByteTimeDomainData(data);
          var peak = 0;
          for (var i = 0; i < data.length; i++) peak = Math.max(peak, Math.abs(data[i] - 128));
          var value = Math.min(100, Math.round(peak / 1.28));
          level.firstElementChild.style.width = value + "%";
          level.setAttribute("aria-valuenow", String(value));
        }, 120);
      } catch (e) { rec.audio = null; }
      var lastPreview = Date.now();
      rec.timer = setInterval(function () {
        var seconds = (Date.now() - rec.began) / 1000;
        time.textContent = clock(seconds);
        if (seconds >= WARN_S && seconds < WARN_S + 1) setStatus(rec, "cap-soon");
        if (seconds >= CAP_S) { accept(rec); return; }
        if (Date.now() - lastPreview >= PREVIEW_MS) { lastPreview = Date.now(); previewTick(rec); }
      }, 250);
      rec.panel.querySelector("[data-voice-accept]").onclick = function () { accept(rec); };
      rec.panel.querySelector("[data-voice-cancel]").onclick = function () { cancel(rec); };
      rec.panel.querySelector("[data-voice-accept]").focus();
    }).catch(function () { status.textContent = status.getAttribute("data-denied"); });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-voice-start]");
    if (button) startRecording(button);
  });

  document.addEventListener("keydown", function (event) {
    if (!active) return;
    if (event.key === "Enter") { event.preventDefault(); accept(active); }
    else if (event.key === "Escape") { event.preventDefault(); cancel(active); }
  });

  // ---- the "Dowód" panel (v3 spec section 2): a modal dialog from the right, so the page
  // behind is inert (focus stays inside), Esc or ✕ closes it and focus returns to the point.
  var dowod = document.getElementById("dowod");
  var opener = null;

  function showDowod() {
    if (!dowod.open) dowod.showModal();
    var close = dowod.querySelector("[data-dowod-close]");
    if (close) close.focus();
    dowod.querySelector(".dowod-body").scrollTop = 0;
  }

  if (dowod) {
    if (dowod.hasAttribute("data-open")) {  // ?dowod=D14 opened it with the page
      dowod.removeAttribute("data-open");
      dowod.close();
      showDowod();
    }
    dowod.addEventListener("close", function () {
      var back = opener && document.contains(opener) ? opener : document.getElementById("main");
      opener = null;
      dowod.removeAttribute("data-more");
      if (back) back.focus();
    });
    // "Szczegóły badania" (WP21): one click opens the details of every card, and the choice
    // holds while the panel is open (also for the cards behind "Więcej dowodów").
    dowod.addEventListener("toggle", function (event) {
      var target = event.target;
      if (!target.matches) return;
      var wanted = dowod.hasAttribute("data-more");
      if (target.matches("details.ev-more") && target.open !== wanted) {
        wanted = target.open;
        if (wanted) dowod.setAttribute("data-more", ""); else dowod.removeAttribute("data-more");
      } else if (!target.matches("details.dowod-rest")) {
        return;
      }
      dowod.querySelectorAll("details.ev-more").forEach(function (more) {
        if (more.open !== wanted) more.open = wanted;
      });
    }, true);
    dowod.addEventListener("click", function (event) {
      if (event.target === dowod) dowod.close();  // a click on the dimmed page beside it
    });
    // Tab and Shift+Tab go round the panel's controls instead of leaving for the browser.
    dowod.addEventListener("keydown", function (event) {
      if (event.key !== "Tab") return;
      var items = Array.prototype.filter.call(
        dowod.querySelectorAll("a[href], button, summary, [tabindex]:not([tabindex='-1'])"),
        function (el) { return el.offsetParent !== null; }
      );
      if (!items.length) return;
      var first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
  }

  document.addEventListener("click", function (event) {
    if (!dowod) return;
    if (event.target.closest("[data-dowod-close]")) { dowod.close(); return; }
    var point = event.target.closest("[data-dowod]");
    if (!point) return;
    event.preventDefault();
    opener = point;
    fetch(point.getAttribute("data-dowod"), { credentials: "same-origin", headers: { "HX-Request": "true" } })
      .then(function (response) {
        if (!response.ok) throw new Error(String(response.status));
        return response.text();
      })
      .then(function (html) {
        dowod.querySelector(".dowod-body").innerHTML = html;
        showDowod();
      })
      .catch(function () { opener = null; });
  });

  // Collapsible sections (WP21, Pulpit): a section opened or closed stays so in this browser.
  // The server renders the default; storage may be blocked, then the default holds.
  function foldKey(fold) { return "sentinel.fold." + fold.getAttribute("data-fold"); }
  function applyFolds(root) {
    (root || document).querySelectorAll("details[data-fold]").forEach(function (fold) {
      var stored = null;
      try { stored = window.localStorage.getItem(foldKey(fold)); } catch (e) { stored = null; }
      if (stored === "1") fold.open = true;
      else if (stored === "0") fold.open = false;
    });
  }
  applyFolds(document);
  document.body.addEventListener("htmx:load", function (event) { applyFolds(event.target); });
  document.addEventListener("toggle", function (event) {
    var fold = event.target;
    if (!fold.matches || !fold.matches("details[data-fold]")) return;
    try { window.localStorage.setItem(foldKey(fold), fold.open ? "1" : "0"); } catch (e) { /* not kept */ }
  }, true);

  // Źródła: a filter applies as soon as it changes.
  document.addEventListener("change", function (event) {
    var form = event.target.closest("form[data-autosubmit]");
    if (form && event.target.tagName === "SELECT") form.requestSubmit();
  });
})();
