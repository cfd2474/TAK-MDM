/* The rail's ticks must answer "what have I filled in?" and nothing else.
 *
 * A new policy showed "Kiosk › Single app" as filled before an app was chosen,
 * because the panel holds a presentational radio (`__kiosk_mode`) that is checked
 * from the moment the page renders, and the content test counted any checked
 * control. */
const fs = require("fs");
const { JSDOM } = require("jsdom");

const ROOT = "D:/Projects/cursor/TAK-MDM";
const PAGE = process.argv[2];
if (!PAGE) { console.log("usage: node check_rail_checks.js <rendered-creator.html>"); process.exit(2); }

// A real URL, because the rail calls history.replaceState to record the page and
// jsdom refuses that on about:blank.
const dom = new JSDOM(fs.readFileSync(PAGE, "utf8"), {
  url: "https://console.test/policies/new",
  runScripts: "outside-only",
});
const { window } = dom;
global.window = window; global.document = window.document;
window.eval(fs.readFileSync(ROOT + "/app/web/static/atlas.js", "utf8"));

const doc = window.document;
let fails = 0;
function check(name, ok, detail) {
  console.log(`  ${name}: ${ok ? "PASS" : "FAIL" + (detail ? " -> " + detail : "")}`);
  if (!ok) fails++;
}

/** Sub-pages currently showing a tick. */
function ticked() {
  return [...doc.querySelectorAll(".rail-sub [data-page]")]
    .filter((a) => { const c = a.querySelector(".rail-check"); return c && !c.hidden; })
    .map((a) => a.getAttribute("data-page"));
}

console.log("a policy nobody has touched:");
const initial = ticked();
check("nothing is marked as filled", initial.length === 0, JSON.stringify(initial));
check(
  "Single app in particular is not",
  !initial.some((k) => k.startsWith("kiosk:") && k.includes("single")),
  JSON.stringify(initial),
);

// The presentational radio really is present and checked - otherwise this test
// would pass for the wrong reason.
const mode = doc.querySelector('input[name="__kiosk_mode"]:checked');
check("the presentational radio is checked (so the test means something)", !!mode);

console.log("\nafter choosing a kiosk app:");
const select = doc.querySelector('[data-kiosk-app] select[name="kiosk_package"]');
if (!select) {
  check("the kiosk app select exists", false);
} else {
  const option = [...select.options].find((o) => o.value);
  select.value = option ? option.value : "";
  select.dispatchEvent(new window.Event("change", { bubbles: true }));
  const now = ticked();
  check("Single app is marked filled", now.some((k) => k.includes("single")), JSON.stringify(now));
  check("and only that page is", now.length === 1, JSON.stringify(now));
}

console.log(fails === 0 ? "\nall checks passed" : `\n${fails} FAILED`);
process.exit(fails === 0 ? 0 : 1);
