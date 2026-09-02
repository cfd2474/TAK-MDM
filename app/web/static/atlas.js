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
