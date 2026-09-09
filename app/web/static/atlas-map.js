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
 * Drawing where a device is, and where it has been (W106).
 *
 * Loaded only by the two pages that need it, after Leaflet, both `defer` so the
 * order holds.
 *
 * The markers are `divIcon`s — CSS, not images — for both maps. That is partly
 * because the history map numbers its markers anyway, and partly so that nothing
 * here depends on Leaflet's image assets resolving, which is the usual way a
 * vendored copy breaks quietly after a move.
 */

(function () {
  "use strict";

  /** Tiles come from the server so the source stays a deployment decision. */
  function tileLayer(config) {
    return L.tileLayer(config.tileUrl, {
      attribution: config.tileAttribution || "",
      maxZoom: 19,
    });
  }

  /**
   * ⚠️ A map created in a hidden or just-inserted container measures itself as
   * zero and renders a grey box. Leaflet only recovers on `invalidateSize`, so
   * every map here gets one after layout has settled — this is the single most
   * common way an embedded Leaflet map "does not work".
   */
  function settle(map) {
    window.setTimeout(function () { map.invalidateSize(); }, 0);
  }

  function badge(number, selected) {
    return L.divIcon({
      className: "",
      html:
        '<span class="location-marker-badge' + (selected ? " selected" : "") + '">' +
        number + "</span>",
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });
  }

  // ------------------------------------------------------------------ latest

  function drawLatest(element) {
    var config = JSON.parse(element.getAttribute("data-map"));
    var map = L.map(element, {
      center: [config.latitude, config.longitude],
      zoom: 14,
      // Off, matching the reference portal: a page that swallows the scroll
      // wheel traps someone trying to scroll past the map.
      scrollWheelZoom: false,
    });
    tileLayer(config).addTo(map);

    // The reported accuracy, drawn rather than only stated. "±3 m" and "±3 km"
    // read almost the same in a table and are entirely different on a map.
    if (config.accuracyM) {
      L.circle([config.latitude, config.longitude], {
        radius: config.accuracyM,
        className: "location-accuracy",
      }).addTo(map);
    }

    L.marker([config.latitude, config.longitude], { icon: badge("●", false) })
      .addTo(map)
      .bindPopup(config.label);

    settle(map);
  }

  // ----------------------------------------------------------------- history

  function drawHistory(element) {
    var config = JSON.parse(element.getAttribute("data-map"));
    var points = config.points || [];

    var map = L.map(element, {
      center: points.length
        ? [points[0].latitude, points[0].longitude]
        : [config.fallbackLat, config.fallbackLon],
      zoom: 14,
      scrollWheelZoom: true,
    });
    tileLayer(config).addTo(map);

    if (!points.length) { settle(map); return; }

    var markers = {};
    points.forEach(function (point) {
      var marker = L.marker([point.latitude, point.longitude], {
        icon: badge(point.number, false),
      }).addTo(map);
      marker.bindPopup("#" + point.number + " — " + point.when);
      markers[point.number] = marker;
    });

    if (points.length === 1) {
      map.setView([points[0].latitude, points[0].longitude], 15);
    } else {
      map.fitBounds(
        L.latLngBounds(points.map(function (p) { return [p.latitude, p.longitude]; })).pad(0.2)
      );
    }
    settle(map);

    // --- selecting a row focuses its marker, and vice versa ---------------- //
    var selected = null;

    function select(number, fly) {
      if (selected !== null && markers[selected]) {
        markers[selected].setIcon(badge(selected, false));
        markers[selected].setZIndexOffset(0);
      }
      var marker = markers[number];
      if (!marker) return;
      selected = number;
      marker.setIcon(badge(number, true));
      marker.setZIndexOffset(1000);
      if (fly) map.flyTo(marker.getLatLng(), 16, { duration: 0.45 });

      document.querySelectorAll(".location-history-row").forEach(function (row) {
        row.classList.toggle("selected", row.getAttribute("data-point") === String(number));
      });
    }

    document.querySelectorAll(".location-history-row").forEach(function (row) {
      row.addEventListener("click", function () {
        select(Number(row.getAttribute("data-point")), true);
      });
    });
    Object.keys(markers).forEach(function (number) {
      markers[number].on("click", function () { select(Number(number), false); });
    });

    select(points[0].number, false);
  }

  // -------------------------------------------------------------------- boot

  document.querySelectorAll("[data-map-latest]").forEach(drawLatest);
  document.querySelectorAll("[data-map-history]").forEach(drawHistory);
})();
