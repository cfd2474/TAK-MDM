/*
 * Copyright 2026 TAK-Solutions LLC
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
 */

/*
 * The dashboard's refresh (W440): every 60 s while the tab is visible, and at
 * once on coming back to a tab left longer than that.
 *
 * It only rewrites the `data-dash-*` hooks the server drew; the page is whole
 * without it. ⚠️ A failed refresh says so and keeps the time of the figures it
 * shows: numbers that silently stopped updating are worse than none. A
 * sign-in that expired comes back as an HTML page, not JSON, and is treated
 * the same way.
 */

(function () {
  "use strict";

  var PERIOD_MS = 60 * 1000;
  var CIRCUMFERENCE = 289.03;
  var asOfEl = document.querySelector("[data-dash-asof]");
  if (!asOfEl) return;

  var lastGood = Date.now();
  var timer = null;

  function clock(date) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function say(text) { asOfEl.textContent = text; }

  function ringLevel(percent) {
    if (percent === null) return "";
    return percent >= 90 ? "bad" : percent >= 75 ? "warn" : "";
  }

  function drawRing(ring) {
    var root = document.querySelector('[data-dash-ring="' + ring.key + '"]');
    if (!root) return;
    var fill = root.querySelector(".dash-ring-fill");
    var value = root.querySelector(".dash-ring-value");
    var known = ring.percent !== null;
    fill.hidden = !known;
    fill.setAttribute("class", "dash-ring-fill " + ringLevel(ring.percent));
    fill.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE * (1 - (known ? ring.percent : 0) / 100)));
    value.textContent = known ? ring.percent.toFixed(1) + "%" : "—";
    root.querySelector("svg").setAttribute("aria-label",
      ring.label + " " + (known ? ring.percent.toFixed(1) + "%" : "unknown"));
    root.querySelector(".dash-ring-detail").textContent = ring.detail;
  }

  function drawTile(tile) {
    var root = document.querySelector('[data-dash-tile="' + tile.key + '"]');
    if (!root) return;
    root.className = "dash-tile " + tile.level;
    root.title = tile.detail;
    root.querySelector(".dash-tile-value").textContent = tile.value;
    root.querySelector(".dash-tile-detail").textContent = tile.detail;
  }

  // ----------------------------------------------------------------------- //
  // W442: summary, banner, the fleet bar and the group bars
  // ----------------------------------------------------------------------- //

  var buckets = [];
  var groups = [];
  var sortKey = "stale";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function fmt(n) { return Number(n).toLocaleString(); }

  function barNote(c) {
    return fmt(c.total) + " · " + fmt(c.stale) + " stale (" + Math.round(c.stale_share) + "%) · " + fmt(c.old) + " >1y";
  }

  function bar(counts, scale) {
    var track = el("div", "dash-bar-track");
    var inner = el("div", "dash-bar");
    inner.style.width = scale + "%";
    buckets.forEach(function (b) {
      var n = counts.buckets[b.key];
      if (!n) return;
      var seg = el("span", "dash-seg b-" + b.key);
      seg.style.width = (n * 100 / counts.total) + "%";
      seg.title = b.label + ": " + n;
      inner.appendChild(seg);
    });
    track.appendChild(inner);
    return track;
  }

  var MEASURES = {
    stale: function (g) { return g.stale; },
    old: function (g) { return g.old; },
    share: function (g) { return g.stale_share; },
    total: function (g) { return g.total; },
  };

  function drawGroups() {
    var root = document.querySelector("[data-dash-groups]");
    if (!root) return;
    var measure = MEASURES[sortKey];
    var sorted = groups.slice().sort(function (a, b) {
      return (measure(b) - measure(a)) || a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
    var largest = Math.max.apply(null, [1].concat(groups.map(function (g) { return g.total; })));
    root.textContent = "";
    sorted.forEach(function (g) {
      var row = el("div", "dash-bar-row");
      row.appendChild(el("div", "dash-bar-name", g.name));
      row.appendChild(bar(g, g.total * 100 / largest));
      row.appendChild(el("div", "dash-bar-note muted", barNote(g)));
      root.appendChild(row);
    });
    var note = document.querySelector("[data-dash-groups-note]");
    if (note) {
      note.textContent = "All " + groups.length + " group" + (groups.length === 1 ? "" : "s") +
        "; bar length is device count. A device in several groups counts in each.";
    }
  }

  function drawFleet(view) {
    buckets = view.buckets;
    groups = view.fleet.groups;
    var f = view.fleet;
    var set = function (sel, text) { var n = document.querySelector(sel); if (n) n.textContent = text; };
    set("[data-dash-summary]", view.summary);
    set("[data-dash-fleet-details]", view.fleet_details);
    set("[data-dash-fleet-name]", "All " + fmt(f.total) + " devices");
    set("[data-dash-fleet-note]", barNote(f));
    var holder = document.querySelector("[data-dash-fleet-bar]");
    if (holder) { holder.textContent = ""; holder.appendChild(bar(f, 100)); }
    var table = document.querySelector("[data-dash-fleet-table]");
    if (table) {
      table.textContent = "";
      buckets.forEach(function (b) {
        var n = f.buckets[b.key];
        var tr = el("tr");
        tr.appendChild(el("td", "muted", b.label));
        tr.appendChild(el("td", "", fmt(n) + " (" + Math.round(f.total ? n * 100 / f.total : 0) + "%)"));
        table.appendChild(tr);
      });
    }
    var banner = document.querySelector("[data-dash-banner]");
    if (banner) {
      var list = banner.querySelector("ul");
      list.textContent = "";
      view.banner.forEach(function (b) {
        var li = el("li");
        li.appendChild(el("strong", "", b.label + ": " + b.value + "."));
        li.appendChild(document.createTextNode(" " + b.detail));
        list.appendChild(li);
      });
      banner.hidden = view.banner.length === 0;
    }
    drawGroups();
  }

  document.querySelectorAll("[data-dash-sort]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      sortKey = tab.getAttribute("data-dash-sort");
      document.querySelectorAll("[data-dash-sort]").forEach(function (t) {
        t.setAttribute("aria-pressed", t === tab ? "true" : "false");
      });
      drawGroups();
    });
  });

  // The server's figures, so sorting works before the first refresh.
  (function () {
    var holder = document.querySelector("[data-dash-view]");
    if (!holder) return;
    try {
      var data = JSON.parse(holder.getAttribute("data-dash-view"));
      buckets = data.buckets;
      groups = data.groups;
    } catch (e) { /* the server-drawn rows stay as they are */ }
  })();

  function refresh() {
    fetch("/dashboard/data", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        var type = response.headers.get("Content-Type") || "";
        if (!response.ok || type.indexOf("application/json") !== 0) throw new Error("not the figures");
        return response.json();
      })
      .then(function (view) {
        view.rings.forEach(drawRing);
        view.tiles.forEach(drawTile);
        var footer = document.querySelector("[data-dash-footer]");
        if (footer) footer.textContent = view.footer;
        if (view.fleet) drawFleet(view);
        lastGood = Date.now();
        say("Updated " + clock(new Date(lastGood)));
      })
      .catch(function () {
        say("Couldn't refresh. Showing figures from " + clock(new Date(lastGood)) + ".");
      });
  }

  function schedule() {
    clearInterval(timer);
    timer = setInterval(function () { if (!document.hidden) refresh(); }, PERIOD_MS);
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && Date.now() - lastGood >= PERIOD_MS) {
      refresh();
      schedule();
    }
  });

  // ⚠️ Timed on this browser's clock only: the page was drawn just now. The
  // server's time would put "a minute ago" in the future on a browser whose
  // clock runs behind it, and a returning tab would wait to refresh.
  say("Updated " + clock(new Date(lastGood)));
  schedule();
})();
