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
 * The dashboard's trend charts (W442): one reading a day, drawn as SVG.
 *
 * ⚠️ A day with no reading is a gap in the line, never a line drawn across
 * it: a server that was down for a week did not have a flat week. And a
 * figure that could not be read (disk or memory) is a gap too, not a zero.
 * ⚠️ Fetched on load and every 15 minutes: the readings change once a day.
 */

(function () {
  "use strict";

  var root = document.querySelector("[data-dash-trends]");
  if (!root) return;
  var note = document.querySelector("[data-dash-trends-note]");
  var SVG = "http://www.w3.org/2000/svg";
  var W = 600, H = 200, PAD_L = 40, PAD_R = 10, PAD_T = 10, PAD_B = 22;
  var DAY_MS = 86400000;
  var range = 30;
  var data = null;

  var CHARTS = [
    { title: "Checked in", series: [
      { key: "checked_in_1h", label: "Within 1 hour", colour: "--b-week" },
      { key: "checked_in_24h", label: "Within 24 hours", colour: "--b-month" }] },
    { title: "Stale over 30 days", area: true, series: [
      { key: "stale_30d", label: "Stale >30d", colour: "--b-week" }] },
    { title: "Disk and memory", percent: true, series: [
      { key: "disk_percent", label: "Disk %", colour: "--b-week" },
      { key: "memory_percent", label: "Memory %", colour: "--b-month" }] },
    { title: "Low battery devices", area: true, series: [
      { key: "low_battery", label: "Low battery", colour: "--b-week" }] },
  ];

  function svg(tag, attrs, text) {
    var node = document.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function colour(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
  }

  function dayNumber(iso) { return Math.round(Date.parse(iso + "T00:00:00Z") / DAY_MS); }

  /** A round top for the axis: 1, 2 or 5 times a power of ten. */
  function niceMax(value) {
    if (value <= 0) return 1;
    var power = Math.pow(10, Math.floor(Math.log10(value)));
    var steps = [1, 2, 5, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * power >= value) return steps[i] * power;
    return 10 * power;
  }

  /** The readings in range: the last `range` days up to the newest reading. */
  function visible() {
    var days = data.days.map(dayNumber);
    if (!days.length) return { from: 0, to: 0, index: [] };
    var to = days[days.length - 1];
    var from = Math.max(days[0], to - range + 1);
    var index = [];
    days.forEach(function (d, i) { if (d >= from) index.push(i); });
    return { from: from, to: to, index: index, days: days };
  }

  function chart(config, view) {
    var card = document.createElement("div");
    card.className = "dash-chart";
    var title = document.createElement("div");
    title.className = "dash-chart-title";
    title.textContent = config.title;
    card.appendChild(title);
    var legend = document.createElement("ul");
    legend.className = "dash-legend";
    config.series.forEach(function (s) {
      var li = document.createElement("li");
      var swatch = document.createElement("span");
      swatch.className = "dash-swatch";
      swatch.style.background = colour(s.colour);
      li.appendChild(swatch);
      li.appendChild(document.createTextNode(s.label));
      legend.appendChild(li);
    });
    card.appendChild(legend);

    var box = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": config.title });
    card.appendChild(box);
    if (!view.index.length) {
      box.appendChild(svg("text", { x: W / 2, y: H / 2, "text-anchor": "middle", "class": "empty" }, "No readings yet"));
      return card;
    }

    var top = 0;
    config.series.forEach(function (s) {
      view.index.forEach(function (i) { var v = data[s.key][i]; if (v !== null && v > top) top = v; });
    });
    top = config.percent ? 100 : niceMax(top);
    var span = Math.max(view.to - view.from, 1);
    var x = function (day) { return PAD_L + (day - view.from) * (W - PAD_L - PAD_R) / span; };
    if (view.to === view.from) x = function () { return (PAD_L + W - PAD_R) / 2; };
    var y = function (v) { return PAD_T + (1 - v / top) * (H - PAD_T - PAD_B); };

    // The midline only where it is a whole count: a top of 1 would label
    // 0.5 as "1" and read 1, 1, 0. Percent charts always have 50 %.
    var lines = top % 2 === 0 || config.percent ? [0, top / 2, top] : [0, top];
    lines.forEach(function (v) {
      box.appendChild(svg("line", { x1: PAD_L, x2: W - PAD_R, y1: y(v), y2: y(v), "class": "grid" }));
      var label = config.percent ? Math.round(v) + "%" : Math.round(v).toLocaleString();
      box.appendChild(svg("text", { x: PAD_L - 6, y: y(v) + 3, "text-anchor": "end", "class": "axis" }, label));
    });
    var first = data.days[view.index[0]], last = data.days[view.index[view.index.length - 1]];
    box.appendChild(svg("text", { x: PAD_L, y: H - 6, "class": "axis" }, first));
    if (last !== first) box.appendChild(svg("text", { x: W - PAD_R, y: H - 6, "text-anchor": "end", "class": "axis" }, last));

    config.series.forEach(function (s) {
      var stroke = colour(s.colour);
      // Runs of consecutive days with a value; a missing day or value ends a run.
      var runs = [], run = [];
      view.index.forEach(function (i, n) {
        var v = data[s.key][i];
        var gap = n > 0 && view.days[i] - view.days[view.index[n - 1]] > 1;
        if (gap || v === null) { if (run.length) runs.push(run); run = []; }
        if (v !== null) run.push([x(view.days[i]), y(v), i, v]);
      });
      if (run.length) runs.push(run);
      runs.forEach(function (points) {
        var line = points.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
        if (config.area && points.length > 1) {
          var base = y(0).toFixed(1);
          box.appendChild(svg("polygon", { points: points[0][0].toFixed(1) + "," + base + " " + line + " " +
            points[points.length - 1][0].toFixed(1) + "," + base, fill: stroke, "class": "area" }));
        }
        if (points.length > 1) box.appendChild(svg("polyline", { points: line, stroke: stroke, "class": "line" }));
        points.forEach(function (p) {
          var dot = svg("circle", { cx: p[0], cy: p[1], r: points.length > 1 ? 7 : 4, "class": points.length > 1 ? "hit" : "",
            fill: points.length > 1 ? "" : stroke, style: "color:" + stroke });
          dot.appendChild(svg("title", {}, data.days[p[2]] + " · " + s.label + ": " +
            (config.percent ? p[3] + "%" : Number(p[3]).toLocaleString())));
          box.appendChild(dot);
        });
      });
    });
    return card;
  }

  function draw() {
    if (!data) return;
    var view = visible();
    root.textContent = "";
    CHARTS.forEach(function (c) { root.appendChild(chart(c, view)); });
    if (note) {
      var n = data.days.length;
      note.textContent = n === 0
        ? "No readings yet. One is taken each day, the first as soon as ATLAS starts."
        : "One reading a day (" + n + " so far, kept for a year).";
    }
  }

  function load() {
    fetch("/dashboard/trends", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        var type = response.headers.get("Content-Type") || "";
        if (!response.ok || type.indexOf("application/json") !== 0) throw new Error("not the trends");
        return response.json();
      })
      .then(function (view) { data = view; draw(); })
      .catch(function () { if (!data) root.querySelector("p").textContent = "The trends could not be loaded."; });
  }

  document.querySelectorAll("[data-dash-range]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      range = Number(tab.getAttribute("data-dash-range"));
      document.querySelectorAll("[data-dash-range]").forEach(function (t) {
        t.setAttribute("aria-pressed", t === tab ? "true" : "false");
      });
      draw();
    });
  });

  setInterval(function () { if (!document.hidden) load(); }, 15 * 60 * 1000);
  load();
})();
