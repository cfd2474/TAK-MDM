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
 * The dashboard map (W442): every enrolled device's last known location.
 *
 * Grouped here, not on the server, so a bucket switch or the group filter
 * redraws without a request. Devices within about 1 km fall in one dot,
 * sized by count and coloured by the oldest bucket among them. A device in
 * several groups is one point: with a group chosen, only that group's
 * devices are drawn.
 *
 * ⚠️ The view is fitted to the devices once, on the first draw. A refresh
 * never moves the map out from under someone who has panned or zoomed.
 * ⚠️ Device names go into the popup as text nodes, never as HTML.
 */

(function () {
  "use strict";

  var PERIOD_MS = 60 * 1000;
  //: About 1 km of latitude, in degrees.
  var CELL_DEGREES = 0.009;

  var element = document.querySelector("[data-dash-map]");
  if (!element || typeof L === "undefined") return;

  var map = null;
  var layer = null;
  var data = null;
  var fitted = false;
  var lastGood = Date.now();
  var groupSelect = document.querySelector("[data-dash-map-group]");
  var countEl = document.querySelector("[data-dash-map-count]");
  var bucketLabels = {};
  document.querySelectorAll("[data-dash-map-bucket]").forEach(function (box) {
    bucketLabels[box.getAttribute("data-dash-map-bucket")] = box.parentNode.textContent.trim();
  });

  function colour(key) {
    return getComputedStyle(document.documentElement).getPropertyValue("--b-" + key).trim() || "#888";
  }

  function shownBuckets() {
    var on = {};
    document.querySelectorAll("[data-dash-map-bucket]").forEach(function (box) {
      on[box.getAttribute("data-dash-map-bucket")] = box.checked;
    });
    return on;
  }

  /** The devices left after the switches and the filter, grouped by ~1 km cell. */
  function clusters() {
    var on = shownBuckets();
    var group = groupSelect && groupSelect.value !== "" ? Number(groupSelect.value) : null;
    var cells = {};
    data.devices.forEach(function (d) {
      var bucket = data.buckets[d[4]];
      if (!on[bucket]) return;
      if (group !== null && d[5].indexOf(group) === -1) return;
      var lat = d[2], lon = d[3];
      var lonCell = CELL_DEGREES / Math.max(Math.cos(lat * Math.PI / 180), 0.01);
      var key = Math.floor(lat / CELL_DEGREES) + ":" + Math.floor(lon / lonCell);
      var c = cells[key] || (cells[key] = { lat: 0, lon: 0, devices: [], oldest: 0 });
      c.lat += lat;
      c.lon += lon;
      c.devices.push(d);
      c.oldest = Math.max(c.oldest, d[4]);
    });
    return Object.keys(cells).map(function (k) {
      var c = cells[k];
      c.lat /= c.devices.length;
      c.lon /= c.devices.length;
      return c;
    });
  }

  function popup(c) {
    var box = document.createElement("div");
    box.className = "dash-map-popup";
    var head = document.createElement("strong");
    head.textContent = c.devices.length + (c.devices.length === 1 ? " device" : " devices");
    box.appendChild(head);
    var list = document.createElement("ul");
    c.devices.slice().sort(function (a, b) { return b[4] - a[4] || a[1].localeCompare(b[1]); })
      .slice(0, 15).forEach(function (d) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = "/devices/" + encodeURIComponent(d[0]);
        a.textContent = d[1];
        li.appendChild(a);
        li.appendChild(document.createTextNode(" · " + (bucketLabels[data.buckets[d[4]]] || "")));
        list.appendChild(li);
      });
    box.appendChild(list);
    if (c.devices.length > 15) {
      var more = document.createElement("div");
      more.textContent = "and " + (c.devices.length - 15) + " more";
      box.appendChild(more);
    }
    return box;
  }

  function draw() {
    if (!data) return;
    var found = clusters();
    layer.clearLayers();
    var shown = 0;
    found.forEach(function (c) {
      shown += c.devices.length;
      var key = data.buckets[c.oldest];
      L.circleMarker([c.lat, c.lon], {
        radius: 5 + 3 * Math.sqrt(c.devices.length),
        color: colour(key),
        fillColor: colour(key),
        fillOpacity: 0.55,
        weight: 2,
      }).bindPopup(popup(c)).addTo(layer);
    });
    if (countEl) countEl.textContent = shown + (shown === 1 ? " location shown" : " locations shown");
    if (!fitted && found.length) {
      map.fitBounds(L.latLngBounds(found.map(function (c) { return [c.lat, c.lon]; })).pad(0.2), { maxZoom: 13 });
      fitted = true;
    }
  }

  function fillGroups() {
    if (!groupSelect) return;
    var chosen = groupSelect.value;
    var chosenName = chosen !== "" ? groupSelect.options[groupSelect.selectedIndex].text : null;
    while (groupSelect.options.length > 1) groupSelect.remove(1);
    var names = data.groups.map(function (name, i) { return { name: name, i: i }; })
      .sort(function (a, b) { return a.name.localeCompare(b.name, undefined, { sensitivity: "base" }); });
    names.forEach(function (g) {
      var option = new Option(g.name, String(g.i));
      groupSelect.add(option);
      // Indexes can change between refreshes; keep the choice by name.
      if (g.name === chosenName) option.selected = true;
    });
  }

  function start(view) {
    element.textContent = "";
    map = L.map(element, { scrollWheelZoom: false, worldCopyJump: true }).setView([20, 0], 2);
    L.tileLayer(view.tiles.tileUrl, { attribution: view.tiles.tileAttribution || "", maxZoom: 19 }).addTo(map);
    layer = L.layerGroup().addTo(map);
    window.setTimeout(function () { map.invalidateSize(); }, 0);
  }

  function load() {
    fetch("/dashboard/map", { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        var type = response.headers.get("Content-Type") || "";
        if (!response.ok || type.indexOf("application/json") !== 0) throw new Error("not the map");
        return response.json();
      })
      .then(function (view) {
        if (!map) start(view);
        data = view;
        lastGood = Date.now();
        fillGroups();
        draw();
      })
      .catch(function () {
        if (!map) element.querySelector("p").textContent = "The map could not be loaded.";
      });
  }

  document.querySelectorAll("[data-dash-map-bucket]").forEach(function (box) {
    box.addEventListener("change", draw);
  });
  if (groupSelect) groupSelect.addEventListener("change", draw);

  setInterval(function () { if (!document.hidden) load(); }, PERIOD_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && Date.now() - lastGood >= PERIOD_MS) load();
  });
  load();
})();
