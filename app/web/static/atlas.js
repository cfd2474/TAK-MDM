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
    var fromHash = (location.hash || "").replace(/^#tab-/, "");
    var initial =
      (fromHash && container.querySelector('[data-tab="' + CSS.escape(fromHash) + '"]') && fromHash) ||
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
    panelsRoot.querySelectorAll(".rs-row").forEach(function (row) {
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
        function (el) { return !el.disabled && el.name !== "csrf_token" && el.type !== "file"; }
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
    // A removed row fires no event of its own, and an added one is empty until
    // typed into; both still need the rail to catch up.
    panelsRoot.addEventListener("click", function () { setTimeout(refresh, 0); });
    refresh();
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
            search.placeholder = "Filter " + schema.keys.length + " keys…";
            search.style.marginBottom = "12px";
            search.addEventListener("input", function () {
              var q = search.value.trim().toLowerCase();
              fields.querySelectorAll("[data-config-field]").forEach(function (row) {
                row.hidden = q !== "" &&
                  row.getAttribute("data-config-field").toLowerCase().indexOf(q) === -1;
              });
            });
            fields.appendChild(search);
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

  /* --- Version choices belong to the app that was picked (W51) ----------------
     Every option already carried `data-package`; nothing ever read it, so the
     dropdown listed every version of every app at once — including builds of
     apps the row has nothing to do with, which is an easy way to pin the wrong
     one. Now it is empty until an app is chosen, and then shows only that app's.

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
      var latest = all.filter(function (o) { return !o.getAttribute("data-package"); });

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
          var owner = o.getAttribute("data-package");
          return !owner || owner === pkg;
        });
        choice.disabled = false;
        wanted.forEach(function (o) { choice.appendChild(o); });

        // Keep the saved choice when it still belongs to this app; otherwise fall
        // back to "Latest published" rather than silently keeping a pin that now
        // points at some other app's build.
        if (keepValue && wanted.some(function (o) { return o.value === keepValue; })) {
          choice.value = keepValue;
        } else if (latest.length) {
          choice.value = latest[0].value;
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
      if (row) row.remove();
    }
  });

  /* --- Insert an app group's packages into a required_apps JSON textarea -------
     Used by the profile editor's App Management section. Merges by package name so
     pressing a button twice does not duplicate entries. */

  /* Append a row per package in an app group to the named row-set (e.g.
     required_apps), skipping packages that already have a row. */
  window.atlasAddAppGroup = function (fieldName, packageNames) {
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
  };

  /* --- Confirm before submit --------------------------------------------------
     <form data-confirm="This retires the token. Continue?"> */

  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
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
   like an MDM fault and is not one. So warn, never block — and warn on the
   plugin, since ATAK is the fixed point everything else is built against. */
(function () {
  var blob = document.querySelector("[data-app-compat]");
  if (!blob) return;

  var compat;
  try { compat = JSON.parse(blob.textContent); } catch (e) { return; }

  function lineFor(row) {
    var pkg = row.querySelector('select[name$="__package_name"]');
    var ver = row.querySelector('select[name$="__version_choice"]');
    if (!pkg || !pkg.value) return null;
    var entry = compat[pkg.value];
    if (!entry) return null;
    var choice = ver ? ver.value : "";
    if (choice.indexOf("pin:") === 0) {
      // A pinned build names itself; "latest" and a floor both resolve to the
      // newest published one.
      return { pkg: pkg.value, atak: entry.is_atak, line: entry.pins[choice.slice(4)] || null };
    }
    return { pkg: pkg.value, atak: entry.is_atak, line: entry.latest };
  }

  function refresh(scope) {
    var rows = Array.from(scope.querySelectorAll(".rs-row"));
    var infos = rows.map(lineFor);

    // ATAK is the truth. If the policy does not install it, there is nothing to
    // compare against here and the device view is the place that knows.
    var atak = infos.find(function (i) { return i && i.atak && i.line; });

    rows.forEach(function (row, i) {
      var box = row.querySelector(".app-compat-warning");
      if (!box) return;
      var info = infos[i];
      box.hidden = true;
      if (!atak || !info || info.atak || !info.line) return;
      if (info.line === atak.line) return;
      box.textContent =
        info.pkg + " is built for ATAK " + info.line + ", but this policy installs ATAK " +
        atak.line + ". ATAK loads only plugins built for its own version, so this one " +
        "will install and then not appear. Assigning it anyway is allowed.";
      box.hidden = false;
    });
  }

  document.querySelectorAll("[data-rowset]").forEach(function (scope) {
    if (!scope.querySelector(".app-compat-warning")) return;
    scope.addEventListener("change", function () { refresh(scope); });
    scope.addEventListener("click", function () { setTimeout(function () { refresh(scope); }, 0); });
    refresh(scope);
  });
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
