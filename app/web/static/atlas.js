/* Copyright 2026 TAK-Solutions LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * ATLAS console behaviour. Hand-written, no dependencies, no build step (DW1).
 * Everything is opt-in through data- attributes so a page only gets the wiring
 * it asks for.
 */
/* ⚠️ First on purpose. A top-level throw anywhere in this file stops every
   block after it from evaluating — so the further down this sits, the more
   unrelated failures can silently take it out. Found exactly that way: a
   missing search control on the Apps page threw, and the marker (then last in
   the file) never ran on that page at all. */
/* --- Required fields wear an asterisk (W146) --------------------------------
   Every mandatory field says so, project-wide, without anyone remembering to
   write it on each one.

   ⚠️ Driven by the `required` attribute rather than a hand-maintained list,
   because the attribute is already what the browser enforces and what the
   server's Form(...) signature mirrors. A separate list would be a third place
   to state the same fact, and the one nobody updates.

   ⚠️ A control with no visible label gets nothing — there is nowhere to put a
   mark. Those are inline toolbar inputs carrying `aria-label` (cloning a policy
   from the list), where the surrounding text already says what is wanted.

   Runs again when the DOM grows, because several forms add rows on demand
   (managed-file rows, attribute rows) and a field that appeared after load is
   exactly as mandatory as one that did not.
*/
(function () {
  "use strict";

  var MARK = "req-star";

  function labelFor(control) {
    /* The `for` pairing first: it is the one that survives a tip paragraph
       sitting between the label and its input, which several forms have. */
    var id = control.getAttribute("id");
    if (id) {
      var byFor = document.querySelector('label[for="' + CSS.escape(id) + '"]');
      if (byFor) return byFor;
    }
    return control.closest("label");
  }

  function star(label) {
    var mark = document.createElement("abbr");
    mark.className = MARK;
    mark.textContent = "*";
    /* Announced as "required" rather than read out as a bare asterisk, which is
       what a screen reader would otherwise do with it. */
    mark.title = "required";
    mark.setAttribute("aria-label", "required");
    label.appendChild(document.createTextNode(" "));
    label.appendChild(mark);
  }

  function mark(control) {
    if (control.type === "hidden" || control.disabled) return;
    var label = labelFor(control);
    if (!label || label.querySelector("." + MARK)) return;
    star(label);
  }

  function sweep(root) {
    var scope = root || document;
    scope.querySelectorAll("[required]").forEach(mark);
    /* An explicit opt-in, for a label that names a *group* of mandatory
       controls rather than one of them — a file list whose rows are added on
       demand, where `for` could only ever point at the first row. */
    scope.querySelectorAll("label[data-required]").forEach(function (label) {
      if (!label.querySelector("." + MARK)) star(label);
    });
  }

  sweep(document);

  if (window.MutationObserver) {
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) return;
          if (node.matches && node.matches("[required]")) mark(node);
          if (node.querySelectorAll) sweep(node);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }
})();

(function () {
  "use strict";

  /* --- Modal --------------------------------------------------------------- */
  /* <button data-modal-open="new-policy">  opens  <div class="modal-backdrop" id="new-policy" hidden>
     A click on the backdrop, the [data-modal-close] control, or Escape closes it. */

  function openModal(id) {
    var el = document.getElementById(id);
    if (el) el.hidden = false;
  }
  function closeModal(el) {
    if (el) el.hidden = true;
  }

  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-modal-open]");
    if (opener) {
      e.preventDefault();
      openModal(opener.getAttribute("data-modal-open"));
      return;
    }
    var closer = e.target.closest("[data-modal-close]");
    if (closer) {
      e.preventDefault();
      closeModal(closer.closest(".modal-backdrop"));
      return;
    }
    if (e.target.classList && e.target.classList.contains("modal-backdrop")) {
      closeModal(e.target);
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-backdrop:not([hidden])").forEach(closeModal);
    }
  });

  /* --- Tabs -------------------------------------------------------------------
     <div class="tabs" data-tabs>
       <button class="tab on" data-tab="a">A</button>
       <button class="tab" data-tab="b">B</button>
     </div>
     <div class="tab-panel" data-tab-panel="a">...</div>
     <div class="tab-panel" data-tab-panel="b" hidden>...</div>
     The active tab is also written to the URL hash so a reload keeps its place. */

  function activateTab(container, name) {
    container.querySelectorAll("[data-tab]").forEach(function (btn) {
      btn.classList.toggle("on", btn.getAttribute("data-tab") === name);
    });
    var scope = container.getAttribute("data-tabs-scope");
    var root = scope ? document.getElementById(scope) : document;
    root.querySelectorAll("[data-tab-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-tab-panel") !== name;
    });
  }

  document.querySelectorAll("[data-tabs]").forEach(function (container) {
    /* ⚠️ `?tab=` counts as well as `#tab-`, because both forms are already in
       use and only one of them worked. `/admin?tab=googleplay` landed on Admin
       and sat on whichever tab was default, which reads as a broken link rather
       than an unsupported spelling — and `/apps?tab=tpc` is worse, because the
       server *does* honour that query (it eagerly loads the catalog) while the
       page went on showing a different tab entirely.

       The hash still wins: it is what a click writes back, so it is the more
       specific statement of intent. */
    var fromHash = (location.hash || "").replace(/^#tab-/, "");
    var fromQuery = "";
    try {
      fromQuery = new URLSearchParams(location.search).get("tab") || "";
    } catch (e) {
      fromQuery = "";
    }
    var wanted = fromHash || fromQuery;
    var initial =
      (wanted && container.querySelector('[data-tab="' + CSS.escape(wanted) + '"]') && wanted) ||
      (container.querySelector("[data-tab].on") || container.querySelector("[data-tab]") || {}).getAttribute &&
        (container.querySelector("[data-tab].on") || container.querySelector("[data-tab]")).getAttribute("data-tab");
    if (initial) activateTab(container, initial);

    container.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-tab]");
      if (!btn) return;
      e.preventDefault();
      var name = btn.getAttribute("data-tab");
      activateTab(container, name);
      history.replaceState(null, "", "#tab-" + name);
    });

    // So a link elsewhere on the page (e.g. `href="#tab-templates"`) can switch
    // this tab bar without a reload.
    window.addEventListener("hashchange", function () {
      var name = (location.hash || "").replace(/^#tab-/, "");
      if (name && container.querySelector('[data-tab="' + CSS.escape(name) + '"]')) {
        activateTab(container, name);
      }
    });
  });

  /* --- Two-level rail navigation (policy sub-pages, W12) ---------------------
     <nav class="rail" data-rail data-rail-panels="cat-panels">
       <li class="rail-cat" data-cat-group="restrictions">
         <a class="rail-cat-head" data-cat-toggle>Restrictions</a>   (N>1 sub-pages)
         <ul class="rail-sub">
           <li><a data-page="restrictions:basic">Basic</a></li> ...
       ...
       <li class="rail-cat" data-cat-group="files">
         <a class="rail-cat-head" data-page="files:files">Files</a>  (leaf)
     Panels: <section data-page-panel="restrictions:basic" hidden>...</section> */

  document.querySelectorAll("[data-rail]").forEach(function (rail) {
    var panelsRoot = document.getElementById(rail.getAttribute("data-rail-panels")) || document;

    function showPage(key) {
      panelsRoot.querySelectorAll("[data-page-panel]").forEach(function (p) {
        p.hidden = p.getAttribute("data-page-panel") !== key;
      });
      rail.querySelectorAll("[data-page]").forEach(function (a) {
        a.classList.toggle("on", a.getAttribute("data-page") === key);
      });
      var cat = key.split(":")[0];
      rail.querySelectorAll(".rail-cat").forEach(function (li) {
        var mine = li.getAttribute("data-cat-group") === cat;
        li.classList.toggle("open", mine);
        var head = li.querySelector(".rail-cat-head");
        if (head) head.classList.toggle("active-cat", mine);
      });
      history.replaceState(null, "", "#page-" + key);
    }

    rail.addEventListener("click", function (e) {
      var page = e.target.closest("[data-page]");
      if (page) {
        e.preventDefault();
        showPage(page.getAttribute("data-page"));
        return;
      }
      var toggle = e.target.closest("[data-cat-toggle]");
      if (toggle) {
        e.preventDefault();
        toggle.closest(".rail-cat").classList.toggle("open");
      }
    });

    var fromHash = (location.hash || "").replace(/^#page-/, "");
    var first = panelsRoot.querySelector("[data-page-panel]");
    var start =
      (fromHash && panelsRoot.querySelector('[data-page-panel="' + CSS.escape(fromHash) + '"]') && fromHash) ||
      (first && first.getAttribute("data-page-panel"));
    if (start) showPage(start);
  });

  /* --- Live "this category has content" checks -------------------------------
     The rail's green checks are rendered from the *saved* spec, which means they
     are always absent while building a new policy (nothing is saved yet) and go
     stale the moment anyone types. This recomputes them from the form itself, so
     the rail answers "what have I filled in?" at a glance — the only question it
     is there to answer.

     "Has content" deliberately mirrors what `parse_form` keeps, so a check
     promises a field that will actually be saved:
       * a control outside a repeatable row counts when it is non-empty — every
         "Not managed" option is the empty string, so untouched fields score zero;
       * a row that came from saved data always counts;
       * a row the operator just added counts only once something in it is both
         non-empty and changed from its default — otherwise the pre-selected
         "Monthly / Mobile data" on a blank threshold row would claim content that
         saving is about to discard. */

  (function () {
    var rail = document.querySelector("[data-rail]");
    if (!rail) return;
    var panelsRoot = document.getElementById(rail.getAttribute("data-rail-panels")) || document;

    // Rows present at load came from the server, i.e. from saved policy content.
    //
    // ⚠️ **Inside a rowset only** (W142). The inference is "a row exists, so the
    // server rendered it from something saved" — and that holds only where rows
    // are created per saved entry. ATAK Core is a *fixed* `.rs-row`: it uses the
    // class so the version picker can find its package select with
    // `closest(".rs-row")`, and it renders whether or not anything is chosen.
    // Marking it saved made a blank ATAK section report content on every page
    // load, and no amount of emptying the controls could undo it, because this
    // branch returns before they are looked at.
    panelsRoot.querySelectorAll("[data-rowset] .rs-row").forEach(function (row) {
      row.setAttribute("data-saved-row", "");
    });

    function nonEmpty(el) {
      if (el.type === "checkbox" || el.type === "radio") return el.checked;
      return (el.value || "").trim() !== "";
    }

    function changed(el) {
      if (el.tagName === "SELECT") {
        return Array.prototype.some.call(el.options, function (o) {
          return o.selected !== o.defaultSelected;
        });
      }
      if (el.type === "checkbox" || el.type === "radio") return el.checked !== el.defaultChecked;
      return el.value !== el.defaultValue;
    }

    function controls(scope) {
      // `disabled` skips the Knox-gated controls, which cannot hold content and
      // are not submitted either.
      return Array.prototype.filter.call(
        scope.querySelectorAll("input, select, textarea"),
        function (el) {
          // `__`-prefixed names are presentational only - `__kiosk_mode` picks
          // which single-app form to show and is never read by parse_form. One
          // of its radios is checked from the moment the page renders, so
          // counting it marked "Single app" as filled on every new policy,
          // before an app had been chosen.
          //
          // Prefix, not substring: multi_app_packages__package_name is a real
          // field and contains a double underscore in the middle.
          if (el.name && el.name.indexOf("__") === 0) return false;

          // ⚠️ `<field>__key` is scaffolding, not content. The ATAK settings
          // table renders one hidden key input per *declared* setting — 293 of
          // them for ATAK, every one non-empty — so counting them marked the
          // page configured the moment it finished loading, before anyone had
          // typed a value. Nothing is lost by skipping them: a key is always
          // rendered beside its `__value`, and that is the half an operator
          // actually fills in.
          if (el.name && /__key$/.test(el.name)) return false;

          return !el.disabled && el.name !== "csrf_token" && el.type !== "file";
        }
      );
    }

    function hasContent(scope) {
      var loose = controls(scope).filter(function (el) { return !el.closest(".rs-row"); });
      if (loose.some(nonEmpty)) return true;

      return Array.prototype.some.call(scope.querySelectorAll(".rs-row"), function (row) {
        if (row.hasAttribute("data-saved-row")) return true;
        return controls(row).some(function (el) { return nonEmpty(el) && changed(el); });
      });
    }

    function mark(anchor, on) {
      var check = anchor && anchor.querySelector(".rail-check");
      if (check) check.hidden = !on;
    }

    function refresh() {
      rail.querySelectorAll(".rail-cat").forEach(function (item) {
        var key = item.getAttribute("data-cat-group");
        var panels = panelsRoot.querySelectorAll('[data-page-panel^="' + key + ':"]');
        var any = false;

        panels.forEach(function (panel) {
          var filled = hasContent(panel);
          any = any || filled;
          var slug = panel.getAttribute("data-page-panel");
          mark(item.querySelector('[data-page="' + slug + '"]'), filled);
        });

        mark(item.querySelector(".rail-cat-head"), any);
      });
    }

    panelsRoot.addEventListener("input", refresh);
    panelsRoot.addEventListener("change", refresh);
    /* ⚠️ A recount that is not an edit. Code that rebuilds a control after the
       page has loaded needs the rail to look again, but firing a synthetic
       `input` to get that also told the unsaved-changes guard the operator had
       typed something — so leaving a freshly saved policy warned about changes
       nobody made. Anything programmatic asks for a recount by name. */
    panelsRoot.addEventListener("atlas:recount", refresh);
    // A removed row fires no event of its own, and an added one is empty until
    // typed into; both still need the rail to catch up.
    panelsRoot.addEventListener("click", function () { setTimeout(refresh, 0); });
    refresh();
    // ⚠️ Again, once the rest of this file has run (W142). This block sits near
    // the top and several modules below it *disable* controls during their own
    // wiring — the version pickers disable a build select until an app is
    // chosen — and a disabled control is deliberately not counted as content.
    // Computing the rail only at this point reads the page as it was half a
    // tick before it finished setting itself up, and ticks pages nobody has
    // touched.
    setTimeout(refresh, 0);
  })();

  /* --- App configurations (managed configuration, W49) -----------------------
     Picking an app fetches the keys that app's own APK declares, renders one
     control per key, and on save writes a row into the rowset. The values travel
     as JSON in a hidden input because the keys belong to the app: there is no
     fixed set of field names to spread them across, and a build that adds a key
     must not need a server change to be configurable. */

  (function () {
    var set = document.querySelector("[data-app-configs]");
    if (!set) return;
    var frame = document.getElementById("app-config-frame");
    if (!frame) return;

    var picker = frame.querySelector("[data-app-config-package]");
    var fields = frame.querySelector("[data-app-config-fields]");
    var save = frame.querySelector("[data-app-config-save]");
    var addBtn = set.querySelector("[data-app-config-add]");
    var current = [];

    function reset() {
      fields.innerHTML = "";
      current = [];
      save.disabled = true;
    }

    addBtn.addEventListener("click", function () {
      picker.value = "";
      reset();
      frame.hidden = false;
    });

    picker.addEventListener("change", function () {
      reset();
      var pkg = picker.value;
      if (!pkg) return;

      fields.textContent = "Reading the app's declared configuration…";
      fetch("/policies/app-config-schema?package=" + encodeURIComponent(pkg))
        .then(function (r) { return r.json(); })
        .then(function (schema) {
          fields.innerHTML = "";
          if (!schema.keys || !schema.keys.length) {
            // Not an error: most apps declare nothing. Say which it is.
            fields.textContent = schema.note || "This app declares no managed configuration.";
            return;
          }
          current = schema.keys;

          // Chrome declares 231 keys. A flat wall of them is unusable, so the
          // frame gets a filter as soon as there are more than a screenful.
          if (schema.keys.length > 12) {
            var search = document.createElement("input");
            search.type = "search";
            search.className = "field-full";
            search.setAttribute("aria-label", "Filter keys");
            var searchTip = document.createElement("p");
            searchTip.className = "field-tip";
            searchTip.style.marginBottom = "12px";
            searchTip.textContent = "Filter " + schema.keys.length + " keys.";
            search.addEventListener("input", function () {
              var q = search.value.trim().toLowerCase();
              fields.querySelectorAll("[data-config-field]").forEach(function (row) {
                row.hidden = q !== "" &&
                  row.getAttribute("data-config-field").toLowerCase().indexOf(q) === -1;
              });
            });
            fields.appendChild(search);
            fields.appendChild(searchTip);
          }

          schema.keys.forEach(function (k) {
            var wrap = document.createElement("div");
            wrap.style.marginBottom = "10px";
            // Filtering matches the key and the label together: an operator
            // hunting "proxy" should not need to know which of the two carries it.
            wrap.setAttribute("data-config-field", k.key + " " + (k.label || ""));

            var label = document.createElement("label");
            label.textContent = k.label;
            wrap.appendChild(label);

            if (k.unsupported_reason) {
              var note = document.createElement("div");
              note.className = "muted";
              note.style.fontSize = "12px";
              note.textContent = k.unsupported_reason;
              wrap.appendChild(note);
            } else if (k.control === "bool") {
              var sel = document.createElement("select");
              sel.className = "field-full";
              [["", "Not set"], ["true", "True"], ["false", "False"]].forEach(function (o) {
                var opt = document.createElement("option");
                opt.value = o[0]; opt.textContent = o[1];
                sel.appendChild(opt);
              });
              sel.setAttribute("data-config-key", k.key);
              wrap.appendChild(sel);
            } else if (k.options && k.options.length && k.control === "multi_select") {
              // A checklist, not a text box: the value Android wants is a
              // String[] of the selected entries, and asking an operator to type
              // comma-separated values they cannot see is how wrong ones get sent.
              var list = document.createElement("div");
              list.className = "config-options";
              list.setAttribute("data-config-key", k.key);
              list.setAttribute("data-config-multi", "1");
              k.options.forEach(function (o) {
                var line = document.createElement("label");
                line.className = "config-option";
                var box = document.createElement("input");
                box.type = "checkbox";
                box.value = o.value;
                line.appendChild(box);
                line.appendChild(document.createTextNode(" " + o.label));
                list.appendChild(line);
              });
              wrap.appendChild(list);
            } else if (k.options && k.options.length) {
              // The app told us exactly which values it accepts (W54), so offer
              // those and nothing else.
              var choice = document.createElement("select");
              choice.className = "field-full";
              var blank = document.createElement("option");
              blank.value = ""; blank.textContent = "Not set";
              choice.appendChild(blank);
              k.options.forEach(function (o) {
                var opt = document.createElement("option");
                opt.value = o.value;
                // The label is the app's own wording; the value is what goes to
                // the device. Both are shown because an operator reading the
                // app's docs will be looking for the value.
                opt.textContent = o.label + (o.label === o.value ? "" : "  (" + o.value + ")");
                choice.appendChild(opt);
              });
              choice.setAttribute("data-config-key", k.key);
              wrap.appendChild(choice);
            } else {
              var input = document.createElement("input");
              input.type = k.control === "int" ? "number" : "text";
              input.className = "field-full";
              // ⚠️ Kept as a placeholder, unlike the rest (W92). This is the
              // field's *state* — what the app uses if nothing is set — not a
              // hint about what to type, so it cannot be mistaken for a value
              // the operator meant to save.
              input.placeholder = k.default || "not set";
              input.setAttribute("data-config-key", k.key);
              wrap.appendChild(input);
            }

            // Only when the option list could NOT be read. An app declares its
            // choices as resource arrays and most resolve now, but a build whose
            // arrays are missing still must not show a text box that implies any
            // value will do.
            if ((k.control === "choice" || k.control === "multi_select") &&
                !(k.options && k.options.length)) {
                var hint = document.createElement("div");
                hint.className = "muted";
                hint.style.fontSize = "11px";
                hint.textContent =
                  (k.control === "multi_select" ? "Multi-select" : "Choice") +
                  ": the app defines the accepted values, but this build does not" +
                  " carry them in readable form." +
                  (k.default ? " Its default is " + k.default + "." : "");
                wrap.appendChild(hint);
            }

            // The key is worth showing even when a title survived: it is what the
            // app actually reads, and what an operator will be given in docs.
            var keyLine = document.createElement("div");
            keyLine.className = "muted";
            keyLine.style.fontSize = "11px";
            keyLine.textContent = k.key + (k.description ? " — " + k.description : "");
            wrap.appendChild(keyLine);

            fields.appendChild(wrap);
          });
          save.disabled = false;
        })
        .catch(function () {
          fields.textContent = "Could not read this app's configuration.";
        });
    });

    save.addEventListener("click", function () {
      var pkg = picker.value;
      if (!pkg) return;

      var values = {};
      fields.querySelectorAll("[data-config-key]").forEach(function (el) {
        var key = el.getAttribute("data-config-key");

        // A multi-select is a container of checkboxes, not an input — it has no
        // `.value`, and reading one would silently record every such key as unset.
        if (el.hasAttribute("data-config-multi")) {
          var picked = [];
          el.querySelectorAll("input[type=checkbox]").forEach(function (box) {
            if (box.checked) picked.push(box.value);
          });
          // Newline-separated AND newline-terminated. The trailing newline is
          // what makes a single selection unambiguous: without it a one-item
          // list is byte-identical to a hand-typed one, and the agent would fall
          // back to comma-splitting and tear a value like "Smith, John" in half.
          if (picked.length) values[key] = picked.join("\n") + "\n";
          return;
        }

        var v = (el.value || "").trim();
        // Only what the operator actually set: an empty control means "leave this
        // key alone", not "send an empty string", which an app would act on.
        if (v !== "") values[key] = v;
      });

      var row = document.createElement("div");
      row.className = "rs-row";
      var count = Object.keys(values).length;
      row.innerHTML =
        '<input type="hidden" name="app_configs__package_name">' +
        '<input type="hidden" name="app_configs__values">' +
        '<div style="flex:1"><strong></strong>' +
        '<span class="muted" style="font-size:12px"></span></div>' +
        '<button type="button" class="ghost" data-remove-row>Remove</button>';
      row.querySelector('[name="app_configs__package_name"]').value = pkg;
      row.querySelector('[name="app_configs__values"]').value = JSON.stringify(values);
      row.querySelector("strong").textContent = pkg;
      row.querySelector(".muted").textContent =
        " · " + count + (count === 1 ? " key" : " keys");

      addBtn.insertAdjacentElement("beforebegin", row);
      frame.hidden = true;
    });
  })();

  /* --- Upload with progress (W51) --------------------------------------------
     <form data-upload-form> + a #upload-modal with the data-upload-* parts.

     ⚠️ XMLHttpRequest, not fetch. `fetch` still cannot report **upload** progress,
     and it cannot be aborted in a way that stops the bytes — so a Cancel button
     built on it would hide the dialog while the transfer carried on. A 130 MB
     package with no feedback is what prompted this; a fake progress bar would
     have been worse than none. */

  (function () {
    var form = document.querySelector("[data-upload-form]");
    var modal = document.getElementById("upload-modal");
    if (!form || !modal) return;

    var title = modal.querySelector("[data-upload-title]");
    var detail = modal.querySelector("[data-upload-detail]");
    var bar = modal.querySelector("[data-upload-bar]");
    var bytes = modal.querySelector("[data-upload-bytes]");
    var cancel = modal.querySelector("[data-upload-cancel]");
    var close = modal.querySelector("[data-upload-close]");
    var request = null;

    function mb(n) { return (n / 1048576).toFixed(1) + " MB"; }

    function finish(heading, message) {
      request = null;
      title.textContent = heading;
      detail.textContent = message;
      cancel.hidden = true;
      close.hidden = false;
    }

    form.addEventListener("submit", function (e) {
      var file = form.querySelector('input[type="file"]').files[0];
      if (!file) return;  // let the browser's own "required" handling speak
      e.preventDefault();

      title.textContent = "Uploading " + file.name;
      detail.textContent = "Starting…";
      bytes.textContent = "";
      bar.style.width = "0";
      cancel.hidden = false;
      close.hidden = true;
      modal.hidden = false;

      request = new XMLHttpRequest();
      request.open("POST", form.getAttribute("action"));

      request.upload.addEventListener("progress", function (event) {
        if (!event.lengthComputable) {
          detail.textContent = "Uploading — size unknown";
          return;
        }
        var percent = Math.round((event.loaded / event.total) * 100);
        bar.style.width = percent + "%";
        detail.textContent = "Uploading — " + percent + "%";
        bytes.textContent = mb(event.loaded) + " of " + mb(event.total);
      });

      // The server still has to unpack an XAPK and hash every part, which on a
      // large package takes noticeable time *after* the last byte arrives. Saying
      // so stops the bar sitting at 100% looking stuck.
      request.upload.addEventListener("load", function () {
        detail.textContent = "Uploaded — the server is unpacking and verifying it…";
        bytes.textContent = "";
      });

      request.addEventListener("load", function () {
        if (request.status >= 200 && request.status < 400) {
          // The server answers with a redirect to the refreshed page.
          window.location = request.responseURL || window.location.pathname;
          return;
        }
        bar.style.width = "0";
        finish("Upload failed", "The server refused it (HTTP " + request.status + ").");
      });

      request.addEventListener("error", function () {
        bar.style.width = "0";
        finish("Upload failed", "Lost contact with the server.");
      });

      request.addEventListener("abort", function () {
        bar.style.width = "0";
        finish("Upload cancelled", "Nothing was added to the library.");
      });

      request.send(new FormData(form));
    });

    cancel.addEventListener("click", function () {
      // Genuinely stops the transfer rather than just closing the dialog.
      if (request) request.abort();
      else modal.hidden = true;
    });

    close.addEventListener("click", function () { modal.hidden = true; });
  })();

  /* --- Which build, for the app that was picked (W51, W139) -------------------
     Every option carries `data-package`; the dropdown once listed every version
     of every app at once, including builds of apps the row has nothing to do
     with, which is an easy way to pin the wrong one. It is empty until an app is
     chosen, and then shows only that app's builds.

     ⚠️ Since W139 there is nothing else in the list. "Latest published" and "At
     least N" were automatic-selection modes, and the server no longer honours
     either, so the default is now a **real build** — the newest, which is the
     first option because the template sorts descending.

     Options are removed and re-added rather than hidden: browsers honour
     `hidden` on an <option> inconsistently, and a "hidden" option that can still
     be selected by keyboard is worse than the bug being fixed. */

  (function () {
    // Wired lazily and per row, because "Add app" clones a row from a <template>
    // long after load — anything done only at startup would leave every new row
    // showing the unfiltered list again.
    function wire(choice) {
      if (choice.hasAttribute("data-version-filtered")) return;
      var row = choice.closest(".rs-row");
      var picker = row && row.querySelector('select[name$="__package_name"]');
      if (!picker) return;
      choice.setAttribute("data-version-filtered", "");

      // The full set, kept aside so filtering is never destructive.
      var all = Array.prototype.map.call(choice.options, function (o) { return o; });

      function rebuild(keepValue) {
        var pkg = picker.value;
        choice.innerHTML = "";

        if (!pkg) {
          // Nothing chosen: say so rather than offer a list that cannot apply.
          var prompt = document.createElement("option");
          prompt.value = "";
          prompt.textContent = "— pick an app first —";
          choice.appendChild(prompt);
          choice.disabled = true;
          return;
        }

        var wanted = all.filter(function (o) {
          return o.getAttribute("data-package") === pkg;
        });

        if (!wanted.length) {
          // An app in the library with no installable build. Say so rather than
          // leave an empty select that looks like it is still loading.
          var none = document.createElement("option");
          none.value = "";
          none.textContent = "— no builds uploaded for this app —";
          choice.appendChild(none);
          choice.disabled = true;
          return;
        }

        choice.disabled = false;
        wanted.forEach(function (o) { choice.appendChild(o); });

        // ⚠️ The newest build is the default, and `wanted[0]` is it because the
        // template sorts descending. A saved choice wins when it still belongs
        // to this app — otherwise it would be a pin at some other app's build,
        // or, for a policy written before W139, a floor that matches nothing.
        if (keepValue && wanted.some(function (o) { return o.value === keepValue; })) {
          choice.value = keepValue;
        } else {
          choice.value = wanted[0].value;
        }
      }

      picker.addEventListener("change", function () { rebuild(null); });
      rebuild(choice.value);
    }

    function wireAll() {
      document.querySelectorAll('select[name$="__version_choice"]').forEach(wire);
    }

    // After the add-row handler has inserted the clone.
    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-add-row]")) setTimeout(wireAll, 0);
    });
    wireAll();
  })();

  /* --- Table filter --------------------------------------------------------
     <input type="search" data-filter="#device-table">
     Rows whose text does not contain the query are hidden. Case-insensitive. */

  document.querySelectorAll("[data-filter]").forEach(function (input) {
    var target = document.querySelector(input.getAttribute("data-filter"));
    if (!target) return;
    var rows = function () { return target.tBodies[0] ? Array.from(target.tBodies[0].rows) : []; };
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      var shown = 0;
      rows().forEach(function (row) {
        if (row.hasAttribute("data-no-filter")) return;
        var hit = !q || row.textContent.toLowerCase().indexOf(q) !== -1;
        row.hidden = !hit;
        if (hit) shown++;
      });
      var count = document.querySelector('[data-filter-count="' + input.getAttribute("data-filter") + '"]');
      if (count) count.textContent = shown + (shown === 1 ? " match" : " matches");
    });
  });

  /* --- Column sort -------------------------------------------------------------
     <table data-sortable> ... <th data-sort>Header</th>
     Clicking a header sorts by that column's text; numeric where every cell parses. */

  document.querySelectorAll("table[data-sortable]").forEach(function (table) {
    table.querySelectorAll("th[data-sort]").forEach(function (th, colIndex) {
      th.style.cursor = "pointer";
      th.title = "Sort by " + th.textContent.trim();
      var asc = true;
      th.addEventListener("click", function () {
        var body = table.tBodies[0];
        if (!body) return;
        var rows = Array.from(body.rows);
        var idx = Array.from(th.parentNode.children).indexOf(th);
        var val = function (row) { return (row.cells[idx] ? row.cells[idx].textContent.trim() : ""); };
        var numeric = rows.every(function (r) { return val(r) === "" || !isNaN(parseFloat(val(r))); });
        rows.sort(function (a, b) {
          var x = val(a), y = val(b);
          var cmp = numeric ? (parseFloat(x) || 0) - (parseFloat(y) || 0) : x.localeCompare(y);
          return asc ? cmp : -cmp;
        });
        asc = !asc;
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });

  /* --- Repeatable rows (policy form list controls) --------------------------
     <div data-rowset>
       ...existing .rs-row blocks...
       <template data-row-template><div class="rs-row">...</div></template>
       <button data-add-row>Add</button>
     </div>
     A [data-remove-row] button inside a row deletes that row. */

  document.addEventListener("click", function (e) {
    var add = e.target.closest("[data-add-row]");
    if (add) {
      e.preventDefault();
      var set = add.closest("[data-rowset]");
      var tpl = set && set.querySelector("[data-row-template]");
      if (tpl) add.insertAdjacentHTML("beforebegin", tpl.innerHTML.trim());
      return;
    }
    var rm = e.target.closest("[data-remove-row]");
    if (rm) {
      e.preventDefault();
      var row = rm.closest(".rs-row");
      var set = row && row.closest("[data-kiosk-apps]");
      if (row) row.remove();
      if (set) renderKioskPreview(set);
    }
  });

  /* --- Multi-app kiosk: ordering, favourites, and the grid preview (W68) -----
     Row order IS the order the apps appear on the device, so moving a row is the
     whole edit — there is no stored index that could disagree with what the
     operator is looking at.

     The favourite checkbox carries the package name as its value rather than a
     position, because an unchecked checkbox does not submit at all: pairing by
     position would shift every favourite after the first unchecked row onto the
     wrong app, and a wrong favourite looks deliberate rather than broken. The
     value therefore has to follow the select. */

  function syncFavouriteValues(set) {
    set.querySelectorAll("[data-kiosk-app-row]").forEach(function (row) {
      var select = row.querySelector("select");
      var favourite = row.querySelector("[data-favorite]");
      if (!select || !favourite) return;
      favourite.value = select.value;
      // A row with no app chosen cannot be a favourite of anything.
      if (!select.value) favourite.checked = false;
      favourite.disabled = !select.value;
    });
  }

  /* Each row's activity list is a fact about the app that row names, so it is
     fetched rather than typed — the same source the single-app kiosk uses. The
     saved value is kept as an option until the fetch lands, so a policy that is
     opened and saved without touching this row does not lose its activity. */
  function loadRowActivities(row, keepValue) {
    var select = row.querySelector("select[name$='__package_name']");
    var activity = row.querySelector("[data-kiosk-activity]");
    var note = row.querySelector("[data-kiosk-activity-note]");
    if (!select || !activity) return;

    var wanted = keepValue === undefined ? activity.value : keepValue;
    var pkg = select.value;

    function reset(label) {
      activity.innerHTML = "";
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Default — open the app normally";
      activity.appendChild(blank);
      if (note) note.textContent = label;
    }

    if (!pkg) {
      reset("Pick an app first.");
      return;
    }
    if (note) note.textContent = "Reading the app…";

    fetch("/policies/app-activities?package=" + encodeURIComponent(pkg))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var list = data.activities || [];
        reset("");
        list.forEach(function (a) {
          var opt = document.createElement("option");
          opt.value = a.name;
          opt.textContent = a.name + (a.launcher ? "   (launcher)" : "");
          if (a.name === wanted) opt.selected = true;
          activity.appendChild(opt);
        });
        // A saved activity this build no longer declares is kept rather than
        // dropped: silently clearing it would change the policy on the next save.
        if (wanted && !list.some(function (a) { return a.name === wanted; })) {
          var kept = document.createElement("option");
          kept.value = wanted;
          kept.textContent = wanted + "   (not in this build)";
          kept.selected = true;
          activity.appendChild(kept);
        }
        if (note) {
          note.textContent = list.length
            ? list.length + " activities declared by this build"
            : "This build declares no activities.";
        }
      })
      .catch(function () {
        if (note) note.textContent = "Could not read this app's activities.";
      });
  }

  function renderKioskPreview(set) {
    var preview = set.querySelector("[data-kiosk-preview]");
    if (!preview) return;
    var grid = set.querySelector("[data-kiosk-preview-grid]");
    var dock = set.querySelector("[data-kiosk-preview-dock]");
    var columnsInput = document.querySelector('[data-field="launcher_columns"] input');
    var columns = parseInt(columnsInput && columnsInput.value, 10);
    if (!(columns >= 2 && columns <= 8)) columns = 4;

    var tiles = [];
    var favourites = [];
    set.querySelectorAll("[data-kiosk-app-row]").forEach(function (row) {
      var select = row.querySelector("select");
      if (!select || !select.value) return;
      // The app's own name, as the device will show it — not the package, which
      // is what the device grid looked like before it read labels.
      var label = select.options[select.selectedIndex].text.replace(/\s*\([^)]*\)\s*$/, "");
      tiles.push(label);
      var favourite = row.querySelector("[data-favorite]");
      if (favourite && favourite.checked) favourites.push(label);
    });

    preview.hidden = tiles.length === 0;
    grid.style.gridTemplateColumns = "repeat(" + columns + ", 1fr)";
    grid.innerHTML = "";
    tiles.forEach(function (label) {
      var tile = document.createElement("div");
      tile.className = "kp-tile";
      tile.innerHTML = '<span class="kp-icon"></span><span class="kp-name"></span>';
      tile.querySelector(".kp-name").textContent = label;
      grid.appendChild(tile);
    });

    dock.hidden = favourites.length === 0;
    dock.innerHTML = "";
    favourites.forEach(function (label) {
      var tile = document.createElement("span");
      tile.className = "kp-icon";
      tile.title = label;
      dock.appendChild(tile);
    });
  }

  document.addEventListener("click", function (e) {
    var move = e.target.closest("[data-move-up], [data-move-down]");
    if (!move) return;
    e.preventDefault();
    var row = move.closest("[data-kiosk-app-row]");
    var set = row && row.closest("[data-kiosk-apps]");
    if (!row || !set) return;
    var up = move.hasAttribute("data-move-up");
    var sibling = up ? row.previousElementSibling : row.nextElementSibling;
    // Only swap with another row: the template and the Add button are siblings
    // too, and moving past them would take the row out of the list entirely.
    if (!sibling || !sibling.hasAttribute("data-kiosk-app-row")) return;
    if (up) sibling.before(row); else sibling.after(row);
    renderKioskPreview(set);
  });

  document.addEventListener("change", function (e) {
    var set = e.target.closest("[data-kiosk-apps]");
    if (set) {
      syncFavouriteValues(set);
      renderKioskPreview(set);
      // A new app means the old activity list belongs to a different build, so
      // it is refilled from scratch rather than kept.
      if (e.target.matches("select[name$='__package_name']")) {
        var row = e.target.closest("[data-kiosk-app-row]");
        if (row) loadRowActivities(row, null);
      }
      return;
    }
    // The column count lives in its own field, and the preview is the only place
    // its effect is visible before the policy reaches a device.
    if (e.target.closest('[data-field="launcher_columns"]')) {
      document.querySelectorAll("[data-kiosk-apps]").forEach(renderKioskPreview);
    }
  });

  document.addEventListener("input", function (e) {
    if (e.target.closest('[data-field="launcher_columns"]')) {
      document.querySelectorAll("[data-kiosk-apps]").forEach(renderKioskPreview);
    }
  });

  // Rows added by [data-add-row] arrive after this file runs, so the preview is
  // redrawn on the same click rather than only on the next change.
  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-add-row]")) return;
    var set = e.target.closest("[data-kiosk-apps]");
    if (set) setTimeout(function () { syncFavouriteValues(set); renderKioskPreview(set); }, 0);
  });

  document.querySelectorAll("[data-kiosk-apps]").forEach(function (set) {
    syncFavouriteValues(set);
    renderKioskPreview(set);
    // Saved rows arrive holding only their own activity as an option; this fills
    // in the rest of the build's so the operator can change it.
    set.querySelectorAll("[data-kiosk-app-row]").forEach(function (row) {
      var select = row.querySelector("select[name$='__package_name']");
      if (select && select.value) loadRowActivities(row, undefined);
    });
  });

  /* --- Insert an app group's packages into a required_apps JSON textarea -------
     Used by the profile editor's App Management section. Merges by package name so
     pressing a button twice does not duplicate entries. */

  /* Append a row per package in an app group to the named row-set (e.g.
     required_apps), skipping packages that already have a row.

     Reached by delegation, not by an inline onclick:
       <button data-add-app-group="required_apps" data-packages='["com.a"]'>
     The button carries the data; the page carries no script. That is what lets
     the Content-Security-Policy refuse inline script outright (SEC_AUDIT M-6). */
  function addAppGroup(fieldName, packageNames) {
    var set = document.querySelector('[data-rowset="' + fieldName + '"]');
    var tpl = set && set.querySelector("[data-row-template]");
    var addBtn = set && set.querySelector("[data-add-row]");
    if (!set || !tpl || !addBtn) return;
    var have = {};
    set.querySelectorAll('[name="' + fieldName + '__package_name"]').forEach(function (s) {
      if (s.value) have[s.value] = true;
    });
    (packageNames || []).forEach(function (name) {
      if (have[name]) return;
      addBtn.insertAdjacentHTML("beforebegin", tpl.innerHTML.trim());
      var rows = set.querySelectorAll('[name="' + fieldName + '__package_name"]');
      var select = rows[rows.length - 1];
      if (select && [].some.call(select.options, function (o) { return o.value === name; })) {
        select.value = name;
      }
    });
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-add-app-group]");
    if (!btn) return;
    e.preventDefault();
    var packages;
    try {
      packages = JSON.parse(btn.getAttribute("data-packages") || "[]");
    } catch (err) {
      /* A malformed attribute adds nothing rather than throwing into the
         console, where nobody would see it. */
      return;
    }
    addAppGroup(btn.getAttribute("data-add-app-group"), packages);
  });

  /* --- Mobile navigation (W190) -----------------------------------------------
     The menu itself is CSS: a checkbox and a label, so it is right on the first
     paint and works with no script at all. Everything here is enhancement.

     ⚠️ None of it may *open* the menu or the no-script path would be a lie. It
     only closes it, and keeps what a screen reader is told in step with what a
     sighted user can see. */

  var navSwitch = document.getElementById("nav-switch");
  var navToggle = document.querySelector(".nav-toggle");

  function syncNavState() {
    if (navToggle && navSwitch) {
      navToggle.setAttribute("aria-expanded", navSwitch.checked ? "true" : "false");
    }
  }

  function closeNav() {
    if (navSwitch && navSwitch.checked) {
      navSwitch.checked = false;
      syncNavState();
    }
  }

  if (navSwitch) {
    syncNavState();
    navSwitch.addEventListener("change", syncNavState);

    /* A label is not a button, so the browser gives it click and nothing else.
       Space and Enter have to be wired for a keyboard, and both are what
       somebody will try. */
    if (navToggle) {
      navToggle.addEventListener("keydown", function (e) {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          navSwitch.checked = !navSwitch.checked;
          syncNavState();
        }
      });
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeNav();
    });

    /* Tapping anywhere that is not the menu or its button. ⚠️ A tap on a *link*
       is deliberately left alone — the page is navigating anyway, and closing
       first makes the menu flicker shut before it goes. */
    document.addEventListener("click", function (e) {
      if (!navSwitch.checked) return;
      if (e.target.closest && (e.target.closest(".nav-grid") || e.target.closest(".nav-toggle"))) {
        return;
      }
      closeNav();
    });
  }

  /* --- Confirm before submit --------------------------------------------------
     <form data-confirm="This retires the token. Continue?"> */

  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* --- Reveal one of a set of forms by value ----------------------------------
     <select data-reveals="[data-type-form]"> shows the element whose
     data-type-form equals the selection and hides the rest.

     Change only. The page renders with the first option selected and the first
     form visible, so there is nothing to apply at load — and applying it anyway
     would look like it was handling a re-rendered form, which nothing here
     produces. */

  function applyReveal(select) {
    var selector = select.getAttribute("data-reveals");
    if (!selector || selector.charAt(0) !== "[") return;
    /* "[data-type-form]" names both the set to search and the attribute whose
       value is compared, so the attribute is read back off the selector rather
       than repeated in a second attribute that could disagree with it. */
    var attribute = selector.slice(1, -1);
    document.querySelectorAll(selector).forEach(function (el) {
      el.hidden = el.getAttribute(attribute) !== select.value;
    });
  }

  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches("[data-reveals]")) applyReveal(e.target);
  });

  /* --- Character counter -------------------------------------------------------
     <textarea name="x" maxlength="200"> + <span data-char-count-for="x">
     Keeps the count honest as the operator types. maxlength already stops them at
     the limit; this says how close they are before they hit it. */

  document.querySelectorAll("[data-char-count-for]").forEach(function (out) {
    var field = document.querySelector(
      '[name="' + CSS.escape(out.getAttribute("data-char-count-for")) + '"]'
    );
    if (!field) return;
    field.addEventListener("input", function () {
      out.textContent = field.value.length;
    });
  });

  /* --- Show/hide password ----------------------------------------------------
     <button type="button" data-toggle-password="wifi_password">Show</button>
     Toggles the named field between type="password" and type="text". */

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-toggle-password]");
    if (!btn) return;
    e.preventDefault();
    var input = document.getElementById(btn.getAttribute("data-toggle-password"));
    if (!input) return;
    var reveal = input.type === "password";
    input.type = reveal ? "text" : "password";
    btn.textContent = reveal ? "Hide" : "Show";
  });

  /* --- Save the provisioning QR ----------------------------------------------
     <div data-qr-image><svg .../></div>
     <button data-save-qr="atlas-enrollment-qr-bench">Save QR</button>

     Downloads the QR the page is already showing (W138). Only permanent QRs
     render the button; a saved copy of a fifteen-minute code is a file that
     expires before it is opened.

     ⚠️ Everything here happens in the browser. The QR encodes a live enrollment
     credential, and the page already holds it — serialising the SVG in place
     means it travels nowhere new. A download route would have had to take the
     secret as a parameter, which writes it into nginx's access log on every
     press.

     ⚠️ PNG, because it pastes into a document and prints from anything. The
     source SVG is 20mm across and rasterises to roughly 76 pixels, far too
     coarse for a code this dense, so the clone is given pixel dimensions first.

     ⚠️ White ground, painted before the QR. The SVG carries no background — the
     page supplies one with a white div — and a transparent PNG is black-on-
     black wherever something assumes a dark background. It would look perfect
     in the browser and refuse to scan off the page.

     ⚠️ Any failure saves the SVG instead. Browsers differ on whether drawing an
     SVG taints a canvas, and a button that silently does nothing is worse than
     one that hands over a less convenient file. */

  (function () {
    var SIZE = 1024;

    function save(blob, filename) {
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Deferred: revoking synchronously can cancel the download in Safari.
      setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-save-qr]");
      if (!btn) return;
      e.preventDefault();

      var wrap = document.querySelector("[data-qr-image]");
      var svg = wrap && wrap.querySelector("svg");
      if (!svg) return;

      var name = btn.getAttribute("data-save-qr") || "enrollment-qr";
      var clone = svg.cloneNode(true);
      clone.setAttribute("width", SIZE);
      clone.setAttribute("height", SIZE);
      var markup = new XMLSerializer().serializeToString(clone);
      var svgBlob = new Blob([markup], { type: "image/svg+xml;charset=utf-8" });

      var fallback = function () { save(svgBlob, name + ".svg"); };

      var url = URL.createObjectURL(svgBlob);
      var img = new Image();
      img.onload = function () {
        try {
          var canvas = document.createElement("canvas");
          canvas.width = SIZE;
          canvas.height = SIZE;
          var ctx = canvas.getContext("2d");
          ctx.fillStyle = "#fff";
          ctx.fillRect(0, 0, SIZE, SIZE);
          ctx.drawImage(img, 0, 0, SIZE, SIZE);
          canvas.toBlob(function (png) {
            URL.revokeObjectURL(url);
            if (png) save(png, name + ".png");
            else fallback();
          }, "image/png");
        } catch (err) {
          URL.revokeObjectURL(url);
          fallback();
        }
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        fallback();
      };
      img.src = url;
    });
  })();

  /* --- Unsaved-change guard --------------------------------------------------
     <form data-policy-form>: warn before leaving the page with edits pending —
     on tab close (beforeunload) and on any in-app link that would navigate away.
     A submit of that form clears the flag so the redirect after save is silent. */

  (function () {
    var form = document.querySelector("form[data-policy-form]");
    if (!form) return;
    var dirty = false;
    var WARNING = "You have unsaved changes to this policy. Leave without saving?";

    form.addEventListener("input", function () { dirty = true; });
    form.addEventListener("change", function () { dirty = true; });
    form.addEventListener("submit", function () { dirty = false; });

    window.addEventListener("beforeunload", function (e) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = WARNING;
      return WARNING;
    });

    document.addEventListener("click", function (e) {
      if (!dirty) return;
      var a = e.target.closest && e.target.closest("a[href]");
      if (!a) return;
      var href = a.getAttribute("href");
      if (!href || href.charAt(0) === "#" || a.target === "_blank") return;
      if (!window.confirm(WARNING)) e.preventDefault();
    });
  })();
})();

/* --- TPC plugin import ------------------------------------------------------
   The download runs on the server off the request, because a 433 MB plugin held
   inside one takes minutes and tells the operator nothing while it does. This
   starts the job, then polls it so the bar reflects real bytes rather than an
   animation that would keep moving through a stall. */
(function () {
  var modal = document.getElementById("tpc-import-modal");
  if (!modal) return;

  var title = document.getElementById("tpc-import-title");
  var detail = document.getElementById("tpc-import-detail");
  var bar = document.getElementById("tpc-import-bar");
  var bytes = document.getElementById("tpc-import-bytes");
  var close = document.getElementById("tpc-import-close");
  var timer = null;

  function mb(n) { return (n / 1048576).toFixed(1) + " MB"; }

  function finish(label, message, ok) {
    if (timer) { clearInterval(timer); timer = null; }
    title.textContent = label;
    detail.textContent = message;
    close.hidden = false;
  }

  close.addEventListener("click", function () {
    modal.hidden = true;
    // Reload so the row picks up its "imported" pill and Local apps is current.
    location.reload();
  });

  function poll(id) {
    fetch("/apps/tpc/import/" + encodeURIComponent(id), { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (job) {
        if (job.state === "running") {
          if (job.total) {
            bar.style.width = job.percent + "%";
            detail.textContent = "Downloading — " + job.percent + "%";
            bytes.textContent = mb(job.downloaded) + " of " + mb(job.total);
          } else {
            // No Content-Length: show movement, but never a made-up percentage.
            detail.textContent = "Downloading — size unknown";
            bytes.textContent = mb(job.downloaded) + " so far";
          }
          return;
        }
        if (job.state === "done") {
          bar.style.width = "100%";
          bytes.textContent = "";
          finish("Imported", (job.package_name || "The plugin") + " is in the local library.");
        } else {
          bytes.textContent = "";
          finish("Import failed", job.error || "The import did not complete.");
        }
      })
      .catch(function () { /* transient; the next tick retries */ });
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-tpc-import]");
    if (!btn) return;

    var body = new FormData();
    body.append("identifier", btn.getAttribute("data-identifier"));
    body.append("product", btn.getAttribute("data-product"));
    body.append("product_version", btn.getAttribute("data-product-version"));
    body.append("label", btn.getAttribute("data-label") || "");
    var token = document.querySelector('input[name="csrf_token"]');
    if (token) body.append("csrf_token", token.value);

    title.textContent = "Importing " + (btn.getAttribute("data-label") || "");
    detail.textContent = "Contacting tak.gov…";
    bytes.textContent = "";
    bar.style.width = "0";
    close.hidden = true;
    modal.hidden = false;

    fetch("/apps/tpc/import", { method: "POST", body: body })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, job: j }; }); })
      .then(function (res) {
        if (!res.ok || !res.job.id) {
          finish("Import failed", res.job.error || "The server refused to start the import.");
          return;
        }
        timer = setInterval(function () { poll(res.job.id); }, 700);
        poll(res.job.id);
      })
      .catch(function () { finish("Import failed", "Could not reach the server."); });
  });
})();

/* --- ATAK plugin compatibility -------------------------------------------
   A plugin only loads in the ATAK build it was compiled against. A mismatch is
   not a crash: the plugin installs and then never appears in ATAK, which looks
   like an MDM fault and is not one. So warn, never block.

   ⚠️ Anchored on the **ATAK Core select**, not on whichever row happens to be
   ATAK (W141). ATAK is the fixed point everything else is built against, and it
   is now chosen rather than inferred — required apps cannot contain it at all,
   so the old "find the ATAK row" rule would never fire again.

   ⚠️ Versions only. A CIV/MIL/GOV check lived here briefly and came out: MIL and
   GOV are not separate builds. A device runs ATAK-CIV and a flavour plugin
   unlocks the rest, so there is no second ATAK to be incompatible with. What a
   GOV or MIL plugin needs is that flavour plugin, which the TPC browser says. */
(function () {
  function lineOf(select) {
    if (!select) return null;
    var option = select.options[select.selectedIndex];
    if (!option) return null;
    return (
      option.getAttribute("data-atak-line") ||
      option.getAttribute("data-plugin-target") ||
      null
    );
  }

  function refresh() {
    var core = document.querySelector('select[name="atak_core__version_choice"]');
    var plugins = document.querySelector("[data-atak-plugins]");
    if (!plugins) return;

    // No ATAK chosen is an unknown, not a clean bill of health — and not a
    // reason to tell someone their plugin is wrong.
    var atakLine = lineOf(core);

    plugins.querySelectorAll(".rs-row").forEach(function (row) {
      var box = row.querySelector(".app-compat-warning");
      if (!box) return;
      box.hidden = true;

      var target = lineOf(row.querySelector('select[name$="__version_choice"]'));
      if (!atakLine || !target || target === atakLine) return;

      box.textContent =
        "This plugin is built for ATAK " + target + ", but this policy installs " +
        "ATAK " + atakLine + ". It is a mismatch and may not be compatible — it " +
        "will install, and ATAK may then refuse to load it. Assigning it anyway " +
        "is allowed.";
      box.hidden = false;
    });
  }

  // Delegated, because rows arrive from a <template> long after load and the
  // core select changes independently of them.
  document.addEventListener("change", refresh);
  document.addEventListener("click", function () { setTimeout(refresh, 0); });
  refresh();
})();

/* --- Wallpaper preview ------------------------------------------------------
   Shows the selected image in both orientations at the slot's real aspect
   ratio, cropped the way Android crops it. */
(function () {
  document.querySelectorAll("[data-image-slot]").forEach(function (slot) {
    var field = slot.querySelector("[data-image-select]");
    var preview = slot.querySelector("[data-image-preview]");
    var picker = slot.querySelector("[data-image-upload]");
    var status = slot.querySelector("[data-image-status]");
    var clear = slot.querySelector("[data-image-clear]");
    if (!field || !preview) return;

    function refresh() {
      var id = field.value;
      if (clear) clear.hidden = !id;
      if (!id) { preview.hidden = true; return; }
      // Cache-buster: replacing an image reuses the <img>, and without this the
      // browser shows the previous picture for the new id.
      var src = "/content/" + encodeURIComponent(id) + "/raw?v=" + encodeURIComponent(id);
      preview.querySelectorAll("img").forEach(function (img) { img.src = src; });
      preview.hidden = false;
    }

    function say(message) {
      if (status) status.textContent = message;
    }

    // Upload immediately on choosing a file, rather than at policy save: the
    // operator gets the preview — and any rejection — while they are still
    // looking at the picture they picked.
    if (picker) {
      picker.addEventListener("change", function () {
        var file = picker.files && picker.files[0];
        if (!file) return;

        var body = new FormData();
        body.append("file", file);
        var token = document.querySelector('input[name="csrf_token"]');
        if (token) body.append("csrf_token", token.value);

        say("uploading " + file.name + "…");
        fetch("/policies/image", { method: "POST", body: body })
          .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
          .then(function (res) {
            if (!res.ok || !res.body.id) {
              say(res.body.error || "upload failed");
              picker.value = "";
              return;
            }
            field.value = res.body.id;
            say(file.name);
            refresh();
          })
          .catch(function () {
            say("upload failed — could not reach the server");
            picker.value = "";
          });
      });
    }

    if (clear) {
      clear.addEventListener("click", function () {
        // Clears the slot on this policy only. The uploaded file is left alone:
        // another policy version may still point at it, and orphan cleanup is a
        // decision for the server, not a side effect of a click here.
        field.value = "";
        if (picker) picker.value = "";
        say("no image chosen");
        refresh();
      });
    }

    field.addEventListener("change", refresh);
    refresh();
  });
})();

/* --- TPC plugin filter ------------------------------------------------------
   Filters rows already on the page. The catalog is fetched once and every row is
   present, so there is nothing to ask the server for — and nothing to make the
   operator wait for between keystrokes.

   Matches across the whole row's text, which is the plugin name, its package name
   and its description: an operator hunting "video" should not have to know which
   of the three the word lives in. */
(function () {
  var box = document.querySelector("[data-plugin-filter]");
  var table = document.querySelector(".tpc-table");
  if (!box || !table) return;

  var body = table.tBodies[0];
  if (!body) return;

  var count = document.querySelector("[data-plugin-filter-count]");
  var total = document.querySelector("[data-plugin-total]");
  var rows = Array.from(body.rows).map(function (row) {
    return { row: row, text: (row.textContent || "").toLowerCase() };
  });

  function apply() {
    // Every whitespace-separated word must appear somewhere in the row, so
    // "uas 5.8" narrows rather than widening the way a single substring would.
    var terms = box.value.toLowerCase().split(/\s+/).filter(Boolean);
    var shown = 0;

    rows.forEach(function (entry) {
      var hit = terms.every(function (t) { return entry.text.indexOf(t) !== -1; });
      entry.row.hidden = !hit;
      if (hit) shown++;
    });

    if (total) total.hidden = terms.length > 0;
    if (count) {
      count.textContent = terms.length
        ? shown + " of " + rows.length + " plugin" + (rows.length === 1 ? "" : "s")
        : "";
    }
  }

  box.addEventListener("input", apply);
  // A browser restoring the field on back/reload must not leave a stale list.
  apply();
})();

  /* --- Single-app kiosk: app, or app with activity (W61) ---------------------
     Two radios decide whether the activity fields are on screen. The mode is not
     a stored field: it is derived on load from whether an activity class is
     already set, so there is no third piece of state to fall out of step with
     the two that are saved.

     ⚠️ Clearing the inputs on the way out is the point. Switching back to
     "Select app" has to actually mean it — a hidden input still submits, so an
     activity left behind would keep being sent while the operator could no
     longer see it. */
  (function () {
    var host = document.querySelector("[data-kiosk-app]");
    if (!host) return;

    var rows = {};
    ["kiosk_activity", "kiosk_restrict_to_activity"].forEach(function (name) {
      rows[name] = document.querySelector('.pf-field[data-field="' + name + '"]');
    });
    var activity = document.querySelector('[name="kiosk_activity"]');
    var restrict = document.querySelector('[name="kiosk_restrict_to_activity"]');

    function show(withActivity) {
      Object.keys(rows).forEach(function (name) {
        if (rows[name]) rows[name].hidden = !withActivity;
      });
      if (!withActivity) {
        if (activity) activity.value = "";
        if (restrict) restrict.value = "";
      }
    }

    var radios = host.querySelectorAll("[data-kiosk-mode]");
    radios.forEach(function (radio) {
      radio.addEventListener("change", function () {
        show(radio.value === "activity" && radio.checked);
      });
    });

    /* The activity list is a fact about the chosen build, so it is fetched rather
       than typed. Refilled whenever the app changes — an activity from the
       previously selected app is not a valid choice for this one. */
    var appSelect = host.querySelector('select[name="kiosk_package"]');
    var note = document.querySelector("[data-activity-note]");

    function loadActivities(keepValue) {
      if (!activity || activity.tagName !== "SELECT") return;
      var pkg = appSelect && appSelect.value;
      if (!pkg) {
        activity.innerHTML = '<option value="">— pick an app first —</option>';
        if (note) note.textContent = "";
        return;
      }
      if (note) note.textContent = "Reading the app…";
      fetch("/policies/app-activities?package=" + encodeURIComponent(pkg))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var list = data.activities || [];
          activity.innerHTML = '<option value="">— pick an activity —</option>';
          list.forEach(function (a) {
            var opt = document.createElement("option");
            opt.value = a.name;
            // The launcher marker is the useful distinction: it is the screen a
            // user would normally arrive at, and usually the one a kiosk wants.
            opt.textContent = a.name + (a.launcher ? "   (launcher)" : "");
            if (a.name === keepValue) opt.selected = true;
            activity.appendChild(opt);
          });
          if (note) {
            note.textContent = list.length
              ? list.length + " activities declared by this build"
              : "This build declares no activities — it has nothing to lock to.";
          }
        })
        .catch(function () {
          if (note) note.textContent = "Could not read this app's activities.";
        });
    }

    if (appSelect) {
      appSelect.addEventListener("change", function () { loadActivities(null); });
    }

    // Derived, not stored: a saved policy with an activity opens on that mode.
    var hasActivity = !!(activity && activity.value.trim());
    radios.forEach(function (r) { r.checked = (r.value === "activity") === hasActivity; });
    show(hasActivity);
    if (hasActivity) loadActivities(activity.value);
  })();
/* --- Countdown pills (W77) -------------------------------------------------
   <span data-countdown="900" data-countdown-expired="expired - ...">
     expires in <span data-countdown-value>15:00</span>
   </span>

   Counts down from a duration the server supplied, NOT towards a timestamp.
   The clock in this browser is not the server's, and one a few minutes out
   would show a confidently wrong answer to someone standing over a
   factory-reset tablet. A duration cannot be wrong that way.

   Driven by the wall clock rather than by counting ticks: a background tab is
   throttled to roughly one timer a minute, so a counter that decremented per
   tick would drift minutes behind over a 15-minute token and still claim to be
   live after it had expired. */

(function () {
  var pills = document.querySelectorAll("[data-countdown]");
  if (!pills.length) return;

  pills.forEach(function (pill) {
    var seconds = parseInt(pill.getAttribute("data-countdown"), 10);
    if (!(seconds > 0)) return;
    var value = pill.querySelector("[data-countdown-value]");
    if (!value) return;
    var endsAt = Date.now() + seconds * 1000;

    function paint() {
      var left = Math.round((endsAt - Date.now()) / 1000);
      if (left <= 0) {
        // The pill stops being a countdown and becomes the reason it is dead.
        // Leaving "0:00" on screen reads as a display that has stopped
        // updating, not as a token that has expired.
        pill.textContent = pill.getAttribute("data-countdown-expired") || "expired";
        pill.classList.remove("warn");
        pill.classList.add("bad");
        clearInterval(timer);
        return;
      }
      var m = Math.floor(left / 60);
      var s = left % 60;
      value.textContent = m + ":" + (s < 10 ? "0" : "") + s;
      // Under a minute is the point at which someone should stop starting a
      // new tablet and generate a fresh code instead.
      if (left <= 60) {
        pill.classList.remove("warn");
        pill.classList.add("bad");
      }
    }

    var timer = setInterval(paint, 1000);
    paint();
  });
})();


/* --- ATAK settings tables (W90) ---------------------------------------------
   ATAK 5.8.0.4 declares 293 settings across 48 screens; one plugin declares 158.
   That is a filtered, paged table — 50 rows a page — and not a form.

   The rows are built from the scanned APK rather than rendered server-side: the
   plugin's schema is not even known until the operator picks one, and the core
   table would otherwise be 293 rows of Jinja on every policy page whether or not
   anyone opens that sub-topic.

   ⚠️ Rows off the current page are **hidden, never removed or disabled**. A
   hidden input still submits; a removed one drops the operator's value the
   moment they turn a page, and a disabled one drops it on save. */

(function () {
  var PAGE_SIZE = 50;

  /* Values submit as two parallel lists — `<field>__key` and `<field>__value` —
     paired **by index** on the server. Emitting both inputs together on every
     row, in DOM order, is what keeps that pairing honest; a row that emitted
     only one of them would shift every pair after it onto the wrong setting. */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function valueControl(field, current) {
    var control;
    if (field.control === "bool" || (field.options && field.options.length)) {
      control = document.createElement("select");
      // "" is "not managed", and it is first so it is what an untouched row
      // holds. Without it every setting in the table would be managed the
      // moment it rendered, and saving would push all 293 at the fleet.
      control.appendChild(new Option("— not managed —", ""));
      if (field.control === "bool") {
        control.appendChild(new Option("True", "true"));
        control.appendChild(new Option("False", "false"));
      } else {
        field.options.forEach(function (option) {
          control.appendChild(new Option(option.label, option.value));
        });
      }
      // A saved value the current build no longer offers still has to be
      // selectable, or opening the policy would silently change it to unmanaged.
      if (current && !Array.prototype.some.call(control.options, function (o) {
        return o.value === current;
      })) {
        control.appendChild(new Option(current + " (not in this build)", current));
      }
      control.value = current || "";
    } else {
      control = document.createElement("input");
      control.type = field.control === "int" ? "number" : "text";
      control.value = current || "";
      // State, not a hint: what ATAK uses when this is left unmanaged (W92).
    control.placeholder = field.default ? "default: " + field.default : "";
    }
    return control;
  }

  /* Build the table into `host`, seeded from `values` ({key: value}).
     Returns { collect() } so a caller can read it back without touching DOM. */
  function buildTable(host, schema, values, fieldName) {
    var status = host.querySelector("[data-prefs-status]");
    var wrapper = host.querySelector("[data-prefs-table]");
    var body = host.querySelector("[data-prefs-body]");
    var filterBox = host.querySelector("[data-prefs-filter]");
    var count = host.querySelector("[data-prefs-count]");
    var pager = host.querySelector("[data-prefs-pager]");
    var pageLabel = host.querySelector("[data-prefs-page]");
    var prev = host.querySelector("[data-prefs-prev]");
    var next = host.querySelector("[data-prefs-next]");

    var rows = [];
    var declared = {};

    (schema.sections || []).forEach(function (section) {
      (section.fields || []).forEach(function (field) {
        declared[field.key] = true;
        rows.push(makeRow(field, section.title, values[field.key], fieldName, false));
      });
    });

    /* ⚠️ A setting the policy carries that this build no longer declares is kept,
       marked, and still editable — never dropped. ATAK renames and retires keys
       between releases, and quietly discarding one would change a live policy
       just because somebody opened it, with nothing on screen to say so. They go
       first, because they are the ones that need a decision. */
    var orphans = Object.keys(values).filter(function (key) { return !declared[key]; });
    orphans.sort().reverse().forEach(function (key) {
      rows.unshift(
        makeRow(
          { key: key, label: key, control: "str", options: [] },
          "Not in this build",
          values[key],
          fieldName,
          true
        )
      );
    });

    var visible = rows;
    var page = 0;

    /* Rows that are not on the current page live here — still inside the form,
       so their inputs still submit. Created before the first paint because
       `render` puts every row back into it before choosing the new window.

       A real (hidden) table, not a `div`: parking a `<tr>` inside a `<div>` is
       legal enough when done through `appendChild` and the inputs still submit,
       but it is invalid nesting to no purpose, and this is not the place to be
       relying on how forgiving a browser feels. */
    var holderTable = el("table");
    holderTable.hidden = true;
    var holder = el("tbody");
    holderTable.appendChild(holder);
    host.appendChild(holderTable);

    function render() {
      /* ⚠️ Reclaim first. Clearing the tbody without this orphans the rows that
         were on screen — they leave the document entirely, and with them the
         operator's unsaved values for that page. */
      rows.forEach(function (row) { holder.appendChild(row.tr); });
      body.textContent = "";
      if (!visible.length) {
        var empty = el("tr");
        var cell = el("td", "prefs-empty", rows.length
          ? "No setting matches that filter."
          : "This build declares no settings.");
        cell.colSpan = 3;
        empty.appendChild(cell);
        body.appendChild(empty);
      }

      var pages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
      if (page >= pages) page = pages - 1;
      var start = page * PAGE_SIZE;

      visible.slice(start, start + PAGE_SIZE).forEach(function (row) {
        body.appendChild(row.tr);
      });

      count.textContent =
        visible.length === rows.length
          ? rows.length + " setting" + (rows.length === 1 ? "" : "s")
          : visible.length + " of " + rows.length + " settings";
      pager.hidden = pages < 2;
      pageLabel.textContent = "Page " + (page + 1) + " of " + pages;
      prev.disabled = page === 0;
      next.disabled = page >= pages - 1;
    }

    function applyFilter() {
      var term = (filterBox.value || "").trim().toLowerCase();
      visible = term
        ? rows.filter(function (row) { return row.haystack.indexOf(term) !== -1; })
        : rows;
      page = 0;
      render();
    }

    filterBox.addEventListener("input", applyFilter);
    prev.addEventListener("click", function () { page -= 1; render(); });
    next.addEventListener("click", function () { page += 1; render(); });

    if (status) status.hidden = true;
    wrapper.hidden = false;
    render();

    return {
      collect: function () {
        var out = {};
        rows.forEach(function (row) {
          var value = (row.control.value || "").trim();
          if (value !== "") out[row.key] = value;
        });
        return out;
      },
      warn: function (messages) {
        if (!messages || !messages.length || !status) return;
        status.hidden = false;
        status.className = "banner warn";
        status.textContent = messages.join(" ");
      }
    };
  }

  function makeRow(field, sectionTitle, current, fieldName, unknown) {
    var tr = el("tr", unknown ? "prefs-row-unknown" : null);

    var setting = el("td", "prefs-setting");
    setting.appendChild(el("strong", null, field.label || field.key));
    setting.appendChild(el("code", "prefs-key", field.key));
    if (field.summary) setting.appendChild(el("div", "prefs-summary", field.summary));
    if (unknown) {
      setting.appendChild(
        el("div", "prefs-summary",
           "This policy sets it, but the build in the library no longer declares " +
           "it. Kept as it is until you change or clear it.")
      );
    }

    var valueCell = el("td", "prefs-value");
    var control = valueControl(field, current);
    // The pair. Both always present, in this order, on every row.
    /* ⚠️ Nameless when there is no field to submit into. The plugin picker's
       table is rendered *inside* the policy form, so named inputs there would
       post a hundred-odd stray pairs on every save — and into the core
       settings list, which is the one field whose names they would match. Its
       values are read back through `collect()` instead. */
    if (fieldName) {
      var keyInput = document.createElement("input");
      keyInput.type = "hidden";
      keyInput.name = fieldName + "__key";
      keyInput.value = field.key;
      control.name = fieldName + "__value";
      valueCell.appendChild(keyInput);
    }
    valueCell.appendChild(control);
    if (field.default != null && field.default !== "" && !(field.options || []).length) {
      valueCell.appendChild(el("div", "prefs-default", "ATAK default: " + field.default));
    }

    tr.appendChild(setting);
    tr.appendChild(valueCell);
    tr.appendChild(el("td", "prefs-group", sectionTitle || ""));

    return {
      tr: tr,
      key: field.key,
      control: control,
      haystack: ((field.label || "") + " " + field.key + " " + (sectionTitle || "")).toLowerCase()
    };
  }

  function fetchSchema(packageName) {
    var url = "/policies/pref-schema";
    if (packageName) url += "?package=" + encodeURIComponent(packageName);
    return fetch(url).then(function (r) { return r.json(); });
  }

  /* --- ATAK core settings --------------------------------------------------- */

  (function () {
    var host = document.querySelector("[data-atak-prefs]");
    if (!host) return;

    var fieldName = host.getAttribute("data-prefs-field");
    var fallback = host.querySelector("[data-prefs-fallback]");
    var status = host.querySelector("[data-prefs-status]");

    // Seeded from the hidden inputs the server rendered, so the table starts
    // from what the policy actually holds rather than from a second copy of it.
    var values = {};
    var keys = fallback.querySelectorAll('input[name="' + fieldName + '__key"]');
    var vals = fallback.querySelectorAll('input[name="' + fieldName + '__value"]');
    for (var i = 0; i < keys.length; i++) {
      values[keys[i].value] = vals[i] ? vals[i].value : "";
    }

    fetchSchema(null)
      .then(function (schema) {
        // ⚠️ Only now. Until the table exists, the fallback inputs are the only
        // thing carrying this policy's settings, and removing them earlier would
        // turn a failed fetch into a save that wipes the category.
        var table = buildTable(host, schema, values, fieldName);
        fallback.parentNode.removeChild(fallback);
        table.warn(schema.warnings);
        // The rail's completion checks ran long before this resolved, against
        // the fallback inputs that have just been replaced.
        //
        // ⚠️ `atlas:recount`, not `input`. This fires on *load*, with no
        // operator involvement, and a synthetic `input` here marked the form
        // dirty — so saving a policy and then navigating away warned about
        // unsaved changes that did not exist.
        host.dispatchEvent(new Event("atlas:recount", { bubbles: true }));
      })
      .catch(function () {
        if (!status) return;
        status.className = "banner bad";
        status.textContent =
          "Could not read ATAK's settings. The settings this policy already " +
          "carries are kept — saving now will not lose them — but nothing can " +
          "be added until this loads.";
      });
  })();

  /* --- Plugin settings ------------------------------------------------------ */

  (function () {
    var set = document.querySelector("[data-plugin-prefs]");
    if (!set) return;
    var frame = document.getElementById("plugin-prefs-frame");
    if (!frame) return;

    var picker = frame.querySelector("[data-plugin-prefs-package]");
    var mount = frame.querySelector("[data-plugin-prefs-host]");
    var save = frame.querySelector("[data-plugin-prefs-save]");
    var addBtn = set.querySelector("[data-plugin-prefs-add]");
    var table = null;
    var editing = null;

    function shell() {
      // The same markup the server renders for the core table, so both go
      // through one builder rather than two that can drift.
      mount.innerHTML =
        '<div class="banner" data-prefs-status>Reading the plugin’s settings…</div>' +
        '<div data-prefs-table hidden>' +
        '<div class="prefs-toolbar">' +
        '<input type="search" data-prefs-filter aria-label="Filter settings">' +
        '<p class="field-tip">Filter by name or key.</p>' +
        '<span class="muted" data-prefs-count></span></div>' +
        '<table class="prefs-table"><thead><tr>' +
        '<th class="prefs-setting">Setting</th><th class="prefs-value">Value</th>' +
        '<th class="prefs-group">Section</th></tr></thead>' +
        '<tbody data-prefs-body></tbody></table>' +
        '<div class="prefs-pager" data-prefs-pager hidden>' +
        '<button type="button" class="ghost" data-prefs-prev>← Previous</button>' +
        '<span class="muted" data-prefs-page></span>' +
        '<button type="button" class="ghost" data-prefs-next>Next →</button>' +
        "</div></div>";
    }

    function load(packageName, values) {
      table = null;
      save.disabled = true;
      if (!packageName) {
        mount.textContent = "";
        return;
      }
      shell();
      fetchSchema(packageName)
        .then(function (schema) {
          // No field name: these values never submit from inside the modal, they
          // are collected into the row's JSON on save.
          table = buildTable(mount, schema, values || {}, null);
          table.warn(schema.warnings || (schema.error ? [schema.error] : []));
          save.disabled = false;
        })
        .catch(function () {
          mount.textContent = "Could not read that plugin's settings.";
        });
    }

    addBtn.addEventListener("click", function () {
      editing = null;
      picker.value = "";
      picker.disabled = false;
      mount.textContent = "";
      save.disabled = true;
      frame.hidden = false;
    });

    set.addEventListener("click", function (event) {
      var button = event.target.closest("[data-plugin-prefs-edit]");
      if (!button) return;
      var row = button.closest(".rs-row");
      if (!row) return;
      editing = row;
      var pkg = row.querySelector('[name="plugin_prefs__package_name"]').value;
      var raw = row.querySelector('[name="plugin_prefs__values"]').value;
      var values = {};
      try { values = JSON.parse(raw) || {}; } catch (e) { values = {}; }
      picker.value = pkg;
      // The package is the row's identity — changing it here would silently
      // move a configuration from one plugin to another.
      picker.disabled = true;
      frame.hidden = false;
      load(pkg, values);
    });

    picker.addEventListener("change", function () { load(picker.value, {}); });

    save.addEventListener("click", function () {
      if (!table) return;
      var pkg = picker.value;
      if (!pkg) return;
      var values = table.collect();
      if (!Object.keys(values).length) {
        // A plugin with nothing chosen is refused rather than saved empty: an
        // empty entry still occupies the merge slot for that package, so it
        // would suppress a lower-ranked policy's real configuration.
        window.alert(
          "Choose at least one setting, or cancel — a plugin with no settings " +
          "cannot be saved."
        );
        return;
      }

      var row = editing;
      if (!row) {
        row = document.createElement("div");
        row.className = "rs-row";
        row.innerHTML =
          '<input type="hidden" name="plugin_prefs__package_name">' +
          '<input type="hidden" name="plugin_prefs__values">' +
          '<div style="flex:1"><strong></strong>' +
          '<span class="muted" style="font-size:12px"></span>' +
          '<div class="muted" style="font-size:12px" data-plugin-prefs-summary></div></div>' +
          '<button type="button" class="ghost" data-plugin-prefs-edit>Edit</button>' +
          '<button type="button" class="ghost" data-remove-row>Remove</button>';
        addBtn.insertAdjacentElement("beforebegin", row);
      }

      var count = Object.keys(values).length;
      row.querySelector('[name="plugin_prefs__package_name"]').value = pkg;
      row.querySelector('[name="plugin_prefs__values"]').value = JSON.stringify(values);
      row.querySelector("strong").textContent = pkg;
      row.querySelector(".muted").textContent =
        " · " + count + (count === 1 ? " setting" : " settings");
      var summary = row.querySelector("[data-plugin-prefs-summary]");
      if (summary) {
        summary.textContent = Object.keys(values)
          .map(function (k) { return k + "=" + values[k]; })
          .join(", ");
      }

      frame.hidden = true;
      editing = null;
    });
  })();
})();

/* --- Data packages (W91) ----------------------------------------------------
   Two small behaviours: the Create Data Package modal grows a file row on
   demand, and the policy editor's picker turns a chosen package into a row.

   ⚠️ The picker deliberately offers only packages the server validated at
   upload. An arbitrary zip would be unpacked by ATAK as a plain archive with
   none of the manifest's placement rules, and nothing in the console would say
   that had happened. */

(function () {
  var open = document.querySelector("[data-package-create-open]");
  var frame = document.getElementById("package-create");
  if (open && frame) {
    open.addEventListener("click", function () { frame.hidden = false; });

    var add = frame.querySelector("[data-package-add-file]");
    var list = frame.querySelector("[data-package-files]");
    if (add && list) {
      add.addEventListener("click", function () {
        var row = document.createElement("div");
        row.className = "rs-row";
        // Not `required`: only the first row must be filled, and an empty extra
        // row is a row the operator added and changed their mind about. The
        // server drops zero-byte parts for the same reason.
        row.innerHTML =
          '<input type="file" name="files">' +
          '<button type="button" class="ghost" data-remove-row>Remove</button>';
        list.appendChild(row);
      });
    }
  }

  var set = document.querySelector("[data-data-packages]");
  if (!set) return;
  var pick = set.querySelector("[data-package-pick]");
  var template = set.querySelector("[data-row-template]");
  if (!pick || !template) return;

  pick.addEventListener("change", function () {
    var id = pick.value;
    if (!id) return;
    var label = pick.options[pick.selectedIndex].textContent.trim();

    // Already on the policy? Adding it twice would be two rows the merge then
    // has to reconcile against one file, and the spec keys on file_id anyway.
    var existing = set.querySelectorAll('input[name="data_packages__file_id"]');
    for (var i = 0; i < existing.length; i++) {
      if (existing[i].value === id) { pick.value = ""; return; }
    }

    var row = template.content.firstElementChild.cloneNode(true);
    row.querySelector('[name="data_packages__file_id"]').value = id;
    var name = row.querySelector("[data-package-label]");
    if (name) name.textContent = label;
    pick.parentNode.insertAdjacentElement("beforebegin", row);
    pick.value = "";
  });
})();

/* --- Data packages from inside the policy editor (W91 B4) --------------------
   Upload a zip, or build one from loose files, without leaving the policy.

   ⚠️ Everything here posts by script and reports **inline**. The policy editor
   holds an entire unsaved policy; a form post or a redirect would take every
   other category's changes with it. Same reasoning as the wallpaper upload. */

(function () {
  var set = document.querySelector("[data-data-packages]");
  if (!set) return;

  var status = set.querySelector("[data-package-status]");
  var template = set.querySelector("[data-row-template]");
  var addBefore = set.querySelector("[data-package-pick]");
  var anchor = addBefore ? addBefore.parentNode : set.querySelector("[data-package-status]");

  function csrf(body) {
    var token = document.querySelector('input[name="csrf_token"]');
    if (token) body.append("csrf_token", token.value);
    return body;
  }

  function say(message, bad) {
    if (!status) return;
    status.textContent = message || "";
    status.style.color = bad ? "var(--bad)" : "";
  }

  /** Add a saved package to the policy, exactly as the picker would. */
  function addRow(id, name) {
    var existing = set.querySelectorAll('input[name="data_packages__file_id"]');
    for (var i = 0; i < existing.length; i++) {
      // Already on this policy. The spec keys on file_id, so a second row would
      // be one file described twice for the merge to reconcile.
      if (existing[i].value === id) return false;
    }
    var row = template.content.firstElementChild.cloneNode(true);
    row.querySelector('[name="data_packages__file_id"]').value = id;
    var label = row.querySelector("[data-package-label]");
    if (label) label.textContent = name;
    anchor.insertAdjacentElement("beforebegin", row);
    // The rail's completion check ran before this row existed.
    set.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }

  /* The manifest check gets its own modal. A refusal is the whole point of
     validating here, and a line of muted text beside the control is easy to miss
     on a page that holds an entire policy. */
  var upload = set.querySelector("[data-package-upload]");
  var openUpload = set.querySelector("[data-package-upload-open]");
  var check = document.getElementById("package-check");

  if (openUpload && upload) {
    openUpload.addEventListener("click", function () { upload.click(); });
  }

  if (upload && check) {
    var checkTitle = check.querySelector("[data-check-title]");
    var checkFile = check.querySelector("[data-check-file]");
    var checkProgress = check.querySelector("[data-check-progress]");
    var checkError = check.querySelector("[data-check-error]");
    var checkNote = check.querySelector("[data-check-note]");
    var checkClose = check.querySelector("[data-check-close]");

    function checking(fileName) {
      checkTitle.textContent = "Checking data package";
      checkFile.textContent = fileName;
      checkProgress.hidden = false;
      checkError.hidden = true;
      checkNote.hidden = true;
      checkClose.hidden = true;
      check.hidden = false;
    }

    function refused(message) {
      checkTitle.textContent = "Package refused";
      checkProgress.hidden = true;
      checkError.hidden = false;
      checkError.textContent = message;
      // Only for the manifest case: the note explains that ATAK would have taken
      // the file, which is reassurance for that refusal and noise for any other.
      checkNote.hidden = message.indexOf("MANIFEST") === -1;
      checkClose.hidden = false;
    }

    upload.addEventListener("change", function () {
      var file = upload.files && upload.files[0];
      if (!file) return;
      checking(file.name);

      var body = csrf(new FormData());
      body.append("file", file);
      fetch("/policies/data-package/upload", { method: "POST", body: body })
        .then(function (r) {
          return r.json().then(function (j) { return { ok: r.ok, body: j }; });
        })
        .then(function (res) {
          upload.value = "";
          if (!res.ok || !res.body.id) {
            // The server's words, not ours: it knows *why* the manifest failed.
            refused(res.body.error || "the upload failed");
            return;
          }
          // Accepted: close and let the new row be the confirmation, rather than
          // making the operator dismiss a dialog to see what they just added.
          check.hidden = true;
          addRow(res.body.id, res.body.name);
          var count = res.body.contents;
          say(res.body.name + " added" +
              (count ? " (" + count + (count === 1 ? " file)" : " files)") : ""));
        })
        .catch(function () {
          upload.value = "";
          refused("the upload failed");
        });
    });
  }

  var frame = document.getElementById("policy-package-create");
  var open = set.querySelector("[data-package-create-open]");
  if (!frame || !open) return;

  var nameField = frame.querySelector("[data-ppkg-name]");
  var descField = frame.querySelector("[data-ppkg-desc]");
  var fileList = frame.querySelector("[data-ppkg-files]");
  var addFile = frame.querySelector("[data-ppkg-add-file]");
  var save = frame.querySelector("[data-ppkg-save]");
  var error = frame.querySelector("[data-ppkg-error]");

  function fail(message) {
    error.hidden = false;
    error.textContent = message;
  }

  open.addEventListener("click", function () {
    nameField.value = "";
    descField.value = "";
    fileList.innerHTML = '<div class="rs-row"><input type="file" data-ppkg-file></div>';
    error.hidden = true;
    frame.hidden = false;
  });

  addFile.addEventListener("click", function () {
    var row = document.createElement("div");
    row.className = "rs-row";
    row.innerHTML =
      '<input type="file" data-ppkg-file>' +
      '<button type="button" class="ghost" data-remove-row>Remove</button>';
    fileList.appendChild(row);
  });

  save.addEventListener("click", function () {
    var body = csrf(new FormData());
    body.append("name", nameField.value || "");
    body.append("description", descField.value || "");

    var chosen = 0;
    fileList.querySelectorAll("[data-ppkg-file]").forEach(function (input) {
      if (input.files && input.files[0]) {
        body.append("files", input.files[0]);
        chosen += 1;
      }
    });
    if (!chosen) {
      // Refused here rather than round-tripping: the server says the same thing,
      // but the operator is looking at the empty rows right now.
      fail("Add at least one file.");
      return;
    }

    error.hidden = true;
    save.disabled = true;
    fetch("/policies/data-package/create", { method: "POST", body: body })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, body: j }; });
      })
      .then(function (res) {
        save.disabled = false;
        if (!res.ok || !res.body.id) {
          fail(res.body.error || "could not create the package");
          return;
        }
        addRow(res.body.id, res.body.name);
        say(res.body.name + " created");
        frame.hidden = true;
      })
      .catch(function () {
        save.disabled = false;
        fail("could not create the package");
      });
  });
})();

/* --- General Files: upload from inside the policy (W91 B6) -------------------
   The same shape as the data-package upload, minus the manifest check: this path
   carries a .pref, a certificate, a map source, a zip to extract. Posts by
   script and reports inline, because the editor holds an unsaved policy. */

(function () {
  var set = document.querySelector("[data-general-files]");
  if (!set) return;

  var open = set.querySelector("[data-file-upload-open]");
  var input = set.querySelector("[data-file-upload]");
  var status = set.querySelector("[data-file-upload-status]");
  var template = set.querySelector("[data-row-template]");
  var addRow = set.querySelector("[data-add-row]");
  if (!open || !input || !template || !addRow) return;

  function say(message, bad) {
    status.textContent = message || "";
    status.style.color = bad ? "var(--bad)" : "";
  }

  open.addEventListener("click", function () { input.click(); });

  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;
    say("Uploading " + file.name + "…");

    var body = new FormData();
    var token = document.querySelector('input[name="csrf_token"]');
    if (token) body.append("csrf_token", token.value);
    body.append("file", file);

    fetch("/policies/file/upload", { method: "POST", body: body })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, body: j }; });
      })
      .then(function (res) {
        input.value = "";
        if (!res.ok || !res.body.id) {
          say(res.body.error || "upload failed", true);
          return;
        }

        /* A new row for the file, with the destination left empty on purpose:
           where a file belongs is the operator's decision and there is no
           sensible default. The spec refuses an entry with no destination, so a
           forgotten one is caught at save rather than on a device. */
        var row = template.content.firstElementChild.cloneNode(true);
        var picker = row.querySelector("select");
        if (picker) {
          var option = document.createElement("option");
          option.value = res.body.id;
          option.textContent = res.body.name;
          option.selected = true;
          picker.appendChild(option);
        }
        addRow.parentNode.insertAdjacentElement("beforebegin", row);
        set.dispatchEvent(new Event("input", { bubbles: true }));
        say(res.body.name + " added — set its destination");
      })
      .catch(function () {
        input.value = "";
        say("upload failed", true);
      });
  });
})();

/* --- ATAK DTED uploads (W93) -------------------------------------------------
   The same shape as the data-package upload, checking a different layout.

   ⚠️ Why it is checked at all: a wrapped archive extracts perfectly on the
   device, puts every file on disk, and shows no terrain — ATAK unpacks DTED flat
   into one directory and looks nowhere else. There is nothing in a log
   afterwards, so the layout has to be caught while the operator still has the
   file in front of them. */

(function () {
  var set = document.querySelector("[data-dted-list]");
  if (!set) return;

  var open = set.querySelector("[data-dted-upload-open]");
  var input = set.querySelector("[data-dted-upload]");
  var status = set.querySelector("[data-dted-status]");
  var template = set.querySelector("[data-row-template]");
  var check = document.getElementById("package-check");
  if (!open || !input || !template) return;

  function say(message, bad) {
    status.textContent = message || "";
    status.style.color = bad ? "var(--bad)" : "";
  }

  open.addEventListener("click", function () { input.click(); });

  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;

    // Reuse the package check modal: same job, and a second dialog that looked
    // almost the same would be one more thing to keep in step.
    var title, progress, error, note, close;
    if (check) {
      title = check.querySelector("[data-check-title]");
      progress = check.querySelector("[data-check-progress]");
      error = check.querySelector("[data-check-error]");
      note = check.querySelector("[data-check-note]");
      close = check.querySelector("[data-check-close]");
      title.textContent = "Checking terrain archive";
      check.querySelector("[data-check-file]").textContent = file.name;
      progress.hidden = false;
      progress.innerHTML = "<p>Reading the archive and finding the cell folders. If they are nested, the archive is repacked so ATAK can see them — that can take a minute for a large one.</p>";
      error.hidden = true;
      note.hidden = true;
      close.hidden = true;
      check.hidden = false;
    }
    say("Checking " + file.name + "…");

    var body = new FormData();
    var token = document.querySelector('input[name="csrf_token"]');
    if (token) body.append("csrf_token", token.value);
    body.append("file", file);

    fetch("/policies/dted/upload", { method: "POST", body: body })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, body: j }; });
      })
      .then(function (res) {
        input.value = "";
        if (!res.ok || !res.body.id) {
          if (check) {
            title.textContent = "Archive refused";
            progress.hidden = true;
            error.hidden = false;
            error.textContent = res.body.error || "the upload failed";
            close.hidden = false;
          }
          say(res.body.error || "upload failed", true);
          return;
        }
        // A repack changed the operator's file, so the modal stays up and says
        // so. Silently handing back a different archive than the one uploaded is
        // how checksums stop matching with nobody knowing why.
        if (check) {
          if (res.body.repacked) {
            title.textContent = "Terrain repacked";
            progress.hidden = true;
            error.hidden = true;
            note.hidden = false;
            note.textContent = res.body.note;
            close.hidden = false;
          } else {
            check.hidden = true;
          }
        }

        var existing = set.querySelectorAll('input[name="dted_archives__file_id"]');
        for (var i = 0; i < existing.length; i++) {
          if (existing[i].value === res.body.id) { say(res.body.name + " is already on this policy"); return; }
        }
        var row = template.content.firstElementChild.cloneNode(true);
        row.querySelector('[name="dted_archives__file_id"]').value = res.body.id;
        var label = row.querySelector("[data-dted-label]");
        if (label) label.textContent = res.body.name;
        template.parentNode.insertBefore(row, template);
        set.dispatchEvent(new Event("input", { bubbles: true }));
        // The summary is the point: 11 cells is a different thing from 1, and
        // that is how someone notices they grabbed the wrong archive.
        say(res.body.name + " added — " + res.body.summary + (res.body.repacked ? " (repacked)" : ""));
      })
      .catch(function () {
        input.value = "";
        say("upload failed", true);
      });
  });
})();

/* --- App sources: search, inspect, import (W97, W101) -----------------------
   The compatibility facts are the point of this screen. R19 cost days because
   nobody could see, until it failed on a device, that a build was 32-bit only —
   so the version list says what each build carries before anything is fetched,
   and the import button is disabled when the server has already said no.

   Two panels share this: the 3rd party repositories, and Google Play on its own
   tab. They differ only in which search endpoint they call — everything after
   the results (versions, preflight, the import job) is identical, and the source
   travels on each row, so it is wired once rather than copied. */
function atlasWireAppSource(panelName, searchUrl) {
  var panel = document.querySelector('[data-tab-panel="' + panelName + '"]');
  if (!panel) return;

  var query = panel.querySelector("[data-repo-query]");
  // ⚠️ A panel can exist without a search bar (W145/W146). Google Play renders
  // no box until an account is linked, and this used to walk straight into
  // `.addEventListener` on null — which throws at the top level of this file
  // and stops every block *after* it from evaluating at all. One missing
  // control silently disabled the rest of the page's JavaScript.
  if (!query || !panel.querySelector("[data-repo-search]")) return;
  // ⚠️ There is no picker any more (W98). One bar searches everything, so the
  // source travels on the *row* — a version list or an import that guessed
  // would fetch a different build than the one the operator clicked.
  // ⚠️ Data attributes, not ids (W101). Two panels share this code, and two
  // elements cannot carry the same id — nor could `getElementById` tell which
  // panel's progress bar it had found once both existed.
  var status = panel.querySelector("[data-repo-status]");
  var results = panel.querySelector("[data-repo-results]");
  var modal = panel.querySelector("[data-repo-modal]");
  var modalTitle = panel.querySelector("[data-repo-modal-title]");
  var modalBody = panel.querySelector("[data-repo-modal-body]");
  var poll = null;

  function say(message, bad) {
    status.textContent = message || "";
    status.style.color = bad ? "var(--bad)" : "";
  }

  function csrf() {
    var token = document.querySelector('input[name="csrf_token"]');
    return token ? token.value : "";
  }

  function closeModal() {
    modal.hidden = true;
    if (poll) { clearInterval(poll); poll = null; }
  }

  panel.addEventListener("click", function (e) {
    if (e.target.closest("[data-repo-close]")) closeModal();
  });

  // --- search --------------------------------------------------------------

  function search() {
    var q = (query.value || "").trim();
    if (!q) { results.innerHTML = ""; say(""); return; }
    // Named for what it searches, not for one of the things it searches: this
    // bar covers four repositories, and the Play tab reuses the same code.
    say("Searching repos…");
    results.innerHTML = "";

    fetch(searchUrl + "?q=" + encodeURIComponent(q))
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) { say(res.body.error || "search failed", true); return; }
        var apps = res.body.apps || [];
        var problems = res.body.problems || [];

        // ⚠️ A source that failed is named, always — even when others answered.
        // Silence here would send someone hunting for an app that was found.
        if (problems.length) {
          var warn = document.createElement("p");
          warn.className = "field-tip";
          warn.style.color = "var(--bad)";
          warn.textContent = "⚠️ " + problems.map(function (p) {
            return p.label + ": " + p.error;
          }).join("  ·  ");
          results.appendChild(warn);
        }

        if (!apps.length) {
          say(problems.length ? "No results from the sources that answered."
                              : "Nothing matching " + q + ".");
          return;
        }
        say(apps.length + " result" + (apps.length === 1 ? "" : "s"));

        var table = document.createElement("table");
        table.innerHTML = "<thead><tr><th>App</th><th>Package</th><th>Source</th><th></th></tr></thead>";
        var body = document.createElement("tbody");
        apps.forEach(function (app) {
          var row = document.createElement("tr");
          var name = document.createElement("td");
          name.innerHTML = "<strong></strong><div class='muted' style='font-size:12px'></div>";
          name.querySelector("strong").textContent = app.name;
          name.querySelector("div").textContent = app.summary || "";
          var pkg = document.createElement("td");
          pkg.className = "mono";
          pkg.textContent = app.package_name;
          // Where it came from, on the row itself — the sources differ in what
          // they can promise, so a result without its origin is half a fact.
          var src = document.createElement("td");
          var badge = document.createElement("span");
          badge.className = app.verifiable ? "pill good" : "pill";
          badge.textContent = app.source_label || app.source;
          badge.title = app.verifiable
            ? "Publishes a digest this download is checked against."
            : "Publishes no checksum; the file is checked after it arrives.";
          src.appendChild(badge);

          var act = document.createElement("td");
          var button = document.createElement("button");
          button.type = "button";
          button.className = "ghost";
          // ⚠️ A source that cannot enumerate versions (Google Play) gets a
          // straight Import. Its "version list" is a single placeholder with no
          // code, no name and no architecture, so a picker there asks the
          // operator to choose from one blank row (W125).
          if (app.picks_version === false) {
            button.textContent = "Import";
            button.addEventListener("click", function () { importLatest(app); });
          } else {
            button.textContent = "Versions";
            button.addEventListener("click", function () { openVersions(app); });
          }
          act.appendChild(button);
          row.appendChild(name); row.appendChild(pkg); row.appendChild(src); row.appendChild(act);
          body.appendChild(row);
        });
        table.appendChild(body);
        results.appendChild(table);
      })
      .catch(function () { say("search failed", true); });
  }

  panel.querySelector("[data-repo-search]").addEventListener("click", search);
  query.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); search(); }
  });

  // --- versions ------------------------------------------------------------

  function architecture(version) {
    // ⚠️ Three states, as everywhere else this is shown (W96): the index may
    // declare architectures, declare none, or say nothing at all.
    if (version.abis === null) return "<span class='muted'>not stated</span>";
    if (!version.abis.length) return "<span class='pill good'>any</span>";
    return "<span class='mono'>" + version.abis.join(", ") + "</span>";
  }

  /**
   * Import from a source that has only one thing to offer (W125).
   *
   * Still asks the server for the version rather than inventing one: the
   * placeholder carries the download URL and the source name the import
   * endpoint needs, and fabricating those on the client would put knowledge of
   * a server-side URL scheme into the browser.
   */
  function importLatest(app) {
    modalTitle.textContent = app.name + " — " + (app.source_label || app.source);
    modalBody.innerHTML = "<p class='muted'>Starting…</p>";
    modal.hidden = false;

    fetch("/apps/repo/versions?source=" + encodeURIComponent(app.source) +
          "&package=" + encodeURIComponent(app.package_name))
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        var versions = (res.body && res.body.versions) || [];
        if (!res.ok || !versions.length) {
          modalBody.innerHTML = "<p style='color:var(--bad)'></p>";
          modalBody.querySelector("p").textContent =
            (res.body && res.body.error) || "nothing to download";
          return;
        }
        startImport(app, versions[0]);
      })
      .catch(function () {
        modalBody.innerHTML = "<p style='color:var(--bad)'>could not reach the source</p>";
      });
  }

  function openVersions(app) {
    modalTitle.textContent = app.name + " — " + (app.source_label || app.source);
    modalBody.innerHTML = "<p class='muted'>Reading versions…</p>";
    modal.hidden = false;

    fetch("/apps/repo/versions?source=" + encodeURIComponent(app.source) +
          "&package=" + encodeURIComponent(app.package_name))
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          modalBody.innerHTML = "<p style='color:var(--bad)'></p>";
          modalBody.querySelector("p").textContent = res.body.error || "could not read versions";
          return;
        }
        renderVersions(app, res.body.versions || []);
      })
      .catch(function () {
        modalBody.innerHTML = "<p style='color:var(--bad)'>could not read versions</p>";
      });
  }

  function renderVersions(app, versions) {
    modalBody.innerHTML = "";
    if (!versions.length) {
      modalBody.innerHTML = "<p class='muted'>No downloadable builds.</p>";
      return;
    }

    var table = document.createElement("table");
    table.innerHTML =
      "<thead><tr><th>versionCode</th><th>Version</th><th>Architecture</th>" +
      "<th>Needs</th><th></th></tr></thead>";
    var body = document.createElement("tbody");

    versions.forEach(function (v) {
      var row = document.createElement("tr");
      row.innerHTML =
        "<td class='mono'>" + (v.version_code === null ? "—" : v.version_code) + "</td>" +
        "<td>" + (v.version_name || "—") + "</td>" +
        "<td>" + architecture(v) + "</td>" +
        "<td class='muted'>" + (v.min_sdk ? "API " + v.min_sdk : "—") + "</td>";

      var act = document.createElement("td");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "ghost";
      button.textContent = "Import";
      if (v.blocking && v.blocking.length) {
        // Already refused by the server, so the button says why rather than
        // inviting a click that cannot succeed.
        button.disabled = true;
        button.title = v.blocking[0];
        button.textContent = "Refused";
      } else {
        button.addEventListener("click", function () { startImport(app, v); });
      }
      act.appendChild(button);
      row.appendChild(act);
      body.appendChild(row);

      var notes = (v.blocking || []).concat(v.warnings || []);
      if (notes.length) {
        var noteRow = document.createElement("tr");
        var cell = document.createElement("td");
        cell.colSpan = 5;
        cell.style.paddingTop = "0";
        notes.forEach(function (text, i) {
          var p = document.createElement("p");
          p.className = "field-tip";
          p.style.margin = "2px 0";
          if (v.blocking && i < v.blocking.length) p.style.color = "var(--bad)";
          p.textContent = (v.blocking && i < v.blocking.length ? "⚠️ " : "") + text;
          cell.appendChild(p);
        });
        noteRow.appendChild(cell);
        body.appendChild(noteRow);
      }
    });

    table.appendChild(body);
    modalBody.appendChild(table);
  }

  // --- import --------------------------------------------------------------

  function startImport(app, version) {
    // ⚠️ Google Play publishes no versionCode until the file has been
    // downloaded and read, so this was rendering "Importing Google Chrome
    // null…" for every Play import (W124). The version is decoration here —
    // the operator already knows what they clicked — so it is omitted rather
    // than faked.
    var label = version.version_code || version.version_name || "";
    modalBody.innerHTML =
      "<p data-repo-headline></p>" +
      // The stylesheet's .progress expects a <span> child; reused rather than
      // inventing a second bar style.
      "<div class='progress'><span data-repo-bar></span></div>" +
      "<p class='muted' data-repo-progress></p>";
    // textContent, not interpolation: an app name is whatever the source says
    // it is, and this one arrives from a search result.
    modalBody.querySelector("[data-repo-headline]").textContent =
      "Importing " + app.name + (label ? " " + label : "") + "…";

    var body = new FormData();
    body.append("csrf_token", csrf());
    body.append("source", app.source);
    body.append("package", app.package_name);
    body.append("version_key", version.version_key);
    body.append("label", app.name);

    fetch("/apps/repo/import", { method: "POST", body: body })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok || !res.body.id) {
          modalBody.innerHTML = "<p style='color:var(--bad)'></p>";
          modalBody.querySelector("p").textContent = res.body.error || "import failed";
          return;
        }
        watch(res.body.id);
      })
      .catch(function () {
        modalBody.innerHTML = "<p style='color:var(--bad)'>import failed</p>";
      });
  }

  function watch(jobId) {
    if (poll) clearInterval(poll);
    poll = setInterval(function () {
      fetch("/apps/repo/import/" + jobId)
        .then(function (r) { return r.json(); })
        .then(function (job) {
          // Scoped to this panel's modal, so two open tabs cannot cross wires.
          var bar = modalBody.querySelector("[data-repo-bar]");
          var text = modalBody.querySelector("[data-repo-progress]");
          var headline = modalBody.querySelector("[data-repo-headline]");
          if (bar && job.total) bar.style.width = job.percent + "%";
          if (text) {
            // ⚠️ A source that cannot state a size still reports bytes, so the
            // operator sees movement rather than a frozen "downloading…".
            // apkeep offers no total at all, and inventing a denominator to
            // make the bar advance would be a worse answer than no bar (W127).
            var mb = function (n) { return (n / 1048576).toFixed(1) + " MB"; };
            if (job.total) {
              text.textContent = job.percent + "% of " + mb(job.total);
            } else if (job.downloaded) {
              text.textContent = mb(job.downloaded) + " so far — size unknown";
            } else {
              text.textContent = "starting…";
            }
          }
          if (job.state === "done") {
            clearInterval(poll); poll = null;
            // ⚠️ Reads exactly like the tak.gov plugin importer's success
            // (W126). That one says "Imported" / "<pkg> is in the local
            // library" and leaves the bar full; this one announced the *hold*
            // in the title position and threw the bar away, so the same
            // outcome looked like two different things depending on which tab
            // the operator came from. Holding is the normal result of every
            // import — it belongs on the Apps page, which now states it, not
            // in the one line confirming the download worked.
            modalTitle.textContent = "Imported";
            if (bar) bar.style.width = "100%";
            if (text) text.textContent = "";
            if (headline) {
              headline.textContent =
                (job.package_name || job.label || "The package") +
                " is in the local library.";
            }
          } else if (job.state === "failed") {
            clearInterval(poll); poll = null;
            modalBody.innerHTML = "<p style='color:var(--bad)'></p>";
            modalBody.querySelector("p").textContent = job.error || "import failed";
          }
        })
        .catch(function () { /* keep polling; a dropped poll is not a failure */ });
    }, 1000);
  }
}

atlasWireAppSource("repo", "/apps/repo/search");
atlasWireAppSource("play", "/apps/play/search");

/*
 * A geofence lock needs a password policy beside it (W106).
 *
 * ⚠️ **The select is greyed, never `disabled`.** A disabled select submits
 * nothing, and these rows are paired by position — so disabling one would shift
 * every later fence's password setting onto the wrong row. That is the same trap
 * the kiosk favourites carry a note about, and it would arrive here as a fence
 * demanding a lock that nobody set. Greying is a CSS state plus a forced value;
 * the control keeps submitting.
 *
 * ⚠️ **This is a convenience, not the enforcement.** The server refuses the same
 * combination on save, and has to: a greyed control is a suggestion to anyone
 * with developer tools. The test below is deliberately the same one the server
 * makes — "does the Password panel have any value at all" — because an untouched
 * password section parses to an empty spec, which is exactly what the server
 * treats as "no password policy".
 */
function atlasWireFenceLock() {
  var selects = document.querySelectorAll('select[name$="__password_enforced"]');
  if (!selects.length) return;

  var panel = document.querySelector('[data-page-panel^="password:"]');
  var note = document.querySelector("[data-fence-lock-note]");

  function passwordPolicySet() {
    // No Password panel on the page at all (editing a lone policy): there is
    // nothing this fence could be travelling with.
    if (!panel) return false;
    var fields = panel.querySelectorAll("input, select, textarea");
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      if (el.type === "hidden" || el.disabled) continue;
      if ((el.value || "").trim() !== "") return true;
    }
    return false;
  }

  function refresh() {
    var allowed = passwordPolicySet();
    selects.forEach(function (select) {
      select.classList.toggle("greyed", !allowed);
      // Forced rather than left showing "Yes" against a rule that would refuse
      // the save: the control should never display a state the server rejects.
      if (!allowed) select.value = "no";
    });
    if (note) note.hidden = allowed;
  }

  if (panel) {
    panel.addEventListener("input", refresh);
    panel.addEventListener("change", refresh);
  }
  // New fence rows arrive from the rowset template already greyed or not.
  document.addEventListener("click", function (event) {
    if (event.target && event.target.hasAttribute("data-add-row")) {
      window.setTimeout(function () {
        selects = document.querySelectorAll('select[name$="__password_enforced"]');
        refresh();
      }, 0);
    }
  });

  refresh();
}

atlasWireFenceLock();


/* --- App-store shortcuts for the blocklist (W153) ---------------------------
   <div data-store-toggles> holds checkboxes carrying data-packages="a,b,c".
   Ticking one writes those packages into the sibling [data-rowset]; unticking
   removes exactly those rows and nothing else.

   ⚠️ The packages go into the visible list rather than into a stored flag. An
   operator can then read what will actually be blocked, add a store we missed,
   or drop one that is wrong for their fleet — none of which is possible if the
   expansion happens somewhere they cannot see.

   ⚠️ A box is ticked on load only when *every* one of its packages is already
   present. Half a group is not the group, and showing it ticked would claim a
   store is blocked when one of its packages is missing.
*/
(function () {
  "use strict";

  function rowsetFor(toggles) {
    var parent = toggles.parentElement;
    return parent ? parent.querySelector("[data-rowset]") : null;
  }

  function packagesOf(box) {
    return (box.getAttribute("data-packages") || "")
      .split(",").map(function (p) { return p.trim(); }).filter(Boolean);
  }

  function present(rowset) {
    var found = [];
    rowset.querySelectorAll(".rs-row input[type=text]").forEach(function (input) {
      var v = (input.value || "").trim();
      if (v) found.push(v);
    });
    return found;
  }

  function addPackage(rowset, name) {
    var template = rowset.querySelector("[data-row-template]");
    if (!template) return;
    /* An empty row the operator has not filled in yet is reused rather than
       left stranded above the ones we add. */
    var blank = null;
    rowset.querySelectorAll(".rs-row input[type=text]").forEach(function (input) {
      if (!blank && !(input.value || "").trim()) blank = input;
    });
    if (blank) { blank.value = name; return; }
    var row = template.content.firstElementChild.cloneNode(true);
    var field = row.querySelector("input[type=text]");
    if (field) field.value = name;
    rowset.insertBefore(row, template);
  }

  function removePackage(rowset, name) {
    rowset.querySelectorAll(".rs-row").forEach(function (row) {
      var input = row.querySelector("input[type=text]");
      if (input && (input.value || "").trim() === name) row.remove();
    });
  }

  function sync(box, rowset) {
    var have = present(rowset);
    var wanted = packagesOf(box);
    box.checked = wanted.length > 0 && wanted.every(function (p) {
      return have.indexOf(p) !== -1;
    });
  }

  document.querySelectorAll("[data-store-toggles]").forEach(function (toggles) {
    var rowset = rowsetFor(toggles);
    if (!rowset) return;
    var boxes = toggles.querySelectorAll("[data-store-group]");

    boxes.forEach(function (box) { sync(box, rowset); });

    toggles.addEventListener("change", function (event) {
      var box = event.target.closest("[data-store-group]");
      if (!box) return;
      var wanted = packagesOf(box);
      if (box.checked) {
        var have = present(rowset);
        wanted.forEach(function (name) {
          if (have.indexOf(name) === -1) addPackage(rowset, name);
        });
      } else {
        wanted.forEach(function (name) { removePackage(rowset, name); });
      }
      /* Another group may share a package, so re-read them all rather than
         trusting the one that changed. */
      boxes.forEach(function (other) { sync(other, rowset); });
    });

    /* Editing the list by hand is the authority: a box reflects the rows, so
       deleting one package unticks its group rather than lying about it. */
    rowset.addEventListener("input", function () {
      boxes.forEach(function (box) { sync(box, rowset); });
    });
    rowset.addEventListener("click", function (event) {
      if (!event.target.closest("[data-remove-row]")) return;
      setTimeout(function () {
        boxes.forEach(function (box) { sync(box, rowset); });
      }, 0);
    });
  });
})();
