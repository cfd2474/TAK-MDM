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
     A click on the backdrop, the [data-modal-close] control, or Escape closes it.

     ⚠️ **Unless the backdrop carries `data-modal-locked`** (W276). A modal
     showing work in progress -- an upload -- must not vanish on a stray click:
     hiding it left the page live underneath, and the next click on a link
     navigated away and killed the transfer. A locked modal closes only through
     its own controls, which decide what closing means. */

  function openModal(id) {
    var el = document.getElementById(id);
    if (el) el.hidden = false;
  }
  function closeModal(el) {
    if (el && !el.hasAttribute("data-modal-locked")) el.hidden = true;
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

  // A seam for navigation, so a test can see where the page would go (W316).
  window.atlasNavigate = window.atlasNavigate || function (url) { window.location.assign(url); };

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
      // ⚠️ W316: a tab marked `data-tab-refresh` reloads onto itself, so it is
      // rendered from current data. Imports on other tabs change the library
      // without a reload, and a switched-in-place App groups tab then offered
      // a stale list. Not when it is already the open tab: that is a no-op.
      if (btn.hasAttribute("data-tab-refresh") && !btn.classList.contains("on")) {
        window.atlasNavigate(location.pathname + "?tab=" + encodeURIComponent(name) +
                             "#tab-" + encodeURIComponent(name));
        return;
      }
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

  /* --- Find a setting without knowing its section (W201) ---------------------
     A KIOSK policy has well over a hundred fields across a dozen rail sections,
     and until now the only way to reach one was to remember where it lived. The
     rail answers "what have I filled in?"; this answers "where is the thing I am
     looking for?".

     ⚠️ **The index is the page.** Every panel is rendered on load and merely
     hidden, so the labels, help text and merge hints read here are exactly the
     ones in front of the operator. Nothing is fetched and nothing is duplicated
     on the server, where a second copy would be free to disagree.

     ⚠️ **Selecting a result clicks the rail.** `showPage` is a closure inside
     the rail's own initialiser, and reimplementing panel switching here would be
     a second navigation free to drift from the first. Triggering the same
     `[data-page]` click a person would is the whole of it. */

  (function () {
    var box = document.querySelector("[data-policy-search]");
    if (!box) return;

    var input = box.querySelector("[data-policy-search-input]");
    var list = box.querySelector("[data-policy-search-results]");
    var note = box.querySelector("[data-policy-search-note]");
    if (!input || !list) return;

    var LIMIT = 12;

    // Built once: the panels do not change without a page load.
    var index = [];
    document.querySelectorAll("[data-page-panel]").forEach(function (panel) {
      var key = panel.getAttribute("data-page-panel");
      var heading = panel.querySelector("h2");
      // ⚠️ A single-page policy type renders no <h2>, because there is no rail
      // to disambiguate. Such a result says the field name and nothing else,
      // which is honest: there is only one section to be in.
      var section = heading ? (heading.textContent || "").trim() : "";

      panel.querySelectorAll(".pf-field").forEach(function (field) {
        var label = field.querySelector(".pf-label label");
        var title = label ? (label.textContent || "").trim() : "";
        var name = field.getAttribute("data-field") || "";
        // The help text and the merge hint, which is where most of the words an
        // operator remembers actually live.
        var blurb = "";
        field.querySelectorAll(".pf-label .muted").forEach(function (m) {
          blurb += " " + (m.textContent || "");
        });
        if (!title && !name) return;
        index.push({
          field: field,
          key: key,
          section: section,
          title: title || name,
          // ⚠️ The field's own name is searchable on purpose: half of what an
          // operator has to go on is a key they saw in a spec or an error
          // message, not the label we chose to show them.
          haystack: (title + " " + name + " " + blurb).toLowerCase(),
        });
      });
    });

    var shown = [];

    function clear() {
      list.innerHTML = "";
      list.hidden = true;
      note.hidden = true;
      shown = [];
    }

    function render(term) {
      var needle = term.trim().toLowerCase();
      list.innerHTML = "";
      shown = [];
      if (needle.length < 2) {
        // One character matches most of the page, which is noise rather than help.
        clear();
        return;
      }

      var hits = index.filter(function (entry) {
        return entry.haystack.indexOf(needle) >= 0;
      });

      if (!hits.length) {
        list.hidden = true;
        note.textContent = "Nothing in this policy matches \u201c" + term.trim() + "\u201d.";
        note.hidden = false;
        return;
      }

      note.hidden = hits.length <= LIMIT;
      if (!note.hidden) {
        note.textContent =
          "Showing " + LIMIT + " of " + hits.length + " matches — keep typing to narrow it.";
      }

      hits.slice(0, LIMIT).forEach(function (entry, i) {
        var li = document.createElement("li");
        var button = document.createElement("button");
        button.type = "button";
        button.className = "policy-search-hit";
        button.setAttribute("data-policy-search-hit", String(i));
        var strong = document.createElement("strong");
        strong.textContent = entry.title;
        button.appendChild(strong);
        if (entry.section) {
          var span = document.createElement("span");
          span.className = "muted";
          span.textContent = " — " + entry.section;
          button.appendChild(span);
        }
        li.appendChild(button);
        list.appendChild(li);
        shown.push(entry);
      });
      list.hidden = false;
    }

    function go(entry) {
      if (!entry) return;

      // ⚠️ The rail, not a reimplementation of it. A single-page policy type has
      // no rail and its panel is already visible, so a missing link is normal
      // rather than a failure.
      var link = document.querySelector('[data-rail] [data-page="' + entry.key + '"]');
      if (link) link.click();

      clear();
      input.value = "";

      // After the click, so the panel is visible and has a box to scroll to.
      if (entry.field.scrollIntoView) {
        entry.field.scrollIntoView({ block: "center" });
      }
      // A flash rather than a permanent mark: the eye needs to land on the right
      // row, and a highlight left behind would read as a validation error.
      entry.field.classList.add("pf-found");
      setTimeout(function () { entry.field.classList.remove("pf-found"); }, 2000);
    }

    input.addEventListener("input", function () { render(input.value); });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        clear();
        input.value = "";
        return;
      }
      // Enter takes the first hit, which is the whole interaction for anyone who
      // typed enough to be sure.
      if (e.key === "Enter") {
        e.preventDefault();
        go(shown[0]);
      }
    });

    list.addEventListener("click", function (e) {
      var hit = e.target.closest("[data-policy-search-hit]");
      if (!hit) return;
      e.preventDefault();
      go(shown[parseInt(hit.getAttribute("data-policy-search-hit"), 10)]);
    });
  })();

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
    // ⚠️ ...and the ATLAS console tile is the same trap one step along (W197).
    // It renders on every kiosk page including a brand-new one, so counting it
    // as saved content would put a green check on a Kiosk section nobody has
    // touched — and the save would then drop the whole list, because a console
    // on its own is not a multi-app kiosk. The row is real; it is just not
    // evidence of anything.
    panelsRoot
      .querySelectorAll("[data-rowset] .rs-row:not([data-console-tile])")
      .forEach(function (row) {
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
    // Editing (W292): the row being edited, the values it held, and the saved
    // keys this build no longer declares -- kept, never silently dropped.
    var editing = null;
    var preset = null;
    var kept = {};
    // W357: a bundle's saved settings this build no longer declares, per bundle,
    // kept like `kept`; and which keys of the open schema are bundles.
    var keptInner = {};
    var bundleKeys = {};

    // Set one control from a saved value (top-level key or a bundle's child).
    function setControl(el, v) {
      if (el.hasAttribute("data-config-multi")) {
        var chosen = v.split("\n").filter(function (x) { return x !== ""; });
        el.querySelectorAll("input[type=checkbox]").forEach(function (box) {
          box.checked = chosen.indexOf(box.value) !== -1;
        });
        return;
      }
      if (el.tagName === "SELECT" &&
          !Array.prototype.some.call(el.options, function (o) { return o.value === v; })) {
        // A value this build no longer offers is kept, visibly, not lost.
        var extra = document.createElement("option");
        extra.value = v;
        extra.textContent = v + "  (saved value)";
        el.appendChild(extra);
      }
      el.value = v;
    }

    // What one control holds, or null when the operator left it alone.
    function readControl(el) {
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
        return picked.length ? picked.join("\n") + "\n" : null;
      }
      var v = (el.value || "").trim();
      // Only what the operator actually set: an empty control means "leave this
      // key alone", not "send an empty string", which an app would act on.
      return v !== "" ? v : null;
    }

    function reset() {
      fields.innerHTML = "";
      current = [];
      save.disabled = true;
    }

    addBtn.addEventListener("click", function () {
      editing = null;
      preset = null;
      kept = {};
      keptInner = {};
      picker.disabled = false;
      picker.value = "";
      reset();
      frame.hidden = false;
    });

    // Fill the freshly built controls from a saved row (W292).
    function applyPreset(values) {
      kept = {};
      keptInner = {};
      var known = {};
      fields.querySelectorAll("[data-config-key]").forEach(function (el) {
        var key = el.getAttribute("data-config-key");
        known[key] = true;
        if (!Object.prototype.hasOwnProperty.call(values, key)) return;
        setControl(el, String(values[key]));
      });
      // W357: a bundle's value is a JSON object of its own settings.
      fields.querySelectorAll("[data-config-bundle]").forEach(function (group) {
        var bkey = group.getAttribute("data-config-bundle");
        known[bkey] = true;
        if (!Object.prototype.hasOwnProperty.call(values, bkey)) return;
        var inner = {};
        try {
          inner = JSON.parse(String(values[bkey])) || {};
        } catch (err) {
          inner = {};
        }
        var declared = {};
        group.querySelectorAll("[data-config-child]").forEach(function (el) {
          var ck = el.getAttribute("data-config-child");
          declared[ck] = true;
          if (Object.prototype.hasOwnProperty.call(inner, ck)) setControl(el, String(inner[ck]));
        });
        Object.keys(inner).forEach(function (ck) {
          if (!declared[ck]) (keptInner[bkey] = keptInner[bkey] || {})[ck] = inner[ck];
        });
      });
      Object.keys(values).forEach(function (key) {
        if (!known[key]) kept[key] = values[key];
      });
      var keptKeys = Object.keys(kept);
      if (keptKeys.length) {
        var note = document.createElement("p");
        note.className = "field-tip";
        note.setAttribute("data-app-config-kept", "");
        note.textContent = keptKeys.length + " saved key" + (keptKeys.length === 1 ? "" : "s") +
          " this build of the app no longer declares " + (keptKeys.length === 1 ? "is" : "are") +
          " kept unchanged: " + keptKeys.join(", ") + ".";
        fields.insertBefore(note, fields.firstChild);
      }
    }

    // Open the frame on a saved row (W292). The app is fixed: changing it would
    // be a different configuration, which is Remove and Add.
    set.addEventListener("click", function (e) {
      var btn = e.target.closest && e.target.closest("[data-app-config-edit]");
      if (!btn) return;
      e.preventDefault();
      var row = btn.closest(".rs-row");
      if (!row) return;
      var pkg = row.querySelector('[name="app_configs__package_name"]').value;
      try {
        preset = JSON.parse(row.querySelector('[name="app_configs__values"]').value || "{}");
      } catch (err) {
        preset = {};
      }
      editing = row;
      if (!Array.prototype.some.call(picker.options, function (o) { return o.value === pkg; })) {
        var gone = document.createElement("option");
        gone.value = pkg;
        // Not offered for a new configuration -- deleted from the library, or a
        // plugin configured here before W348 -- but this row's own, so Edit works.
        gone.textContent = pkg + " (not offered for new configurations)";
        picker.appendChild(gone);
      }
      picker.value = pkg;
      picker.disabled = true;
      frame.hidden = false;
      picker.dispatchEvent(new Event("change"));
    });

    // One description for a row, new or edited, so both read the same.
    function describe(row, pkg, values) {
      row.querySelector('[name="app_configs__package_name"]').value = pkg;
      row.querySelector('[name="app_configs__values"]').value = JSON.stringify(values);
      var keys = Object.keys(values);
      row.querySelector("strong").textContent = pkg;
      row.querySelector(".muted").textContent =
        " · " + keys.length + (keys.length === 1 ? " key" : " keys");
      var detail = row.querySelector("[data-app-config-detail]");
      if (!detail) {
        detail = document.createElement("div");
        detail.className = "muted";
        detail.style.fontSize = "12px";
        detail.setAttribute("data-app-config-detail", "");
        row.querySelector("strong").parentNode.appendChild(detail);
      }
      detail.textContent = keys.map(function (k) {
        var v = String(values[k]);
        if (bundleKeys[k]) {
          // W357: a bundle reads as how many of its settings are set.
          var n = 0;
          try { n = Object.keys(JSON.parse(v) || {}).length; } catch (err) { n = 0; }
          return k + ": " + n + (n === 1 ? " setting" : " settings");
        }
        return k + "=" + (v.length > 40 ? v.slice(0, 37) + "..." : v);
      }).join(", ");
    }

    // One control for one declared key: shared by top-level keys and a
    // bundle's own settings (W357), so both behave identically.
    function control(k) {
      if (k.control === "bool") {
        var sel = document.createElement("select");
        sel.className = "field-full";
        [["", "Not set"], ["true", "True"], ["false", "False"]].forEach(function (o) {
          var opt = document.createElement("option");
          opt.value = o[0]; opt.textContent = o[1];
          sel.appendChild(opt);
        });
        return sel;
      }
      if (k.options && k.options.length && k.control === "multi_select") {
        // A checklist, not a text box: the value Android wants is a
        // String[] of the selected entries, and asking an operator to type
        // comma-separated values they cannot see is how wrong ones get sent.
        var list = document.createElement("div");
        list.className = "config-options";
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
        return list;
      }
      if (k.options && k.options.length) {
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
        return choice;
      }
      var input = document.createElement("input");
      input.type = k.control === "int" ? "number" : "text";
      input.className = "field-full";
      // ⚠️ Kept as a placeholder, unlike the rest (W92). This is the
      // field's *state* — what the app uses if nothing is set — not a
      // hint about what to type, so it cannot be mistaken for a value
      // the operator meant to save.
      input.placeholder = k.default || "not set";
      return input;
    }

    // A bundle (W357): its own settings as a group, saved together as one
    // JSON object under the bundle's key. Gboard's "Gboard settings" holds the
    // number row and touch & hold symbols this way.
    function bundleGroup(k) {
      var group = document.createElement("div");
      group.className = "config-bundle";
      group.setAttribute("data-config-bundle", k.key);
      var tip = document.createElement("p");
      tip.className = "field-tip";
      tip.textContent = (k.children || []).length + " settings inside this bundle. " +
        "Set only the ones you want; the rest keep the app's own value.";
      group.appendChild(tip);
      (k.children || []).forEach(function (c) {
        var row = document.createElement("div");
        row.className = "config-bundle-setting";
        row.setAttribute("data-config-child-field", c.key + " " + (c.label || ""));
        var label = document.createElement("label");
        label.textContent = c.label;
        row.appendChild(label);
        if (c.unsupported_reason) {
          var note = document.createElement("div");
          note.className = "muted";
          note.style.fontSize = "12px";
          note.textContent = c.unsupported_reason;
          row.appendChild(note);
        } else {
          var el = control(c);
          el.setAttribute("data-config-child", c.key);
          row.appendChild(el);
        }
        var keyLine = document.createElement("div");
        keyLine.className = "muted";
        keyLine.style.fontSize = "11px";
        keyLine.textContent = c.key + (c.description ? " — " + c.description : "");
        row.appendChild(keyLine);
        group.appendChild(row);
      });
      return group;
    }

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
          bundleKeys = {};
          schema.keys.forEach(function (k) { if (k.control === "bundle") bundleKeys[k.key] = true; });

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
                var self = q === "" ||
                  row.getAttribute("data-config-field").toLowerCase().indexOf(q) !== -1;
                // W357: a bundle shows when it or any of its settings match,
                // and then only the settings that match (all of them, if the
                // bundle itself matched).
                var children = row.querySelectorAll("[data-config-child-field]");
                if (!children.length) { row.hidden = !self; return; }
                var any = false;
                children.forEach(function (c) {
                  var hit = self ||
                    c.getAttribute("data-config-child-field").toLowerCase().indexOf(q) !== -1;
                  c.hidden = !hit;
                  if (hit) any = true;
                });
                row.hidden = !any;
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
            } else if (k.control === "bundle") {
              wrap.appendChild(bundleGroup(k));
            } else {
              var el = control(k);
              el.setAttribute("data-config-key", k.key);
              wrap.appendChild(el);
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
          if (preset) applyPreset(preset);
          save.disabled = false;
        })
        .catch(function () {
          fields.textContent = "Could not read this app's configuration.";
        });
    });

    save.addEventListener("click", function () {
      var pkg = picker.value;
      if (!pkg) return;

      // Keys this build no longer declares ride along untouched (W292).
      var values = editing ? Object.assign({}, kept) : {};
      fields.querySelectorAll("[data-config-key]").forEach(function (el) {
        var v = readControl(el);
        if (v !== null) values[el.getAttribute("data-config-key")] = v;
      });
      // W357: each bundle's settings go together, as one JSON object, under
      // the bundle's own key - which is where the app reads them.
      fields.querySelectorAll("[data-config-bundle]").forEach(function (group) {
        var bkey = group.getAttribute("data-config-bundle");
        var inner = Object.assign({}, keptInner[bkey] || {});
        group.querySelectorAll("[data-config-child]").forEach(function (el) {
          var v = readControl(el);
          if (v !== null) inner[el.getAttribute("data-config-child")] = v;
        });
        if (Object.keys(inner).length) values[bkey] = JSON.stringify(inner);
        else delete values[bkey];
      });

      if (editing) {
        // In place: the same row, the same position, the new values.
        describe(editing, pkg, values);
      } else {
        var row = document.createElement("div");
        row.className = "rs-row";
        row.innerHTML =
          '<input type="hidden" name="app_configs__package_name">' +
          '<input type="hidden" name="app_configs__values">' +
          '<div style="flex:1"><strong></strong>' +
          '<span class="muted" style="font-size:12px"></span></div>' +
          '<button type="button" class="ghost" data-app-config-edit>Edit</button>' +
          '<button type="button" class="ghost" data-remove-row>Remove</button>';
        describe(row, pkg, values);
        addBtn.insertAdjacentElement("beforebegin", row);
      }
      editing = null;
      preset = null;
      kept = {};
      keptInner = {};
      picker.disabled = false;
      frame.hidden = true;
    });
  })();

  /* --- Upload with progress (W51, W276, W339, W342) --------------------------
     One dialog for every upload: #upload-modal (base.html, `upload_modal`).

     Two ways in:

     * **Forms.** Every POST multipart/form-data form with a file chosen is sent
       with XMLHttpRequest and the page goes where the server redirects (W339).
       Per form, optionally: data-upload-processing (what the server does after
       the last byte), data-upload-cancelled (what Cancel leaves behind),
       data-no-upload-progress (leave it to the browser).
     * **Script**, `window.AtlasUpload.send({...})`, for uploads that must not
       leave the page -- the policy editor's data packages hold a whole unsaved
       policy (W342). The caller decides what the answer means.

     ⚠️ XMLHttpRequest, not fetch. `fetch` still cannot report **upload** progress,
     and it cannot be aborted in a way that stops the bytes -- so a Cancel button
     built on it would hide the dialog while the transfer carried on.

     ⚠️ **The form listener is on `window`, so it runs last.** Form- and
     document-level submit handlers (a `data-confirm` prompt, the QR limits'
     confirm, the icon picker holding a submit while it draws) fire first, and
     one that cancels the submit must win: an XHR already sent cannot be taken
     back. */

  (function () {
    var modal = document.getElementById("upload-modal");
    if (!modal) return;

    var title = modal.querySelector("[data-upload-title]");
    var detail = modal.querySelector("[data-upload-detail]");
    var bar = modal.querySelector("[data-upload-bar]");
    var bytes = modal.querySelector("[data-upload-bytes]");
    var note = modal.querySelector("[data-upload-note]");
    var results = modal.querySelector("[data-upload-results]");
    var choices = modal.querySelector("[data-upload-choices]");
    // True from the moment the dialog opens until it closes or shows its end,
    // including while it waits on the operator's answer (W344), when no request
    // is in flight but another upload must still not start.
    var busy = false;
    // Run when Close is pressed after a batch (W343): the page reloads to show
    // what was added. Cleared on every new upload.
    var afterClose = null;
    var cancel = modal.querySelector("[data-upload-cancel]");
    var close = modal.querySelector("[data-upload-close]");
    var request = null;
    // Made here if the page lacks it -- a page cached from before W344 -- so a
    // question can never leave the dialog locked with no way to answer.
    if (!choices) {
      choices = document.createElement("div");
      choices.className = "toolbar upload-choices";
      choices.setAttribute("data-upload-choices", "");
      choices.hidden = true;
      cancel.parentNode.parentNode.insertBefore(choices, cancel.parentNode);
    }

    var cancelledText = "Nothing was saved.";

    function size(n) {
      if (n >= 1073741824) return (n / 1073741824).toFixed(2) + " GB";
      if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
      if (n >= 1024) return Math.round(n / 1024) + " KB";
      return n + " B";
    }

    function remaining(seconds) {
      if (seconds < 10) return "a few seconds left";
      if (seconds < 60) return "about " + Math.round(seconds) + " s left";
      var m = Math.floor(seconds / 60), s = Math.round(seconds % 60);
      if (m >= 60) return "about " + Math.floor(m / 60) + " h " + (m % 60) + " min left";
      return "about " + m + " min" + (s ? " " + s + " s" : "") + " left";
    }

    /** What a refusal means, in words an operator can act on. */
    function refusal(status) {
      if (status === 413) return "The file is larger than the server accepts (HTTP 413).";
      if (status === 401 || status === 403) {
        return "The server refused it (HTTP " + status + "). Your session may have " +
          "expired: reload the page, sign in again, and retry.";
      }
      if (status === 502 || status === 503 || status === 504) {
        return "The server, or the proxy in front of it, dropped the upload (HTTP " +
          status + "). Try again; if it keeps happening, the server's logs will say why.";
      }
      return "The server refused it (HTTP " + status + ").";
    }

    /* ⚠️ **Locked in until Cancel (W276).** While bytes are in flight the
       dialog ignores backdrop clicks and Escape (`data-modal-locked`), and
       leaving the page asks first. A stray click used to hide the dialog, and
       the next one navigated away and silently killed the transfer. */
    function guard(event) {
      event.preventDefault();
      /* Legacy Chrome/Edge (< 119) prompt only when a value is set. `true`, as
         MDN documents, not "": a falsy returnValue cancels an event by itself,
         which made a test unable to tell whether preventDefault was there. */
      event.returnValue = true;
    }
    function lock() {
      modal.setAttribute("data-modal-locked", "");
      window.addEventListener("beforeunload", guard);
    }
    function unlock() {
      modal.removeAttribute("data-modal-locked");
      window.removeEventListener("beforeunload", guard);
    }

    /** End the upload with a message, leaving the dialog up to be read. */
    function finish(heading, message, extra) {
      request = null;
      busy = false;
      unlock();
      clearChoices();
      bar.style.width = "0";
      title.textContent = heading;
      detail.textContent = message;
      bytes.textContent = "";
      if (note) { note.textContent = extra || ""; note.hidden = !extra; }
      cancel.hidden = true;
      close.hidden = false;
    }

    /** End the upload and close the dialog: the caller shows the outcome. */
    function dismiss() {
      request = null;
      busy = false;
      unlock();
      clearChoices();
      modal.hidden = true;
    }

    function clearChoices() {
      if (choices) { choices.innerHTML = ""; choices.hidden = true; }
    }

    /**
     * Ask the operator, in the dialog, and wait (W344). Resolves with the
     * chosen value. Cancel is hidden meanwhile: the choices are the way out.
     */
    function ask(heading, message, options, extra) {
      return new Promise(function (resolve) {
        title.textContent = heading;
        detail.textContent = message;
        bytes.textContent = "";
        if (note) { note.textContent = extra || ""; note.hidden = !extra; }
        cancel.hidden = true;
        choices.innerHTML = "";
        options.forEach(function (o, i) {
          var b = document.createElement("button");
          b.type = "button";
          b.className = i === 0 ? "" : "ghost";
          b.textContent = o.label;
          b.setAttribute("data-upload-choice", o.value);
          b.addEventListener("click", function () {
            clearChoices();
            if (note) { note.textContent = ""; note.hidden = true; }
            cancel.hidden = false;
            resolve(o.value);
          });
          choices.appendChild(b);
        });
        choices.hidden = false;
      });
    }

    /**
     * A second request in the same dialog -- the answer to a question (W344).
     * Resolves {xhr}, {lost: true} or {aborted: true}; never rejects.
     */
    function follow(url, body, processing) {
      return new Promise(function (resolve) {
        detail.textContent = processing || "Working…";
        transfer(url, body, processing, {
          load: function (xhr) { request = null; resolve({ xhr: xhr }); },
          error: function () { request = null; resolve({ lost: true }); },
          abort: function () { request = null; resolve({ aborted: true }); }
        });
      });
    }

    /** Open the dialog, locked, for a new upload. */
    function openDialog(heading) {
      busy = true;
      afterClose = null;
      clearChoices();
      title.textContent = heading;
      detail.textContent = "Starting…";
      bytes.textContent = "";
      bar.style.width = "0";
      if (note) { note.textContent = ""; note.hidden = true; }
      if (results) { results.innerHTML = ""; results.hidden = true; }
      cancel.hidden = false;
      close.hidden = true;
      modal.hidden = false;
      lock();
    }

    /** One XHR with its progress wired to the dialog. `on` gets load/error/abort. */
    function transfer(url, body, processing, on) {
      var began = Date.now();
      var xhr = new XMLHttpRequest();
      request = xhr;
      xhr.open("POST", url);

      xhr.upload.addEventListener("progress", function (event) {
        if (!event.lengthComputable) {
          detail.textContent = "Uploading — " + size(event.loaded) + " sent";
          return;
        }
        var percent = Math.round((event.loaded / event.total) * 100);
        bar.style.width = percent + "%";
        detail.textContent = "Uploading — " + percent + "%";
        var line = size(event.loaded) + " of " + size(event.total);
        var elapsed = (Date.now() - began) / 1000;
        // An average over the whole transfer: a one-second rate jumps about too
        // much on a radio link to be worth reading.
        if (elapsed >= 1 && event.loaded > 0) {
          var rate = event.loaded / elapsed;
          line += " · " + size(rate) + "/s · " + remaining((event.total - event.loaded) / rate);
        }
        bytes.textContent = line;
      });

      // The server still has work to do after the last byte (unpacking an XAPK,
      // checking a data package), and on a large file it takes noticeable time.
      // Saying so stops the bar sitting at 100% looking stuck.
      xhr.upload.addEventListener("load", function () {
        bar.style.width = "100%";
        detail.textContent = processing || "Uploaded — the server is processing it…";
        bytes.textContent = "";
      });

      xhr.addEventListener("load", function () { on.load(xhr); });
      xhr.addEventListener("error", function () { on.error(xhr); });
      xhr.addEventListener("abort", function () { on.abort(xhr); });
      xhr.send(body);
      return xhr;
    }

    var LOST = "Lost contact with the server before it answered. " +
      "If your session expired, reload the page and sign in again.";

    /**
     * Send `body` to `url` with the dialog showing progress.
     *
     *   name        what is being uploaded, for the heading
     *   processing  what the server does after the last byte
     *   cancelled   what Cancel leaves behind
     *   onAnswer(xhr, ui)  the server answered. Call ui.done() to close the
     *               dialog, or ui.show(heading, message, note) to leave something
     *               up for the operator to read (a refusal, a repack).
     *   onGone(ui)  the connection was lost (default: a failure message)
     *
     * Returns false, sending nothing, while another upload is running.
     */
    function send(options) {
      if (busy) return false;
      cancelledText = options.cancelled || "Nothing was saved.";
      var ui = { done: dismiss, show: finish, ask: ask, follow: follow };
      openDialog("Uploading " + (options.name || "file"));
      transfer(options.url, options.body, options.processing, {
        load: function (xhr) { request = null; options.onAnswer(xhr, ui); },
        error: function () {
          if (options.onGone) { options.onGone(ui); return; }
          finish("Upload failed", LOST);
        },
        abort: function () { finish("Upload cancelled", cancelledText); }
      });
      return true;
    }

    /**
     * Several uploads, **one at a time**, in one dialog (W343).
     *
     * ⚠️ Sequential on purpose. On a slow uplink a single request carrying every
     * file loses all of them to one dropped connection; one file per request
     * loses one, and Cancel stops the rest without undoing what is already in.
     *
     *   items       [{name, body}]
     *   url, processing
     *   noun        what each item is, for the summary ("data package")
     *   verdict(xhr, ui) -> {ok, text, skipped?, aborted?}, or a Promise of it:
     *               one item's answer. `ui.ask` and `ui.follow` let it put a
     *               question to the operator mid-batch (W344).
     *   onClosed(outcomes)  after Close on the summary
     */
    function sendBatch(options) {
      if (busy || !options.items.length) return false;
      var ui = { ask: ask, follow: follow };
      var items = options.items;
      var outcomes = [];
      var index = 0;
      openDialog("Uploading " + items.length + " files");

      function nextOrSummary() {
        if (index >= items.length) { summary(false); return; }
        var item = items[index];
        title.textContent = "Uploading " + (index + 1) + " of " + items.length + " — " + item.name;
        transfer(options.url, item.body, options.processing, {
          load: function (xhr) {
            request = null;
            Promise.resolve(options.verdict(xhr, ui)).then(function (v) {
              if (v.aborted) { stop(); return; }
              outcomes.push({ name: item.name, ok: v.ok, skipped: !!v.skipped, text: v.text });
              index++;
              nextOrSummary();
            });
          },
          error: function () {
            outcomes.push({ name: item.name, ok: false, text: LOST });
            index++;
            nextOrSummary();
          },
          abort: stop
        });
      }

      function stop() {
        for (var i = index; i < items.length; i++) {
          outcomes.push({ name: items[i].name, ok: false, cancelled: true, text: "not sent" });
        }
        summary(true);
      }

      function summary(stopped) {
        var added = outcomes.filter(function (o) { return o.ok; }).length;
        var noun = options.noun || "file";
        finish(
          (stopped ? "Upload cancelled — " : "") + "Added " + added + " of " + items.length +
            " " + noun + (items.length === 1 ? "" : "s"),
          added === items.length ? "Every one was accepted." :
            "Anything refused is listed with the reason; nothing else was affected."
        );
        if (results) {
          outcomes.forEach(function (o) {
            var li = document.createElement("li");
            var quiet = o.cancelled || o.skipped;
            li.className = o.ok ? "ok" : (quiet ? "skipped" : "bad");
            li.textContent = (o.ok ? "✓ " : (quiet ? "– " : "✗ ")) + o.name + " — " + o.text;
            results.appendChild(li);
          });
          results.hidden = false;
        }
        afterClose = function () { if (options.onClosed) options.onClosed(outcomes); };
      }

      nextOrSummary();
      return true;
    }

    window.AtlasUpload = { send: send, sendBatch: sendBatch, refusal: refusal, LOST: LOST };

    /* ----- forms ---------------------------------------------------------- */

    function chosenFiles(form) {
      var files = [];
      form.querySelectorAll('input[type="file"]').forEach(function (input) {
        if (input.disabled || !input.name) return;
        Array.prototype.forEach.call(input.files || [], function (f) { files.push(f); });
      });
      return files;
    }

    function eligible(form) {
      return form && form.tagName === "FORM" &&
        (form.getAttribute("method") || "").toLowerCase() === "post" &&
        (form.getAttribute("enctype") || "").toLowerCase() === "multipart/form-data" &&
        !form.hasAttribute("data-no-upload-progress") &&
        chosenFiles(form).length > 0;
    }

    function submitForm(form, submitter) {
      var files = chosenFiles(form);
      var body;
      try {
        body = new FormData(form, submitter || undefined);
      } catch (err) {
        body = new FormData(form);  // a browser without the submitter argument
      }
      send({
        url: form.getAttribute("action") || window.location.pathname,
        body: body,
        name: files.length === 1 ? files[0].name : files.length + " files",
        processing: form.getAttribute("data-upload-processing"),
        cancelled: form.getAttribute("data-upload-cancelled"),
        onAnswer: function (xhr, ui) {
          if (xhr.status >= 200 && xhr.status < 400) {
            // The server answers with a redirect to the refreshed page. Released
            // first, or the page would ask the operator to confirm leaving it for
            // the very page the upload was going to; and cleared, so a held
            // navigation does not leave the page ignoring the next upload.
            var destination = xhr.responseURL || window.location.href;
            request = null;
            busy = false;
            unlock();
            window.atlasNavigate(destination);
            return;
          }
          ui.show("Upload failed", refusal(xhr.status));
        }
      });
    }

    window.addEventListener("submit", function (e) {
      if (e.defaultPrevented || busy || !eligible(e.target)) return;
      e.preventDefault();
      submitForm(e.target, e.submitter);
    });

    cancel.addEventListener("click", function () {
      // Genuinely stops the transfer rather than just closing the dialog.
      if (request) request.abort();
      else modal.hidden = true;
    });

    close.addEventListener("click", function () {
      modal.hidden = true;
      var then = afterClose;
      afterClose = null;
      if (then) then();
    });
  })();

  /* --- Data package answers, duplicates included (W344) ----------------------
     `AtlasDataPackages.answer(xhr, ui, csrf)` reads the server's answer to a
     data package upload and, when it says "already in the library", asks the
     operator in the upload dialog and sends the choice. Shared by the Content
     page and the policy editor, so the question reads the same in both.

     Operator: identical files are refused; the same package with different
     contents asks -- Replace, Keep both (saved as "Name (1)"), or Skip. The
     upload was held on the server while asking, so the choice costs no second
     upload. Resolves {ok, text, res, skipped?, aborted?}. */

  (function () {
    function parse(xhr) {
      try { return JSON.parse(xhr.responseText) || {}; } catch (e) { return {}; }
    }

    function added(res) {
      var n = res.contents;
      return "added as " + res.name + (n ? " (" + n + (n === 1 ? " file)" : " files)") : "");
    }

    function plural(n) { return n + (n === 1 ? " policy" : " policies"); }

    function answer(xhr, ui, csrf) {
      var res = parse(xhr);
      var refusal = window.AtlasUpload.refusal;
      if (xhr.status >= 200 && xhr.status < 300 && res.id) {
        return Promise.resolve({ ok: true, res: res, text: added(res) });
      }
      if (!(xhr.status === 409 && res.conflict && res.token)) {
        return Promise.resolve({ ok: false, text: res.error || refusal(xhr.status) });
      }
      var c = res.conflict;
      var consequence = c.used_by
        ? "Replace updates the " + plural(c.used_by) + " using it: their devices get the new version once, on their next check-in."
        : "No policy uses it yet.";
      return ui.ask("Already in the library", c.question, [
        { label: "Replace", value: "replace" },
        { label: "Keep both — save as “" + c.suggested_name + "”", value: "keep" },
        { label: "Skip", value: "skip" }
      ], consequence).then(function (choice) {
        var body = new FormData();
        if (csrf) body.append("csrf_token", csrf);
        body.append("token", res.token);
        body.append("decision", choice);
        var doing = { replace: "Replacing “" + c.existing.name + "”…", keep: "Saving it as “" + c.suggested_name + "”…",
                      skip: "Skipping…" }[choice];
        return ui.follow("/content/data-package/resolve", body, doing).then(function (r) {
          if (r.aborted) return { aborted: true };
          if (r.lost) return { ok: false, text: window.AtlasUpload.LOST };
          var out = parse(r.xhr);
          if (out.skipped) {
            return { ok: false, skipped: true, text: "skipped; “" + c.existing.name + "” is already in the library" };
          }
          if (r.xhr.status >= 200 && r.xhr.status < 300 && out.id) {
            return { ok: true, res: out, text: out.replaced
              ? "replaced “" + out.name + "”" + (out.used_by ? "; devices on " + plural(out.used_by) + " get it once" : "")
              : added(out) };
          }
          return { ok: false, text: out.error || refusal(r.xhr.status) };
        });
      });
    }

    window.AtlasDataPackages = { answer: answer };
  })();

  /* --- Bulk data packages (W343) ---------------------------------------------
     <form data-bulk-packages> on the Content page. Operator: "can we do a bulk
     upload option for multiple data packages?"

     One file: the ordinary form upload above (W339), name field and all.
     Several: each sent **on its own**, one after another, to the JSON route the
     policy editor uses (the same validation; it lands in the Content library),
     through `AtlasUpload.sendBatch`. The dialog ends with what happened to each,
     and closing it reloads the page to list them.

     ⚠️ Form-level, so it runs before the page-wide form upload on `window` and
     can claim the submit; a single file is left to that one. */

  (function () {
    var form = document.querySelector("[data-bulk-packages]");
    if (!form || !window.AtlasUpload) return;
    var input = form.querySelector('input[type="file"]');
    var nameField = form.querySelector("[data-bulk-name]");
    if (!input) return;

    function several() { return !!(input.files && input.files.length > 1); }

    // A name belongs to one package; with several each takes its manifest's.
    input.addEventListener("change", function () {
      if (nameField) nameField.disabled = several();
    });

    // ⚠️ One file too, since W344: a duplicate is answered by a question in the
    // dialog, which the redirecting form upload cannot ask.
    form.addEventListener("submit", function (e) {
      if (!input.files || !input.files.length) return;
      e.preventDefault();
      var token = form.querySelector('input[name="csrf_token"]');
      var typed = !several() && nameField ? nameField.value.trim() : "";
      var items = Array.prototype.map.call(input.files, function (file) {
        var body = new FormData();
        if (token) body.append("csrf_token", token.value);
        body.append("file", file);
        if (typed) body.append("name", typed);
        return { name: file.name, body: body };
      });
      window.AtlasUpload.sendBatch({
        url: "/policies/data-package/upload",
        items: items,
        noun: "data package",
        processing: "Uploaded — the server is checking the data package…",
        verdict: function (xhr, ui) {
          return window.AtlasDataPackages.answer(xhr, ui, token ? token.value : "");
        },
        onClosed: function (outcomes) {
          // The list below the form is the server's; reload it if anything
          // was added, and leave the page alone if nothing was.
          if (outcomes.some(function (o) { return o.ok; })) window.atlasNavigate("/content");
        }
      });
    });
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
      /* ⚠️ The scope, then the picker inside it. This used to look only for a
         `.rs-row` containing a `__package_name` select, which is the shape of a
         required-apps row and of a kiosk tile — but not of the single-app kiosk
         control, which is not a row and whose select is named `kiosk_package`.
         So that control could never have had a build select wired, which is
         half of why kiosk mode could not engage (W196). */
      var scope = choice.closest("[data-version-scope]") || choice.closest(".rs-row");
      var picker = scope && (
        scope.querySelector("[data-version-picker]") ||
        scope.querySelector('select[name$="__package_name"]')
      );
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

    /* Keep each row's "uninstall if withdrawn" tick pointing at the app that
       row names (W192).

       The checkbox carries the package name as its value rather than relying on
       its position, because an unchecked box does not submit at all and index
       pairing would move every later tick onto the wrong app. That means the
       value has to follow the select, and a row with no app chosen cannot be
       ticked at all — exactly what `syncFavouriteValues` does for a kiosk
       favourite. */
    function syncRemovalValues() {
      document.querySelectorAll("[data-remove-withdrawn]").forEach(function (box) {
        var row = box.closest(".rs-row");
        var select = row && row.querySelector('select[name$="__package_name"]');
        if (!select) return;
        box.value = select.value;
        if (!select.value) box.checked = false;
        box.disabled = !select.value;
      });
    }

    function wireAll() {
      // ⚠️ By attribute as well as by name: the single-app kiosk build select
      // is `kiosk_artifact_sha256`, not `*__version_choice` (W196).
      document.querySelectorAll('select[name$="__version_choice"]').forEach(wire);
      document.querySelectorAll("select[data-version-choice]").forEach(wire);
      syncRemovalValues();
    }

    document.addEventListener("change", function (e) {
      if (e.target.matches && e.target.matches('select[name$="__package_name"]')) {
        syncRemovalValues();
      }
    });

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

  /* --- Policy list filter (W346) ----------------------------------------------
     <div data-policy-filter> above the Device policies table. Name narrows by
     what is typed; Category keeps the policies containing that category. Both at
     once is both. Rows carry data-name and data-categories, so nothing is
     inferred from what the cells happen to say. */

  document.querySelectorAll("[data-policy-filter]").forEach(function (bar) {
    var name = bar.querySelector("[data-policy-filter-name]");
    var category = bar.querySelector("[data-policy-filter-category]");
    var count = bar.querySelector("[data-policy-filter-count]");
    var panel = bar.parentNode;
    var empty = panel.querySelector("[data-policy-filter-empty]");
    var rows = Array.prototype.slice.call(panel.querySelectorAll("tr[data-policy-row]"));
    if (!name || !category) return;

    function apply() {
      var q = name.value.trim().toLowerCase();
      var c = category.value;
      var shown = 0;
      rows.forEach(function (row) {
        var hit = (!q || (row.getAttribute("data-name") || "").indexOf(q) !== -1) &&
          (!c || (row.getAttribute("data-categories") || "").split(" ").indexOf(c) !== -1);
        row.hidden = !hit;
        if (hit) shown++;
      });
      var noun = rows.length === 1 ? "policy" : "policies";
      if (count) count.textContent = (q || c ? shown + " of " : "") + rows.length + " " + noun;
      if (empty) empty.hidden = shown > 0;
    }

    name.addEventListener("input", apply);
    category.addEventListener("change", apply);
    apply();
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
        // A cell may say what it sorts by (W346): a name cell also holds a
        // "held" pill, and a categories cell is a row of tags.
        var val = function (row) {
          var cell = row.cells[idx];
          if (!cell) return "";
          var given = cell.getAttribute("data-sort-value");
          return given !== null ? given : cell.textContent.trim();
        };
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
      var label;
      // The console tile has no app select to read a name from — it names
      // itself (W197). Without this it was the one tile on the device that the
      // preview of the device did not show.
      var fixed = row.getAttribute("data-tile-label");
      if (fixed) {
        label = fixed;
      } else {
        var select = row.querySelector("select");
        if (!select || !select.value) return;
        // The app's own name, as the device will show it — not the package,
        // which is what the device grid looked like before it read labels.
        label = select.options[select.selectedIndex].text.replace(/\s*\([^)]*\)\s*$/, "");
      }
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

  /* --- One row per app (W287) ------------------------------------------------
     Operator: once an app has been picked for a required-apps row, adding
     another row "should not show that previous app in the new dropdown list".

     In a `[data-unique-choice]` rowset, every app chosen in one row is hidden
     *and* disabled in the others' selects -- `hidden` alone is ignored on an
     <option> by Safari, and `disabled` alone leaves a greyed list of apps that
     are already dealt with. A row's own choice is never touched, so nothing
     an operator picked is ever unselected or dropped from the POST.

     ⚠️ Recomputed from the page on every change rather than tracked: rows
     arrive from the template, from an app group, and from a saved policy, and
     leave by Remove. State kept alongside that would be one more thing to fall
     out of step. A <template>'s content is not in the document, so the blank
     row it holds is never counted as a choice. */
  function refreshUniqueChoices(set) {
    var selects = set.querySelectorAll("select[name$='__package_name']");
    var chosen = {};
    selects.forEach(function (s) {
      if (s.value) chosen[s.value] = (chosen[s.value] || 0) + 1;
    });
    selects.forEach(function (s) {
      Array.prototype.forEach.call(s.options, function (o) {
        if (!o.value) return;
        var taken = !!chosen[o.value] && o.value !== s.value;
        o.hidden = taken;
        o.disabled = taken;
      });
    });
  }

  function refreshAllUniqueChoices() {
    document.querySelectorAll("[data-unique-choice]").forEach(refreshUniqueChoices);
  }

  document.addEventListener("change", function (e) {
    var set = e.target.matches && e.target.matches("select[name$='__package_name']") &&
      e.target.closest("[data-unique-choice]");
    if (set) refreshUniqueChoices(set);
  });

  // After the handlers that add and remove rows have run, whichever of them it
  // was -- Add, Remove, or an app group filling several rows at once.
  document.addEventListener("click", function (e) {
    if (!e.target.closest) return;
    if (e.target.closest("[data-add-row], [data-remove-row], [data-add-app-group]")) {
      setTimeout(refreshAllUniqueChoices, 0);
    }
  });

  refreshAllUniqueChoices();

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

    /* Tapping the page, rather than the menu bar, closes it.
     *
     * ⚠️ **Scoped to the whole header, not to the menu and its button.** An
     * earlier version excluded `.nav-grid` and `.nav-toggle` and closed the menu
     * on the very tap that opened it — which read as "the button does nothing".
     *
     * The mechanism: a `<label>` forwards its click to the control as a
     * *second*, synthetic click, dispatched on the `<input>`. That input is a
     * **sibling** of the label, so `closest(".nav-toggle")` did not match it, the
     * handler treated it as an outside tap, and it closed what the first click
     * had just opened. Every part of this control lives inside `<header>`, so
     * asking that one question cannot come apart the same way.
     *
     * A tap on a grid *link* is left alone too: the page is navigating anyway,
     * and closing first makes the menu flicker shut before it goes. */
    document.addEventListener("click", function (e) {
      if (!navSwitch.checked) return;
      if (e.target.closest && e.target.closest("header")) return;
      closeNav();
    });
  }

  /* --- Forced levels (W364) --------------------------------------------------
     <span data-percent-slider>: a tick box that means "managed", a slider, and a
     read-out. The slider always submits; the server keeps it only when the box
     is ticked, so this is presentation only and the form works without it. */

  function percentSliderSync(box) {
    var on = box.querySelector("[data-percent-on]");
    var range = box.querySelector("[data-percent-range]");
    var out = box.querySelector("[data-percent-value]");
    var off = box.querySelector("[data-percent-off]");
    if (!on || !range) return;
    if (out) { out.textContent = range.value + "%"; out.hidden = !on.checked; }
    if (off) off.hidden = on.checked;
    range.style.opacity = on.checked ? "" : ".45";
  }

  document.querySelectorAll("[data-percent-slider]").forEach(percentSliderSync);

  document.addEventListener("input", function (e) {
    var box = e.target.closest && e.target.closest("[data-percent-slider]");
    if (!box) return;
    // Moving the slider is a decision to manage it.
    if (e.target.matches("[data-percent-range]")) {
      var on = box.querySelector("[data-percent-on]");
      if (on && !on.checked) on.checked = true;
    }
    percentSliderSync(box);
  });

  document.addEventListener("change", function (e) {
    var box = e.target.closest && e.target.closest("[data-percent-slider]");
    if (box) percentSliderSync(box);
  });

  /* --- Confirm before submit --------------------------------------------------
     <form data-confirm="This retires the token. Continue?"> */

  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  /* --- Switches that act at once (W349) ---------------------------------------
     <input type="checkbox" data-submit-on-change> inside a form: changing it
     submits the form. The form's data-switch-confirm asks first, and a "no" puts
     the switch back, so it never shows a state that was not saved. A switch
     marked data-indeterminate starts half-set (a package whose overlays are
     partly shown). */

  document.querySelectorAll("input[data-submit-on-change][data-indeterminate]").forEach(function (box) {
    box.indeterminate = true;
  });

  document.addEventListener("change", function (e) {
    var box = e.target;
    if (!box.matches || !box.matches("input[data-submit-on-change]") || !box.form) return;
    var form = box.form;
    var msg = form.getAttribute("data-switch-confirm");
    if (msg && !window.confirm(msg)) {
      box.checked = !box.checked;
      box.indeterminate = box.hasAttribute("data-indeterminate");
      return;
    }
    // A large package takes a few seconds to rewrite; say so, and refuse a
    // second click while it does.
    box.disabled = true;
    var note = form.querySelector("[data-visibility-note]");
    if (note) note.textContent = "Saving…";
    form.submit();
  });

  /* --- Print this page (W335) ------------------------------------------------
     <button data-print-page>. A handler here, not onclick="": the console's CSP
     refuses inline script. */

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-print-page]");
    if (btn) window.print();
  });

  /* --- Enrolment QR limits (W330) ---------------------------------------------
     <div data-qr-limits> holds two boxes, data-qr-limit="timer" / "uses", each
     revealing its data-qr-limit-fields. With neither ticked the QR is
     permanent: the warning shows, and the submit asks first.

     ⚠️ A hidden field is disabled as well as hidden, so a number left in it is
     not submitted and cannot fail validation for a limit nobody chose. */

  function qrLimitsSync(box) {
    var anyOn = false;
    box.querySelectorAll("[data-qr-limit]").forEach(function (check) {
      var fields = box.querySelector(
        '[data-qr-limit-fields="' + check.getAttribute("data-qr-limit") + '"]');
      if (check.checked) anyOn = true;
      if (!fields) return;
      fields.hidden = !check.checked;
      fields.querySelectorAll("input, select").forEach(function (el) {
        el.disabled = !check.checked;
        if (el.type === "number") el.required = check.checked;
      });
    });
    var warning = box.querySelector("[data-qr-permanent-warning]");
    if (warning) warning.hidden = anyOn;
    return anyOn;
  }

  document.querySelectorAll("[data-qr-limits]").forEach(qrLimitsSync);

  document.addEventListener("change", function (e) {
    if (!e.target.matches || !e.target.matches("[data-qr-limit]")) return;
    var box = e.target.closest("[data-qr-limits]");
    if (box) qrLimitsSync(box);
  });

  document.addEventListener("submit", function (e) {
    var box = e.target.querySelector && e.target.querySelector("[data-qr-limits]");
    if (!box || qrLimitsSync(box)) return;
    if (!window.confirm(
      "This QR will not expire. It stays a live enrolment credential until " +
      "the token is revoked. Make a permanent QR?")) e.preventDefault();
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

    // ⚠️ Mirrored onto the form as `data-dirty` (W296), so the deployment card
    // can ask "are there unsaved edits?" without sharing this closure.
    function mark(value) {
      dirty = value;
      if (value) form.setAttribute("data-dirty", "");
      else form.removeAttribute("data-dirty");
    }
    // ⚠️ Not the settings search (W297): on New policy it sits inside this
    // form, and looking for a setting is not an edit to the policy.
    function isEdit(e) {
      return !(e.target && e.target.closest && e.target.closest("[data-policy-search]"));
    }
    form.addEventListener("input", function (e) { if (isEdit(e)) mark(true); });
    form.addEventListener("change", function (e) { if (isEdit(e)) mark(true); });
    form.addEventListener("submit", function () { mark(false); });

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

  /* --- Never lose a policy to a refused save (W363) ---------------------------
     A user built a large policy, left the name blank, pressed Create policy, and
     the server's refusal redirected to a fresh page with every field empty.

       * New policy: Create policy and Save as template stay off until the name
         has a character that is not a space, and a submit that still happens
         (Enter, "Save policy first") is stopped at the name.
       * New and existing: the save posts in the background. Only a success
         leaves the page; any refusal, or no answer at all, keeps every field as
         typed, says why at the top, and re-arms the unsaved-changes guard. */

  (function () {
    var form = document.querySelector("form[data-policy-form]");
    if (!form || !window.fetch || !window.FormData) return;
    var name = form.querySelector("[data-policy-name]");
    var hint = form.querySelector("[data-policy-name-hint]");
    var box = form.querySelector("[data-policy-error]");
    var gated = form.querySelectorAll("button[data-needs-name]");
    var busy = false;

    function hasName() { return !name || name.value.trim() !== ""; }

    function gate() {
      var ok = hasName();
      gated.forEach(function (b) { b.disabled = !ok || busy; });
      if (hint) hint.hidden = ok;
    }

    function fail(message) {
      if (box) {
        box.textContent = message;
        box.hidden = false;
        if (box.scrollIntoView) box.scrollIntoView({ block: "center" });
      }
      // The unsaved-changes guard cleared itself on submit; the edits are still
      // unsaved, so arm it again with an edit event it already listens for.
      var marker = name || form.querySelector("input, select, textarea");
      if (marker) marker.dispatchEvent(new Event("change", { bubbles: true }));
    }

    if (name) {
      name.addEventListener("input", gate);
      gate();
    }

    form.addEventListener("submit", function (e) {
      // Another handler already stopped this submit (a confirm, a lock): theirs.
      if (e.defaultPrevented) return;
      e.preventDefault();
      if (busy) return;
      if (!hasName()) {
        fail("Give the policy a name before saving it. Nothing was submitted, and everything you entered is still here.");
        name.focus();
        return;
      }
      if (box) box.hidden = true;

      // The clicked button's own value (Save as template) is added by hand:
      // not every FormData honours a submitter, and some ignore it silently.
      var data = new FormData(form);
      var by = e.submitter;
      if (by && by.name && !data.has(by.name)) data.append(by.name, by.value);

      busy = true;
      gate();
      fetch(form.getAttribute("action") || window.location.pathname, {
        method: "POST",
        body: data,
        credentials: "same-origin",
        headers: { "X-ATLAS-Submit": "fetch" },
      })
        .then(function (res) {
          return res.json().then(
            function (body) { return { ok: res.ok, body: body || {} }; },
            function () { return { ok: false, body: {} }; }
          );
        })
        .then(function (res) {
          if (res.ok && res.body.redirect) {
            window.location.assign(res.body.redirect);
            return;
          }
          busy = false;
          gate();
          fail((res.body.error || "The server refused the save.") +
               " Nothing was lost: correct it and save again.");
        })
        .catch(function () {
          busy = false;
          gate();
          fail("Could not reach the server. Nothing was saved, and everything you entered is still here.");
        });
    });
  })();
})();

/* --- Save deployment without leaving the page (W296) -------------------------
   The Deployment card used to post and redirect, and the reload threw away any
   unsaved edits in the policy editor above it. Now:
     * nothing changed (the choice already in force)  -> say so, send nothing;
     * unsaved policy edits on the page               -> ask first;
     * otherwise -> POST in the background, answer in the modal, and replace the
       header's deployment pill in place.
   Without script the form still posts and redirects. */
(function () {
  var form = document.querySelector("form[data-deployment-form]");
  var modal = document.getElementById("deploy-modal");
  if (!form || !modal) return;

  var title = modal.querySelector("[data-deploy-modal-title]");
  var body = modal.querySelector("[data-deploy-modal-body]");
  var actions = modal.querySelector("[data-deploy-modal-actions]");

  function show(heading, text, buttons) {
    title.textContent = heading;
    body.textContent = text;
    actions.innerHTML = "";
    (buttons || [{ label: "Close", ghost: true }]).forEach(function (b) {
      var el = document.createElement("button");
      el.type = "button";
      if (b.ghost) el.className = "ghost";
      el.textContent = b.label;
      el.setAttribute("data-deploy-choice", b.id || "close");
      el.addEventListener("click", function () {
        modal.hidden = true;
        if (b.run) b.run();
      });
      actions.appendChild(el);
    });
    modal.hidden = false;
  }

  function chosen() { return form.querySelector('input[name="state"]:checked'); }
  function inForce() {
    return Array.prototype.find.call(
      form.querySelectorAll('input[name="state"]'), function (r) { return r.defaultChecked; });
  }
  function when() { return form.querySelector('input[name="effective_at"]'); }

  // Unchanged means: the same option as the one in force, and for a schedule
  // the same moment. The reported case is Live -> Live.
  function unchanged() {
    var now = chosen(), was = inForce();
    if (!now || !was || now !== was) return false;
    if (now.value !== "scheduled") return true;
    var at = when();
    return !at || at.value === at.defaultValue;
  }

  var ALREADY = {
    live: "This policy is already live. There is nothing to change.",
    held: "This policy is already on hold. There is nothing to change.",
    scheduled: "This policy is already scheduled for that time. There is nothing to change.",
  };

  function save() {
    var data = new FormData(form);
    fetch(form.action, { method: "POST", body: data, headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, body: j }; });
      })
      .then(function (res) {
        if (!res.ok || res.body.error) {
          show("Deployment not saved", res.body.error || "The server refused the change.");
          return;
        }
        // What is now in force becomes the baseline for the next "unchanged".
        form.querySelectorAll('input[name="state"]').forEach(function (r) { r.defaultChecked = r.checked; });
        var at = when();
        if (at) at.defaultValue = at.value;
        var slot = document.querySelector("[data-deploy-pill]");
        if (slot && typeof res.body.pill === "string") slot.innerHTML = res.body.pill;
        show("Deployment saved", res.body.message || "Saved.");
      })
      .catch(function () {
        show("Deployment not saved", "Could not reach the server. Nothing was changed.");
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var now = chosen();
    if (!now) return;

    if (unchanged()) {
      show("Nothing to change", ALREADY[now.value] || "There is nothing to change.");
      return;
    }

    var policy = document.querySelector("form[data-policy-form]");
    if (policy && policy.hasAttribute("data-dirty")) {
      show(
        "Unsaved policy changes",
        "This page has changes to the policy that are not saved yet. Save the policy " +
          "first, or save only the deployment and keep editing.",
        [
          { id: "save-policy", label: "Save policy first", run: function () {
              if (policy.requestSubmit) policy.requestSubmit(); else policy.submit();
            } },
          { id: "deployment-only", label: "Save deployment only", ghost: true, run: save },
          { id: "cancel", label: "Cancel", ghost: true },
        ]
      );
      return;
    }
    save();
  });
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
  // Where the running job is polled. TPC jobs and TAKWERX jobs (W279) live in
  // the same job table but answer on their own routes.
  var statusBase = "/apps/tpc/import/";

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
    fetch(statusBase + encodeURIComponent(id), { headers: { "Accept": "application/json" } })
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
    var btn = e.target.closest("[data-tpc-import], [data-takwerx-import]");
    if (!btn) return;

    // One modal, two catalogs (W279). The TAKWERX import names the build by
    // package + versionCode + ATAK version, and the server re-reads the catalog
    // for the URL and the digest rather than trusting anything sent from here.
    var takwerx = btn.hasAttribute("data-takwerx-import");
    var action = takwerx ? "/apps/takwerx/import" : "/apps/tpc/import";
    statusBase = takwerx ? "/apps/repo/import/" : "/apps/tpc/import/";

    var body = new FormData();
    if (takwerx) {
      body.append("package", btn.getAttribute("data-package"));
      body.append("version_code", btn.getAttribute("data-version-code"));
      body.append("atak_version", btn.getAttribute("data-atak-version"));
    } else {
      body.append("identifier", btn.getAttribute("data-identifier"));
      body.append("product", btn.getAttribute("data-product"));
      body.append("product_version", btn.getAttribute("data-product-version"));
    }
    body.append("label", btn.getAttribute("data-label") || "");
    var token = document.querySelector('input[name="csrf_token"]');
    if (token) body.append("csrf_token", token.value);

    title.textContent = "Importing " + (btn.getAttribute("data-label") || "");
    detail.textContent = takwerx ? "Contacting the TAKWERX catalog…" : "Contacting tak.gov…";
    bytes.textContent = "";
    bar.style.width = "0";
    close.hidden = true;
    modal.hidden = false;

    fetch(action, { method: "POST", body: body })
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

/* --- Play device picker (W312) ----------------------------------------------
   Type -> Manufacturer -> Model. Each select narrows the next; only the Model
   select (`data-play-device`) is sent with an import. Options carry their
   type and maker as data attributes, so the server renders one flat list and
   this only hides what doesn't match. */
(function () {
  document.querySelectorAll("[data-play-picker]").forEach(function (picker) {
    var kind = picker.querySelector('[data-play-tier="kind"]');
    var maker = picker.querySelector('[data-play-tier="maker"]');
    var model = picker.querySelector("[data-play-device]");
    if (!kind || !maker || !model) return;
    // W341: the yellow "generic profile" banner, shown while the Flagship is
    // the chosen model, however it came to be chosen.
    var generic = picker.parentNode.querySelector("[data-play-generic-warning]");
    function warn() {
      if (generic) generic.hidden = model.value !== generic.getAttribute("data-flagship");
    }
    var all = Array.prototype.slice.call(model.options).map(function (o) {
      return { value: o.value, label: o.textContent, kind: o.getAttribute("data-kind"),
               maker: o.getAttribute("data-maker") };
    });

    function fill(select, values, keep) {
      select.innerHTML = "";
      values.forEach(function (v) {
        var o = document.createElement("option");
        o.value = v.value; o.textContent = v.label;
        if (v.kind) o.setAttribute("data-kind", v.kind);
        if (v.maker) o.setAttribute("data-maker", v.maker);
        select.appendChild(o);
      });
      var still = values.some(function (v) { return v.value === keep; });
      select.value = still ? keep : (values[0] ? values[0].value : "");
    }

    function makers() {
      var seen = {}, out = [];
      all.forEach(function (o) {
        if (o.kind === kind.value && !seen[o.maker]) {
          seen[o.maker] = true; out.push({ value: o.maker, label: o.maker });
        }
      });
      fill(maker, out, maker.value);
    }

    function models() {
      fill(model, all.filter(function (o) {
        return o.kind === kind.value && o.maker === maker.value;
      }), model.value);
    }

    kind.addEventListener("change", function () { makers(); models(); warn(); });
    maker.addEventListener("change", function () { models(); warn(); });
    model.addEventListener("change", warn);
    makers();
    models();
    warn();
  });
})();

/* --- ATAK plugin compatibility -------------------------------------------
   ATAK's `isTakCompatible` (W305): a plugin built for the same or an *older*
   ATAK (from 4.10.0 on) loads, and gets a quiet note. One built for a *newer*
   ATAK, or older than 4.10.0, is refused, and gets a warning: it installs and
   then never appears, which looks like an MDM fault and is not one. Warn, never
   block. Mirrors `atak_compat.level` on the server.

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

  // Numbers, not text: as text "5.10.0" sorts below "5.9.0".
  function numbers(version) {
    var parts = String(version).split(".");
    for (var i = 0; i < parts.length; i++) {
      if (!/^\d+$/.test(parts[i])) return null;
      parts[i] = parseInt(parts[i], 10);
    }
    return parts;
  }

  function compare(a, b) {
    for (var i = 0; i < Math.max(a.length, b.length); i++) {
      // Missing parts are zero, so "5.8" is the same line as "5.8.0".
      var x = i < a.length ? a[i] : 0;
      var y = i < b.length ? b[i] : 0;
      if (x !== y) return x < y ? -1 : 1;
    }
    return 0;
  }

  var OLDEST_ACCEPTED = [4, 10, 0];

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
      box.classList.remove("note");
      box.removeAttribute("data-compat");

      var target = lineOf(row.querySelector('select[name$="__version_choice"]'));
      if (!atakLine || !target) return;
      var plugin = numbers(target);
      var atak = numbers(atakLine);
      if (!plugin || !atak || compare(plugin, atak) === 0) return;

      if (compare(plugin, atak) < 0 && compare(plugin, OLDEST_ACCEPTED) >= 0) {
        box.textContent =
          "Built for ATAK " + target + ". This policy installs ATAK " + atakLine +
          ", which loads plugins built for older ATAK. Use a build for " + atakLine +
          " if the vendor has one, in case the plugin relies on something ATAK " +
          "has since changed.";
        box.classList.add("note");
        box.setAttribute("data-compat", "note");
      } else {
        box.textContent =
          "This plugin is built for ATAK " + target + ", but this policy installs " +
          "ATAK " + atakLine + ". ATAK will refuse to load it: it installs and then " +
          "does not appear. Assigning it anyway is allowed.";
        box.setAttribute("data-compat", "warning");
      }
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
// ⚠️ One filter per panel, not per page (W279): TPC and TAKWERX each have a
// catalog table, and a page-wide lookup would wire the second box to the first
// table.
Array.prototype.forEach.call(document.querySelectorAll("[data-plugin-filter]"), function (box) {
  var panel = box.closest(".panel") || document;
  var table = panel.querySelector(".tpc-table");
  if (!table) return;

  var body = table.tBodies[0];
  if (!body) return;

  var count = panel.querySelector("[data-plugin-filter-count]");
  var total = panel.querySelector("[data-plugin-total]");
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
});

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

/* Matches routes._duration_label: days and hours past a day, hours and minutes
   past an hour, m:ss below. A W330 timer can run 30 days, and "43199:59" is
   not a time anyone can read. */
function countdownLabel(left) {
  if (left >= 86400) return Math.floor(left / 86400) + "d " + Math.floor(left % 86400 / 3600) + "h";
  if (left >= 3600) return Math.floor(left / 3600) + "h " + Math.floor(left % 3600 / 60) + "m";
  var m = Math.floor(left / 60);
  var s = left % 60;
  return m + ":" + (s < 10 ? "0" : "") + s;
}

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
      value.textContent = countdownLabel(left);
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

  /* ⚠️ **A package on the list is not offered again (W340).** Operator: "when i
     add a data package to the install list, remove it from the available
     dropdown ... it cannot be installed twice on the same policy." The server
     refuses a duplicate too; this keeps the page from offering one.

     Options are removed and re-added rather than hidden: browsers honour
     `hidden` on an <option> inconsistently, and one that can still be chosen by
     keyboard is the bug itself. `known` keeps every package this page has seen,
     in the library's order, so a removed row's package returns to its place --
     including one uploaded or built on this page, which the server never
     rendered as an option. */
  var promptOption = pick.options[0];
  var promptText = promptOption ? promptOption.textContent : "";
  var known = [];
  Array.prototype.forEach.call(pick.options, function (o) {
    if (o.value) known.push({ id: o.value, label: o.textContent.trim() });
  });

  function rowIds() {
    var ids = {};
    set.querySelectorAll('input[name="data_packages__file_id"]').forEach(function (input) {
      if (input.value) ids[input.value] = true;
    });
    return ids;
  }

  function remember(row) {
    var input = row.querySelector && row.querySelector('input[name="data_packages__file_id"]');
    if (!input || !input.value) return;
    for (var i = 0; i < known.length; i++) if (known[i].id === input.value) return;
    var label = row.querySelector("[data-package-label]") || row.querySelector("strong");
    known.push({ id: input.value, label: label ? label.textContent.trim() : input.value });
  }

  function offerUnused() {
    var used = rowIds();
    while (pick.options.length > (promptOption ? 1 : 0)) pick.remove(pick.options.length - 1);
    var offered = 0;
    known.forEach(function (p) {
      if (used[p.id]) return;
      pick.add(new Option(p.label, p.id));
      offered++;
    });
    if (promptOption) {
      promptOption.textContent = offered || !known.length
        ? promptText
        : "— every data package is already on this policy —";
    }
    pick.disabled = !offered && known.length > 0;
    pick.value = "";
  }

  // Rows arrive from three places (this picker, the upload, the build) and go
  // through the page-wide Remove button, so the list is watched rather than
  // each of those told to call back here.
  new MutationObserver(function (changes) {
    // Remembered as they arrive, so a removed row's package is already known.
    changes.forEach(function (c) { Array.prototype.forEach.call(c.addedNodes, remember); });
    offerUnused();
  }).observe(set, { childList: true });
  set.querySelectorAll(".rs-row").forEach(remember);
  offerUnused();

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

  /* ⚠️ **The site-wide upload dialog, not a page-only one (W342).** Operator:
     "uploading a data package should have the same upload modal behavior of the
     upload to content page." Progress, speed, time left, a real Cancel, the
     W276 lock -- and then the manifest check, whose refusal is the whole point
     of validating here, shown in the same dialog with the server's own words.
     It never navigates: the editor holds an entire unsaved policy. */
  var upload = set.querySelector("[data-package-upload]");
  var openUpload = set.querySelector("[data-package-upload-open]");

  // Only for the manifest case: it explains that ATAK would have taken the
  // file, which is reassurance for that refusal and noise for any other.
  var MANIFEST_NOTE = "ATAK would unpack a zip without a manifest, as a plain " +
    "archive with none of the manifest's placement rules. ATLAS refuses it so " +
    "that what lands on a device is predictable, not because the file is broken.";

  /** The server's JSON answer, or {} when it sent none (a proxy's 502 page). */
  function answer(xhr) {
    try { return JSON.parse(xhr.responseText) || {}; } catch (e) { return {}; }
  }

  if (openUpload && upload) {
    openUpload.addEventListener("click", function () { upload.click(); });
  }

  if (upload && window.AtlasUpload) {
    upload.addEventListener("change", function () {
      var file = upload.files && upload.files[0];
      if (!file) return;
      var body = csrf(new FormData());
      body.append("file", file);
      var sent = window.AtlasUpload.send({
        url: "/policies/data-package/upload",
        body: body,
        name: file.name,
        processing: "Uploaded — the server is checking the data package…",
        cancelled: "No data package was added.",
        onAnswer: function (xhr, ui) {
          var token = document.querySelector('input[name="csrf_token"]');
          window.AtlasDataPackages.answer(xhr, ui, token ? token.value : "").then(function (v) {
            if (v.aborted) { ui.show("Upload cancelled", "No data package was added."); return; }
            if (v.ok) {
              // Accepted: close and let the row be the confirmation, rather than
              // making the operator dismiss a dialog to see what they added. A
              // replaced package may already be on this policy: that row stays.
              ui.done();
              addRow(v.res.id, v.res.name);
              var count = v.res.contents;
              say(v.res.name + (v.res.replaced ? " replaced" : " added") +
                  (count ? " (" + count + (count === 1 ? " file)" : " files)") : ""));
              return;
            }
            if (v.skipped) { ui.done(); say(v.text); return; }
            // The server's words, not ours: it knows *why* the manifest failed.
            ui.show("Package refused", v.text,
                    v.text.indexOf("MANIFEST") !== -1 ? MANIFEST_NOTE : "");
          });
        }
      });
      upload.value = "";
      if (!sent) say("Another upload is still running.", true);
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
    var names = [];
    fileList.querySelectorAll("[data-ppkg-file]").forEach(function (input) {
      if (input.files && input.files[0]) names.push(input.files[0].name);
    });
    // The same dialog as every other upload (W342). A refusal goes back to this
    // form, where the files that caused it can be changed.
    window.AtlasUpload.send({
      url: "/policies/data-package/create",
      body: body,
      name: names.length === 1 ? names[0] : names.length + " files",
      processing: "Uploaded — the server is building the data package…",
      cancelled: "No data package was made.",
      onAnswer: function (xhr, ui) {
        var res = answer(xhr);
        ui.done();
        if (xhr.status >= 200 && xhr.status < 300 && res.id) {
          addRow(res.id, res.name);
          say(res.name + " created");
          frame.hidden = true;
          return;
        }
        fail(res.error || window.AtlasUpload.refusal(xhr.status));
      },
      onGone: function (ui) {
        ui.done();
        fail("Lost contact with the server before it answered; the package was not made.");
      }
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
  if (!open || !input || !template) return;

  function say(message, bad) {
    status.textContent = message || "";
    status.style.color = bad ? "var(--bad)" : "";
  }

  open.addEventListener("click", function () { input.click(); });

  /** The server's JSON answer, or {} when it sent none (a proxy's 502 page). */
  function answer(xhr) {
    try { return JSON.parse(xhr.responseText) || {}; } catch (e) { return {}; }
  }

  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file || !window.AtlasUpload) return;

    var body = new FormData();
    var token = document.querySelector('input[name="csrf_token"]');
    if (token) body.append("csrf_token", token.value);
    body.append("file", file);

    // The site-wide upload dialog (W342): terrain archives are often the largest
    // thing an operator uploads, so they get progress and a real Cancel too.
    var sent = window.AtlasUpload.send({
      url: "/policies/dted/upload",
      body: body,
      name: file.name,
      processing: "Uploaded — the server is finding the cell folders. A nested " +
        "archive is repacked so ATAK can see it, which can take a minute for a large one…",
      cancelled: "No terrain archive was added.",
      onAnswer: function (xhr, ui) {
        var res = answer(xhr);
        if (!(xhr.status >= 200 && xhr.status < 300 && res.id)) {
          var reason = res.error || window.AtlasUpload.refusal(xhr.status);
          ui.show("Archive refused", reason);
          say(reason, true);
          return;
        }
        // A repack changed the operator's file, so the dialog stays up and says
        // so. Silently handing back a different archive than the one uploaded
        // is how checksums stop matching with nobody knowing why.
        if (res.repacked) ui.show("Terrain repacked", res.summary || "", res.note || "");
        else ui.done();

        var existing = set.querySelectorAll('input[name="dted_archives__file_id"]');
        for (var i = 0; i < existing.length; i++) {
          if (existing[i].value === res.id) { say(res.name + " is already on this policy"); return; }
        }
        var row = template.content.firstElementChild.cloneNode(true);
        row.querySelector('[name="dted_archives__file_id"]').value = res.id;
        var label = row.querySelector("[data-dted-label]");
        if (label) label.textContent = res.name;
        template.parentNode.insertBefore(row, template);
        set.dispatchEvent(new Event("input", { bubbles: true }));
        // The summary is the point: 11 cells is a different thing from 1, and
        // that is how someone notices they grabbed the wrong archive.
        say(res.name + " added — " + res.summary + (res.repacked ? " (repacked)" : ""));
      }
    });
    input.value = "";
    if (!sent) say("Another upload is still running.", true);
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

    // The Play panel's "Download as" choice rides with the search too (W313):
    // an exact package id names the device it will be fetched as, and that must
    // be the one the operator picked, not an account default.
    var device = panel.querySelector("[data-play-device]");
    fetch(searchUrl + "?q=" + encodeURIComponent(q) +
          (device && device.value ? "&device_profile=" + encodeURIComponent(device.value) : ""))
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
    // ⚠️ Per-fetch device profile (W251). Only the Play panel renders the
    // picker, and only the Play source honours the field, so the repositories
    // panel sends nothing here.
    var device = panel.querySelector("[data-play-device]");
    if (device && device.value) body.append("device_profile", device.value);

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

/* --- Pick into a list (W271, W272) ------------------------------------------
   Any `select[multiple][data-multiselect]` becomes two parts: an "add"
   dropdown listing only what is not chosen yet, and the chosen items as a list
   beneath it, each with its own remove button. Items are named by the option
   text, with the option's `data-detail` underneath.

   ⚠️ **The native select stays the source of truth.** Picking sets the
   option's `selected`; removing clears it; nothing else is posted. So the
   form submits exactly what a checkbox list did, the routes are untouched,
   and a page whose script fails to load still has a working multi-select.

   ⚠️ **The dropdown stays open across picks**, so several can be added in a
   row; Escape or a click elsewhere closes it (W272).

   ⚠️ **Each select is enhanced inside its own try.** A top-level throw in this
   file stops every later block from running; one malformed select must not
   take the rest of the page with it. */
(function () {
  function el(tag, cls) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    return node;
  }

  function detailOf(option) {
    var detail = option.getAttribute("data-detail") || "";
    return detail && detail !== option.textContent ? detail : "";
  }

  function nameBlock(option) {
    var text = el("span", "ms-text");
    var name = el("span", "ms-name");
    name.textContent = option.textContent;
    text.appendChild(name);
    var detail = detailOf(option);
    if (detail) {
      var sub = el("span", "ms-detail mono");
      sub.textContent = detail;
      text.appendChild(sub);
    }
    return text;
  }

  function enhance(select) {
    if (select.getAttribute("data-multiselect-ready")) return;
    select.setAttribute("data-multiselect-ready", "1");

    var wrap = el("div", "ms");
    var toggle = el("button", "ms-toggle");
    toggle.type = "button";
    toggle.id = (select.id || "ms") + "-toggle";
    toggle.setAttribute("aria-haspopup", "listbox");
    toggle.setAttribute("aria-expanded", "false");
    toggle.appendChild(el("span", "ms-add-label"));
    toggle.firstChild.textContent = select.getAttribute("data-add-label") || "Add…";
    toggle.appendChild(el("span", "ms-caret"));

    var panel = el("div", "ms-panel");
    panel.hidden = true;
    var search = el("input", "ms-search");
    search.type = "search";
    search.placeholder = "Search…";
    search.setAttribute("aria-label", "Search");
    var menu = el("div", "ms-list");
    menu.setAttribute("role", "listbox");
    var nomatch = el("p", "ms-empty muted");
    var chosen = el("ul", "ms-chosen");
    chosen.setAttribute("aria-live", "polite");
    var none = el("p", "ms-none muted");
    none.textContent = select.getAttribute("data-empty-label") || "Nothing chosen.";

    var options = Array.prototype.slice.call(select.options);
    var picks = options.map(function (option) {
      var row = el("button", "ms-row");
      row.type = "button";
      row.setAttribute("role", "option");
      row.appendChild(nameBlock(option));
      row.addEventListener("click", function () {
        option.selected = true;
        render();
        search.focus();
      });
      menu.appendChild(row);
      return {
        option: option,
        row: row,
        haystack: (option.textContent + " " + (option.getAttribute("data-detail") || "")).toLowerCase(),
      };
    });

    function render() {
      /* The chosen list, in option order: the order the page sorted them in. */
      chosen.textContent = "";
      var count = 0;
      options.forEach(function (option) {
        if (!option.selected) return;
        count += 1;
        var item = el("li", "ms-item");
        item.appendChild(nameBlock(option));
        var remove = el("button", "ms-remove");
        remove.type = "button";
        remove.textContent = "✕";
        remove.setAttribute("aria-label", "Remove " + option.textContent);
        remove.title = "Remove";
        remove.addEventListener("click", function () {
          option.selected = false;
          render();
          /* Keep focus somewhere sensible: the next remove button, else the
             dropdown. Focus on a node that was just thrown away is lost. */
          var next = chosen.querySelector(".ms-remove");
          (next || toggle).focus();
        });
        item.appendChild(remove);
        chosen.appendChild(item);
      });
      chosen.hidden = count === 0;
      none.hidden = count !== 0;
      filter();
    }

    function filter() {
      var needle = search.value.trim().toLowerCase();
      var available = 0;
      var shown = 0;
      picks.forEach(function (p) {
        var free = !p.option.selected;
        if (free) available += 1;
        var hit = free && (!needle || p.haystack.indexOf(needle) !== -1);
        p.row.hidden = !hit;
        if (hit) shown += 1;
      });
      if (!available) {
        nomatch.textContent = "Everything is already in the list.";
        nomatch.hidden = false;
      } else {
        nomatch.textContent = "No matches.";
        nomatch.hidden = shown !== 0;
      }
    }

    function open(yes) {
      panel.hidden = !yes;
      toggle.setAttribute("aria-expanded", yes ? "true" : "false");
      if (yes) {
        search.value = "";
        filter();
        search.focus();
      }
    }

    toggle.addEventListener("click", function () { open(panel.hidden); });
    search.addEventListener("input", filter);
    wrap.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !panel.hidden) {
        event.preventDefault();
        open(false);
        toggle.focus();
      }
    });
    document.addEventListener("click", function (event) {
      if (!panel.hidden && !wrap.contains(event.target)) open(false);
    });

    /* A label pointing at the native select would now focus something hidden;
       point it at the control the operator actually uses. */
    if (select.id) {
      var label = document.querySelector('label[for="' + select.id + '"]');
      if (label) label.htmlFor = toggle.id;
    }

    panel.appendChild(search);
    panel.appendChild(menu);
    panel.appendChild(nomatch);
    var picker = el("div", "ms-picker");
    picker.appendChild(toggle);
    picker.appendChild(panel);
    wrap.appendChild(picker);
    wrap.appendChild(chosen);
    wrap.appendChild(none);
    select.classList.add("ms-native");
    select.parentNode.insertBefore(wrap, select.nextSibling);
    render();
  }

  Array.prototype.forEach.call(
    document.querySelectorAll("select[multiple][data-multiselect]"),
    function (select) {
      try {
        enhance(select);
      } catch (err) {
        /* Leave the native select showing: plain, but it still posts. */
        select.classList.remove("ms-native");
        if (window.console) console.warn("multiselect:", err);
      }
    }
  );
})();

/* --- Web shortcut icons (W336, W337) -----------------------------------------
   <div data-icon-picker> from the `icon_picker` macro. Every icon ends up as one
   432 px PNG in the hidden `icon` file input, drawn here:

     * From the website: POST /apps/shortcuts/site-icon fetches the site's own
       icon (the server only fetches; this draws). None, or one under 48 px,
       gives the letter icon instead.
     * Custom picture: the cropper (any image, drag and zoom).
     * Keep (edit only): nothing is sent; the server keeps its icon.

   ⚠️ Pictures are read as data: URLs, never URL.createObjectURL: the console's
   CSP allows data: images and not blob: ones, and a blob URL would leave the
   canvas silently empty.

   The arithmetic and the letter's choices are pure and exported as
   window.AtlasIconCrop, so scripts/check_icon_cropper.js tests them without a
   canvas. */

var AtlasIconCrop = (function () {
  /** The scale at which the picture just covers the square. */
  function coverScale(width, height, size) {
    return Math.max(size / width, size / height);
  }

  /** The scale at which the whole picture fits inside the square. */
  function containScale(width, height, size) {
    return Math.min(size / width, size / height);
  }

  /** Keep the picture covering the square: offset in [size - drawn, 0]. */
  function clampOffset(offset, drawn, size) {
    return Math.min(0, Math.max(size - drawn, offset));
  }

  /** New offset after scaling about the square's centre. */
  function zoomAbout(offset, oldScale, newScale, size) {
    var centre = size / 2;
    return centre - (centre - offset) * (newScale / oldScale);
  }

  /** The letter for a name: its first letter or digit, upper-cased. */
  function letterFor(name) {
    var match = String(name || "").trim().match(/[\p{L}\p{N}]/u);
    return match ? match[0].toLocaleUpperCase() : "?";
  }

  var COLOURS = ["#1f5fbf", "#2e7d32", "#c62828", "#6a1b9a", "#ef6c00",
                 "#00838f", "#ad1457", "#4e342e"];

  /** A colour chosen by the name, so a name always gets the same one. */
  function colourFor(name) {
    var text = String(name || "").trim().toLowerCase();
    var hash = 0;
    for (var i = 0; i < text.length; i++) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    return COLOURS[hash % COLOURS.length];
  }

  /** Under this, a site's icon is a favicon stretched past recognition. */
  var MIN_SITE_ICON = 48;

  return { coverScale: coverScale, containScale: containScale, clampOffset: clampOffset,
           zoomAbout: zoomAbout, letterFor: letterFor, colourFor: colourFor,
           MIN_SITE_ICON: MIN_SITE_ICON, OUTPUT: 432 };
})();
window.AtlasIconCrop = AtlasIconCrop;

(function () {
  var C = AtlasIconCrop;

  function readAsDataUrl(blob) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(reader.result); };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  function loadImage(src) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = reject;
      img.src = src;
    });
  }

  function drawLetter(ctx, size, name) {
    ctx.fillStyle = C.colourFor(name);
    ctx.fillRect(0, 0, size, size);
    ctx.fillStyle = "#ffffff";
    ctx.font = "600 " + Math.round(size * 0.56) + "px system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(C.letterFor(name), size / 2, size * 0.54);
  }

  /** The whole picture, as large as fits, centred. */
  function drawContained(ctx, size, img) {
    var w = img.naturalWidth, h = img.naturalHeight;
    // An SVG with no size of its own is drawn to fill the square.
    if (!w || !h) w = h = size;
    var s = C.containScale(w, h, size);
    ctx.drawImage(img, (size - w * s) / 2, (size - h * s) / 2, w * s, h * s);
  }

  function canvasToBlob(canvas) {
    return new Promise(function (resolve, reject) {
      try {
        canvas.toBlob(function (blob) { blob ? resolve(blob) : reject(new Error("no PNG")); }, "image/png");
      } catch (e) {
        // A tainted canvas (an SVG that pulled in something) refuses; the
        // caller falls back to the letter.
        reject(e);
      }
    });
  }

  /* ----- the cropper (Custom picture) -------------------------------------- */

  function setUpCropper(box) {
    var source = box.querySelector("[data-cropper-source]");
    var stage = box.querySelector("[data-cropper-stage]");
    var canvas = box.querySelector("[data-cropper-canvas]");
    var zoom = box.querySelector("[data-cropper-zoom]");
    if (!source || !canvas || !zoom) return null;

    var size = canvas.width;
    var state = { img: null, base: 1, scale: 1, x: 0, y: 0 };
    var listeners = [];

    function drawn() {
      return { w: state.img.naturalWidth * state.scale, h: state.img.naturalHeight * state.scale };
    }
    function clamp() {
      var d = drawn();
      state.x = C.clampOffset(state.x, d.w, size);
      state.y = C.clampOffset(state.y, d.h, size);
    }
    function paint() {
      var ctx = canvas.getContext && canvas.getContext("2d");
      if (!ctx || !state.img) return;
      var d = drawn();
      ctx.clearRect(0, 0, size, size);
      ctx.drawImage(state.img, state.x, state.y, d.w, d.h);
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,0.45)";
      ctx.beginPath();
      ctx.rect(0, 0, size, size);
      ctx.arc(size / 2, size / 2, size / 2, 0, Math.PI * 2, true);
      ctx.fill("evenodd");
      ctx.restore();
    }
    function changed() {
      paint();
      listeners.forEach(function (fn) { fn(); });
    }

    source.addEventListener("change", function () {
      var file = source.files && source.files[0];
      if (!file) return;
      readAsDataUrl(file).then(loadImage).then(function (img) {
        state.img = img;
        state.base = C.coverScale(img.naturalWidth, img.naturalHeight, size);
        state.scale = state.base;
        zoom.value = "1";
        var d = drawn();
        state.x = (size - d.w) / 2;
        state.y = (size - d.h) / 2;
        stage.hidden = false;
        changed();
      }, function () {
        state.img = null;
        stage.hidden = true;
        window.alert("That file could not be read as a picture.");
        source.value = "";
      });
    });

    zoom.addEventListener("input", function () {
      if (!state.img) return;
      var next = state.base * parseFloat(zoom.value);
      state.x = C.zoomAbout(state.x, state.scale, next, size);
      state.y = C.zoomAbout(state.y, state.scale, next, size);
      state.scale = next;
      clamp();
      changed();
    });

    var drag = null;
    canvas.addEventListener("pointerdown", function (e) {
      if (!state.img) return;
      drag = { x: e.clientX, y: e.clientY, ox: state.x, oy: state.y };
      if (canvas.setPointerCapture) canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!drag) return;
      // The canvas may be drawn smaller than its pixel size on a phone.
      var ratio = size / (canvas.getBoundingClientRect().width || size);
      state.x = drag.ox + (e.clientX - drag.x) * ratio;
      state.y = drag.oy + (e.clientY - drag.y) * ratio;
      clamp();
      changed();
    });
    ["pointerup", "pointercancel"].forEach(function (type) {
      canvas.addEventListener(type, function () { drag = null; });
    });

    return {
      source: source,
      hasImage: function () { return !!state.img; },
      onChange: function (fn) { listeners.push(fn); },
      render: function () {
        var out = document.createElement("canvas");
        out.width = out.height = C.OUTPUT;
        var f = C.OUTPUT / size;
        var d = drawn();
        out.getContext("2d").drawImage(state.img, state.x * f, state.y * f, d.w * f, d.h * f);
        return canvasToBlob(out);
      }
    };
  }

  /* ----- the picker -------------------------------------------------------- */

  function setUpPicker(box) {
    var form = box.closest("form");
    var nameInput = document.querySelector(box.getAttribute("data-name-input"));
    var urlInput = document.querySelector(box.getAttribute("data-url-input"));
    var output = box.querySelector("[data-cropper-output]");
    var sourceField = box.querySelector("[data-icon-source]");
    var sitePanel = box.querySelector("[data-icon-site-panel]");
    var customPanel = box.querySelector("[data-icon-custom-panel]");
    var preview = box.querySelector("[data-icon-preview]");
    var status = box.querySelector("[data-icon-status]");
    var cropBox = box.querySelector("[data-icon-cropper]");
    var cropper = cropBox ? setUpCropper(cropBox) : null;
    if (!form || !output || !sourceField || !nameInput || !urlInput) return;

    var fresh = false;
    // The last site lookup, by address: {url, img|null, svg}.
    var site = null;
    var pending = null;
    var timer = null;

    function choice() {
      var checked = box.querySelector("[data-icon-choice]:checked");
      return checked ? checked.value : "site";
    }

    function say(text) { if (status) status.textContent = text; }

    /** Look up the site's icon for the current address, once per address. */
    function lookUp() {
      var url = urlInput.value.trim();
      if (!/^https?:\/\/[^/?#]+/i.test(url)) {
        site = null;
        return Promise.resolve(null);
      }
      if (site && site.url === url) return Promise.resolve(site);
      if (pending && pending.url === url) return pending.promise;
      var body = new FormData();
      body.append("url", url);
      var token = form.querySelector('input[name="csrf_token"]');
      if (token) body.append("csrf_token", token.value);
      var promise = fetch("/apps/shortcuts/site-icon", { method: "POST", body: body, credentials: "same-origin" })
        .then(function (response) {
          if (response.status !== 200) return null;
          return response.blob();
        })
        .then(function (blob) {
          if (!blob) return null;
          var svg = /svg/.test(blob.type);
          return readAsDataUrl(blob).then(loadImage).then(function (img) {
            var big = svg || (img.naturalWidth >= C.MIN_SITE_ICON && img.naturalHeight >= C.MIN_SITE_ICON);
            return big ? { img: img, svg: svg } : null;
          }, function () { return null; });
        })
        .catch(function () { return null; })
        .then(function (found) {
          site = { url: url, img: found ? found.img : null, svg: found ? found.svg : false };
          pending = null;
          return site;
        });
      pending = { url: url, promise: promise };
      return promise;
    }

    /** Draw the site icon, or the letter, on a canvas of any size. */
    function drawSite(canvas, result) {
      var ctx = canvas.getContext && canvas.getContext("2d");
      if (!ctx) return "letter";
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (result && result.img) {
        try {
          drawContained(ctx, canvas.width, result.img);
          return "site";
        } catch (e) { /* fall through to the letter */ }
      }
      drawLetter(ctx, canvas.width, nameInput.value);
      return "letter";
    }

    function refreshPreview() {
      if (choice() !== "site" || !preview) return;
      var url = urlInput.value.trim();
      if (!url) { say("Enter the web address to see the website's icon."); return; }
      say("Looking for the website's icon…");
      lookUp().then(function (result) {
        if (urlInput.value.trim() !== url) return;
        var used = drawSite(preview, result);
        say(used === "site"
          ? "The website's own icon."
          : "The website has no usable icon, so the shortcut shows the first letter of its name.");
      });
    }

    function showChoice() {
      var c = choice();
      if (sitePanel) sitePanel.hidden = c !== "site";
      if (customPanel) customPanel.hidden = c !== "custom";
      if (cropper) cropper.source.required = c === "custom";
      fresh = false;
      if (c === "site") refreshPreview();
    }

    box.querySelectorAll("[data-icon-choice]").forEach(function (radio) {
      radio.addEventListener("change", showChoice);
    });
    urlInput.addEventListener("input", function () {
      fresh = false;
      clearTimeout(timer);
      timer = setTimeout(refreshPreview, 600);
    });
    nameInput.addEventListener("input", function () {
      fresh = false;
      // The letter follows the name; a found icon does not change.
      if (choice() === "site" && site && !site.img && preview) drawSite(preview, site);
    });
    if (cropper) cropper.onChange(function () { fresh = false; });

    function attach(blob, source) {
      var transfer = new DataTransfer();
      transfer.items.add(new File([blob], "icon.png", { type: "image/png" }));
      output.files = transfer.files;
      sourceField.value = source;
      fresh = true;
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    }

    form.addEventListener("submit", function (e) {
      if (fresh) return;
      var c = choice();
      if (c === "keep") {
        sourceField.value = "";
        return;
      }
      e.preventDefault();
      if (c === "custom") {
        if (!cropper || !cropper.hasImage()) {
          window.alert("Choose a picture for the icon, or pick From the website.");
          return;
        }
        cropper.render().then(function (blob) { attach(blob, "custom"); });
        return;
      }
      say("Getting the website's icon…");
      lookUp().then(function (result) {
        var out = document.createElement("canvas");
        out.width = out.height = C.OUTPUT;
        var used = drawSite(out, result);
        return canvasToBlob(out).then(function (blob) { return [blob, used]; }, function () {
          // A tainted canvas: draw the letter on a clean one.
          var clean = document.createElement("canvas");
          clean.width = clean.height = C.OUTPUT;
          drawLetter(clean.getContext("2d"), C.OUTPUT, nameInput.value);
          return canvasToBlob(clean).then(function (blob) { return [blob, "letter"]; });
        });
      }).then(function (pair) { attach(pair[0], pair[1]); });
    });

    showChoice();
  }

  document.querySelectorAll("[data-icon-picker]").forEach(setUpPicker);
})();
