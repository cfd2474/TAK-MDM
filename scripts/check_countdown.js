/* Drive the real countdown code in a real DOM, with a clock we control.
 *
 * The markup is read out of the template rather than retyped, so this cannot
 * drift into testing a page that does not exist. */
const fs = require("fs");
const { JSDOM } = require("jsdom");

const ROOT = "D:/Projects/cursor/TAK-MDM";
const SCRIPT = fs.readFileSync(ROOT + "/app/web/static/atlas.js", "utf8");
const template = fs.readFileSync(ROOT + "/app/web/templates/token_qr.html", "utf8");

const match = template.match(/<span class="pill warn" data-countdown=[\s\S]*?<\/span>\s*\n/);
if (!match) { console.log("FAIL: the countdown pill is not in the template"); process.exit(1); }
const PILL = match[0]
  .replace("{{ qr_expires_in }}", "900")
  .replace(/title="[^"]*"/, 'title="expires 14:32:10 UTC"')
  .replace(/\{\{[^}]*\}\}/g, "15:00");

let fails = 0;
function check(name, ok, detail) {
  console.log(`  ${name}: ${ok ? "PASS" : "FAIL" + (detail ? " -> " + detail : "")}`);
  if (!ok) fails++;
}

/** A fresh page with a clock and timers we drive by hand. */
function page(startMillis) {
  const dom = new JSDOM(`<body><p>${PILL}</p></body>`, { runScripts: "outside-only" });
  const { window } = dom;
  global.window = window;
  global.document = window.document;

  let now = startMillis;
  const ticks = [];
  window.Date.now = () => now;
  window.setInterval = (fn) => { ticks.push(fn); return ticks.length; };
  window.clearInterval = () => { ticks.length = 0; };

  window.eval(SCRIPT);

  return {
    text: () => window.document.querySelector("[data-countdown]")
      .textContent.replace(/\s+/g, " ").trim(),
    classes: () => window.document.querySelector("[data-countdown]").className,
    title: () => window.document.querySelector("[data-countdown]").getAttribute("title"),
    advance: (seconds) => {
      for (let i = 0; i < seconds; i++) {
        now += 1000;
        ticks.slice().forEach((fn) => fn());
      }
    },
  };
}

console.log("a fresh 15-minute token:");
let p = page(1_000_000);
check("shows a duration, not a time of day", /expires in 15:00/.test(p.text()), p.text());
check("keeps the absolute time in the title", /14:32:10/.test(p.title()));

p.advance(1);
check("counts down each second", /14:59/.test(p.text()), p.text());

p.advance(59);
check("a minute in, reads 14:00", /14:00/.test(p.text()), p.text());

console.log("\nas it runs out:");
p = page(1_000_000);
p.advance(840);                                   // 14:00 gone, 60s left
check("turns urgent under a minute", /bad/.test(p.classes()), p.classes());
check("no longer merely a warning", !/warn/.test(p.classes()), p.classes());

p.advance(60);
check("says it expired rather than 0:00",
  /expired/.test(p.text()) && !/0:00/.test(p.text()), p.text());
p.advance(30);
check("stays expired and stops ticking", /expired/.test(p.text()), p.text());

console.log("\nwith the browser clock an hour ahead of the server:");
p = page(1_000_000 + 3600 * 1000);
check("still shows the full 15 minutes", /expires in 15:00/.test(p.text()), p.text());
p.advance(120);
check("and counts down normally from there", /13:00/.test(p.text()), p.text());

console.log(fails === 0 ? "\nall checks passed" : `\n${fails} FAILED`);
process.exit(fails === 0 ? 0 : 1);
