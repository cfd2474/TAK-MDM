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

/*
 * Drawing geofences instead of typing them (W109).
 *
 * One map for every fence row. Per-row maps would put N Leaflet instances in a
 * form whose rows sit behind tabs, and a map measured while hidden renders as a
 * grey box — see `settle()` in atlas-map.js. A single map also answers the
 * question an operator actually has, which is whether two fences overlap.
 *
 * ⚠️ **The fields stay the source of truth.** The map writes into the row's
 * latitude/longitude inputs and reads back from them; it never holds a position
 * of its own. So typing coordinates, dragging the marker and finding an address
 * all converge on the same values, and the form submits exactly what is drawn.
 */
function atlasWireGeofencePicker() {
  var picker = document.querySelector("[data-geofence-picker]");
  if (!picker || typeof L === "undefined") return;

  var element = picker.querySelector("[data-geofence-map]");
  var status = picker.querySelector("[data-geofence-status]");
  var addressBox = picker.querySelector("[data-geofence-address]");
  var findButton = picker.querySelector("[data-geofence-find]");
  var tiles = JSON.parse(element.getAttribute("data-tiles") || "{}");

  var map = L.map(element, { center: [39.7392, -104.9903], zoom: 4 });
  L.tileLayer(tiles.tileUrl, { attribution: tiles.tileAttribution || "", maxZoom: 19 }).addTo(map);

  var layers = [];
  var selected = 0;

  function rows() {
    return Array.prototype.slice.call(
      document.querySelectorAll("[data-geofences] .geofence-row")
    );
  }

  function fieldIn(row, suffix) {
    return row.querySelector('[name$="__' + suffix + '"]');
  }

  /**
   * The rows, creating the first one if the operator has not added it yet.
   *
   * ⚠️ **Typing an address is the act of creating a fence.** The first version
   * refused with "Add a geofence row first", which is the form's internal order
   * of operations leaking out as an instruction — nobody opens this panel
   * intending to press Add and then type. Reported from the field within an hour
   * of shipping.
   *
   * The existing Add button is clicked rather than the template cloned here, so
   * there stays one code path that knows how a row is built.
   */
  function rowsEnsuringOne() {
    var all = rows();
    if (all.length) return all;
    var add = document.querySelector("[data-geofences] [data-add-row]");
    if (!add) return [];
    add.click();
    return rows();
  }

  function readRow(row) {
    var lat = parseFloat((fieldIn(row, "latitude") || {}).value);
    var lon = parseFloat((fieldIn(row, "longitude") || {}).value);
    var radius = parseFloat((fieldIn(row, "radius_m") || {}).value);
    if (isNaN(lat) || isNaN(lon)) return null;
    return {
      lat: lat,
      lon: lon,
      // A fence with no radius yet still has a centre worth showing; 200 is the
      // template's own default, so the circle matches what would be saved.
      radius: isNaN(radius) || radius <= 0 ? 200 : radius,
      name: ((fieldIn(row, "name") || {}).value || "").trim(),
    };
  }

  function writeRow(row, lat, lon) {
    var latField = fieldIn(row, "latitude");
    var lonField = fieldIn(row, "longitude");
    if (!latField || !lonField) return;
    // Five places is about a metre — more precision than a fence needs, and less
    // noise than the 14 digits a click would otherwise produce.
    latField.value = lat.toFixed(5);
    lonField.value = lon.toFixed(5);
    // Dispatched so anything else watching the form (the unsaved-change guard)
    // sees this as a real edit, which it is.
    latField.dispatchEvent(new Event("input", { bubbles: true }));
    lonField.dispatchEvent(new Event("input", { bubbles: true }));
    redraw();
  }

  function redraw() {
    layers.forEach(function (layer) { map.removeLayer(layer); });
    layers = [];

    rows().forEach(function (row, index) {
      var fence = readRow(row);
      row.classList.toggle("selected", index === selected);
      if (!fence) return;

      var isSelected = index === selected;
      var circle = L.circle([fence.lat, fence.lon], {
        radius: fence.radius,
        className: isSelected ? "geofence-shape selected" : "geofence-shape",
      }).addTo(map);
      circle.bindTooltip(
        (fence.name || "fence " + (index + 1)) + " — " + Math.round(fence.radius) + " m"
      );
      circle.on("click", function () { select(index); });
      layers.push(circle);

      var marker = L.marker([fence.lat, fence.lon], {
        draggable: isSelected,
        icon: L.divIcon({
          className: "",
          html: '<span class="location-marker-badge' + (isSelected ? " selected" : "") +
                '">' + (index + 1) + "</span>",
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        }),
      }).addTo(map);
      // ⚠️ Only the selected fence drags. Dragging one that is not selected would
      // silently move a fence the operator is not looking at, and the row that
      // changed is not the row their attention is on.
      marker.on("dragend", function (event) {
        var at = event.target.getLatLng();
        writeRow(row, at.lat, at.lng);
      });
      marker.on("click", function () { select(index); });
      layers.push(marker);
    });
  }

  function select(index) {
    selected = index;
    redraw();
    var fence = readRow(rows()[index]);
    if (fence) map.setView([fence.lat, fence.lon], Math.max(map.getZoom(), 13));
  }

  function clearResults() {
    var box = picker.querySelector("[data-geofence-results]");
    if (!box) return;
    box.innerHTML = "";
    box.hidden = true;
  }

  function showResults(results, row) {
    var box = picker.querySelector("[data-geofence-results]");
    if (!box) { place(row, results[0]); return; }
    box.innerHTML = "";
    results.forEach(function (result) {
      var option = document.createElement("button");
      option.type = "button";
      option.textContent = result.label;
      option.addEventListener("click", function () {
        place(row, result);
        clearResults();
      });
      box.appendChild(option);
    });
    box.hidden = false;
  }

  /** Put a found place on a row, naming the fence if it has no name yet. */
  function place(row, result) {
    writeRow(row, result.latitude, result.longitude);
    map.setView([result.latitude, result.longitude], 15);

    // A fence named for the place it is, which is what the field asks for. Only
    // when empty: an operator's own name is never overwritten by a lookup.
    var nameField = fieldIn(row, "name");
    if (nameField && !(nameField.value || "").trim()) {
      nameField.value = result.label.split(",")[0].trim().slice(0, 64);
      nameField.dispatchEvent(new Event("input", { bubbles: true }));
    }
    redraw();
    say("Placed at: " + result.label);
  }

  function say(message, bad) {
    if (!status) return;
    status.textContent = message || "";
    status.hidden = !message;
    status.classList.toggle("location-stale", !!bad);
  }

  // --- placing a fence by clicking --------------------------------------- //
  map.on("click", function (event) {
    var all = rowsEnsuringOne();
    if (!all.length) return;
    if (selected >= all.length) selected = all.length - 1;
    writeRow(all[selected], event.latlng.lat, event.latlng.lng);
    say("");
  });

  // --- typing keeps the map honest ---------------------------------------- //
  document.addEventListener("input", function (event) {
    var name = event.target && event.target.getAttribute
      ? event.target.getAttribute("name") : null;
    if (!name) return;
    if (/__(latitude|longitude|radius_m|name)$/.test(name)) redraw();
  });

  document.addEventListener("focusin", function (event) {
    var row = event.target.closest ? event.target.closest(".geofence-row") : null;
    if (!row) return;
    var index = rows().indexOf(row);
    if (index >= 0 && index !== selected) { selected = index; redraw(); }
  });

  // --- address lookup ------------------------------------------------------ //
  function find() {
    var query = (addressBox.value || "").trim();
    if (!query) { say("Type an address first.", true); return; }

    var all = rowsEnsuringOne();
    if (!all.length) {
      say("Could not add a geofence row to place this in.", true);
      return;
    }
    if (selected >= all.length) selected = all.length - 1;

    clearResults();
    say("Looking up the address…");
    findButton.disabled = true;

    fetch("/policies/geocode?q=" + encodeURIComponent(query), {
      headers: { Accept: "application/json" },
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.error) { say(data.error, true); return; }
        if (!data.results || !data.results.length) {
          // ⚠️ Distinct from the error above. "Not found" and "the service is
          // unreachable" send an operator to completely different places, and
          // collapsing them has someone retyping a perfectly good address.
          //
          // The hint is specific because the common failure is specific: this
          // geocoder wants a street *type*. "110 West Upper, Corona California"
          // finds nothing; "110 W Upper Dr, Corona CA" finds it.
          say(
            "No match. Include the street type (Dr, St, Ave) and the state — " +
              'e.g. "110 W Upper Dr, Corona CA". A town name on its own works too.',
            true
          );
          return;
        }

        if (data.results.length === 1) {
          place(all[selected], data.results[0]);
          return;
        }

        // ⚠️ More than one match is normal for a street name, and picking the
        // first silently is how a fence lands on the right-named road in the
        // wrong town — which nothing downstream would ever flag, because the
        // coordinates are perfectly valid.
        say("More than one place matches. Choose one:");
        showResults(data.results, all[selected]);
      })
      .catch(function () {
        say("The address lookup did not complete. Enter coordinates directly.", true);
      })
      .finally(function () { findButton.disabled = false; });
  }

  findButton.addEventListener("click", find);
  addressBox.addEventListener("keydown", function (event) {
    // Enter searches rather than submitting the whole policy form, which is what
    // a lone text input in a form does by default and would be a surprising way
    // to publish a half-finished policy.
    if (event.key === "Enter") { event.preventDefault(); find(); }
  });

  // Rows arrive and leave through the shared rowset controls.
  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!target || !target.hasAttribute) return;
    if (target.hasAttribute("data-add-row") || target.hasAttribute("data-remove-row")) {
      window.setTimeout(function () {
        var all = rows();
        if (selected >= all.length) selected = Math.max(0, all.length - 1);
        redraw();
      }, 0);
    }
  });

  // ⚠️ The map lives inside a tab panel that starts hidden, so it measures itself
  // as zero and paints grey until told otherwise. Re-measured whenever its panel
  // becomes visible, not only once at startup.
  var panel = element.closest("[data-page-panel]");
  if (panel && typeof MutationObserver !== "undefined") {
    new MutationObserver(function () {
      if (!panel.hasAttribute("hidden")) {
        map.invalidateSize();
        fitToFences();
      }
    }).observe(panel, { attributes: true, attributeFilter: ["hidden"] });
  }

  function fitToFences() {
    var points = rows().map(readRow).filter(Boolean);
    if (!points.length) return;
    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lon], 14);
      return;
    }
    map.fitBounds(
      L.latLngBounds(points.map(function (p) { return [p.lat, p.lon]; })).pad(0.3)
    );
  }

  redraw();
  fitToFences();
  window.setTimeout(function () { map.invalidateSize(); }, 0);
}

atlasWireGeofencePicker();
