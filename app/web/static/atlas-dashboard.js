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
