// Records one screen clip per voiceover section by driving the app in headless Edge (Chrome DevTools
// Protocol screencast), so the video needs no manual recording. A drawn cursor shows where clicks go.
//
//   node docs/video/record_screen.mjs [section ...]      e.g. node docs/video/record_screen.mjs 3 4
//
// Needs: the app on http://localhost:8765, Edge started with --remote-debugging-port=9333, ffmpeg on
// PATH, and docs/video/audio/NN.mp3 (each clip is recorded to that section's voice length).
import { mkdirSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = "http://localhost:8765/";
const SLIDES = pathToFileURL(join(HERE, "slides.html")).href;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const seconds = file => parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]).toString());

const page = (await (await fetch("http://127.0.0.1:9333/json")).json()).find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0, frames = null;
const waiting = new Map();
ws.onmessage = async m => {
  const d = JSON.parse(m.data);
  if (d.method === "Page.screencastFrame") {
    if (frames) frames.push({t: d.params.metadata.timestamp, data: d.params.data});
    send("Page.screencastFrameAck", {sessionId: d.params.sessionId});
  }
  if (waiting.has(d.id)) { waiting.get(d.id)(d.result); waiting.delete(d.id); }
};
const send = (method, params = {}) => new Promise(r => { waiting.set(++id, r); ws.send(JSON.stringify({id, method, params})); });
const js = async expr => (await send("Runtime.evaluate", {expression: expr, awaitPromise: true, returnByValue: true}))?.result?.value;

await send("Page.enable");
// 1600x900 CSS pixels drawn at 1.2x = 1920x1080 video, so the page reads like a 120% zoom.
await send("Emulation.setDeviceMetricsOverride", {width: 1600, height: 900, deviceScaleFactor: 1.2, mobile: false});

const CURSOR = `(() => { if (document.getElementById("__cur")) return;
  const c = document.createElement("div"); c.id = "__cur";
  c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M3 2l7 19 2.5-7.5L20 11z" fill="#0B0B0C" stroke="#fff" stroke-width="1.5"/></svg>';
  Object.assign(c.style, {position: "fixed", left: "800px", top: "520px", zIndex: 99999, pointerEvents: "none",
    transition: "left .7s cubic-bezier(.4,0,.2,1), top .7s cubic-bezier(.4,0,.2,1)"});
  document.body.appendChild(c);
  window.__move = (x, y) => { c.style.left = x + "px"; c.style.top = y + "px"; };
  window.__ring = (x, y) => { const r = document.createElement("div");
    Object.assign(r.style, {position: "fixed", left: x - 18 + "px", top: y - 18 + "px", width: "36px", height: "36px",
      borderRadius: "50%", border: "3px solid #F8C020", zIndex: 99998, pointerEvents: "none", transition: "all .45s ease-out"});
    document.body.appendChild(r); requestAnimationFrame(() => { r.style.transform = "scale(1.8)"; r.style.opacity = "0"; });
    setTimeout(() => r.remove(), 600); };
})()`;

async function go(url) {
  // a fresh query string forces a full load: going from #ask to #brief on the same page is only a
  // hash change, and the app picks its tab at load time
  const [base, hash] = url.split("#");
  await send("Page.navigate", {url: `${base}?r=${Date.now()}${hash ? "#" + hash : ""}`});
  await sleep(1800);
  if (!url.startsWith(SLIDES)) await js(CURSOR);  // slides have nothing to click
}
async function center(selector) {
  return js(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e) return null;
    e.scrollIntoView({block: "nearest"}); const r = e.getBoundingClientRect(); return [r.left + Math.min(r.width / 2, 120), r.top + r.height / 2]; })()`);
}
async function move(selector) {
  const p = await center(selector);
  if (!p) throw new Error("not found: " + selector);
  await js(`__move(${p[0]}, ${p[1]})`);
  await sleep(800);
  return p;
}
async function click(selector) {
  const [x, y] = await move(selector);
  await js(`__ring(${x}, ${y})`);
  for (const type of ["mousePressed", "mouseReleased"])
    await send("Input.dispatchMouseEvent", {type, x, y, button: "left", clickCount: 1});
  await sleep(300);
}
async function type(text, perChar = 28) {
  for (const ch of text) { await send("Input.insertText", {text: ch}); await sleep(perChar); }
}
async function enter() {
  for (const type of ["keyDown", "keyUp"])
    await send("Input.dispatchKeyEvent", {type, key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: type === "keyDown" ? "\r" : undefined});
}
async function waitFor(expr, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await js(expr)) return; await sleep(250); }
  throw new Error("timed out waiting for " + expr);
}
async function glide(dy, ms) {  // smooth scroll, so the viewer can follow
  await js(`new Promise(done => { const from = scrollY, t0 = performance.now();
    const step = t => { const k = Math.min((t - t0) / ${ms}, 1); scrollTo(0, from + ${dy} * (1 - Math.cos(k * Math.PI)) / 2);
      k < 1 ? requestAnimationFrame(step) : done(); }; requestAnimationFrame(step); })`);
}
async function repaint() {  // headless screencasts can leave a torn frame after scrolling; force a clean one
  await js(`scrollBy(0, 1)`); await sleep(120); await js(`scrollBy(0, -1)`); await sleep(250);
}
async function ask(question) {
  await click("#q");
  await js(`document.querySelector("#q").value = ""`);
  await type(question, 22);
  await sleep(300);
  await enter();
  await waitFor(`!!document.querySelector("#result .card") && !document.querySelector("#result .stages")`);
  await js(`document.querySelector("#result").scrollIntoView({behavior: "smooth", block: "start"})`);
}

// One function per section; each fills its voice clip's length (the recorder holds the last frame).
const SECTIONS = {
  1: async () => { await sleep(2500); await move("#q"); await sleep(4000); await move(".chip"); },
  2: async () => { },
  3: async () => { await sleep(1500);
    await click("#tlPickIn"); await type("TS3009", 120); await sleep(600); await enter(); await sleep(2500);
    await click('#tlFilters [data-f="decision"]'); await sleep(2500);
    await glide(420, 5000); await repaint(); await sleep(3000);
    await js(`[...document.querySelectorAll(".ev")].find(e => /titanium/i.test(e.textContent) && e.classList.contains("current"))?.scrollIntoView({behavior: "smooth", block: "center"})`);
    await sleep(1500);
    await move(".ev.current .t.s-current");
  },
  4: async () => { await sleep(800);
    await ask("What energy source did Team ES2015 end up with, and who proposed it?");
    await sleep(6000);
    await click("#result [data-q]"); await waitFor(`!!document.querySelector("#drBody .turn")`); await sleep(3500);
    await click("#drWhole"); await sleep(2500);
    await move("#drRaw");
  },
  5: async () => { await sleep(500);
    await ask("How much were the designers in Team IS1004 paid for the project?"); await sleep(2500);
    await js(`scrollTo({top: 0, behavior: "smooth"})`); await sleep(500);
    await ask("Why did Team TS3008 decide to include an LCD display in the final remote?"); await sleep(3000);
    await js(`scrollTo({top: 0, behavior: "smooth"})`); await sleep(500);
    await ask("What is the backup energy source for the remote?"); await sleep(1500);
    await glide(300, 2500); await repaint();
  },
  6: async () => { await sleep(1500);
    await click("#brBtn");
    await waitFor(`!!document.querySelector("#brOut .brief")`);
    await sleep(1200); await glide(500, 4500); await repaint(); await sleep(1500); await glide(600, 5000); await repaint();
  },
  7: async () => { await sleep(18500);
    await go(APP + "#timeline"); await sleep(1200);
    await click("#tlPickIn"); await type("IS1000", 120); await sleep(500); await enter(); await sleep(2000);
    await click('#tlFilters [data-f="number"]'); await sleep(1500);
    await js(`document.querySelector(".t.flag")?.scrollIntoView({behavior: "smooth", block: "center"})`); await sleep(1500);
    await move(".t.flag");
  },
  8: async () => { },
  9: async () => { },
};

const START = {1: APP + "#ask", 2: SLIDES + "#diagram", 3: APP + "#timeline", 4: APP + "#ask", 5: APP + "#ask", 6: APP + "#brief", 7: SLIDES + "#line", 8: SLIDES + "#proof", 9: SLIDES + "#next"};

async function record(n) {
  const voice = join(HERE, "audio", `${String(n).padStart(2, "0")}.mp3`);
  const length = seconds(voice);
  await go(START[n]);  // load the page first, so the clip opens on it, not on a blank tab
  frames = [];
  await send("Page.startScreencast", {format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1});
  if (START[n].startsWith(SLIDES))  // replay the slide's fade-ins from zero, in step with the voice
    await js(`document.body.classList.add("go")`);
  const t0 = Date.now();
  await SECTIONS[n]();
  const left = length * 1000 - (Date.now() - t0);
  if (left > 0) await sleep(left);
  else console.log(`  section ${n}: actions ran ${(-left / 1000).toFixed(1)} s past the voice; the clip is cut to the voice`);
  await send("Page.stopScreencast");
  const shot = frames.filter(f => f.t > 0);
  frames = null;
  const tmp = join(HERE, "screen", `.frames-${n}`);
  rmSync(tmp, {recursive: true, force: true}); mkdirSync(tmp, {recursive: true});
  const start = shot[0].t, lines = [];
  shot.forEach((f, i) => {
    const name = `${String(i).padStart(5, "0")}.jpg`;
    writeFileSync(join(tmp, name), Buffer.from(f.data, "base64"));
    const next = i + 1 < shot.length ? shot[i + 1].t : start + length;
    lines.push(`file '${name}'`, `duration ${Math.max(next - f.t, 0.001).toFixed(4)}`);
  });
  lines.push(`file '${String(shot.length - 1).padStart(5, "0")}.jpg'`);
  writeFileSync(join(tmp, "frames.txt"), lines.join("\n"));
  const out = join(HERE, "screen", `${String(n).padStart(2, "0")}.mp4`);
  execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", join(tmp, "frames.txt"),
    "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "18", "-t", length.toFixed(3), out]);
  rmSync(tmp, {recursive: true, force: true});
  console.log(`section ${n}: ${shot.length} frames, ${length.toFixed(1)} s -> ${out}`);
}

mkdirSync(join(HERE, "screen"), {recursive: true});
const wanted = process.argv.slice(2).map(Number);
for (const n of (wanted.length ? wanted : Object.keys(SECTIONS).map(Number))) {
  try { await record(n); } catch (error) { console.log(`section ${n} FAILED: ${error.message}`); frames = null; }
}
ws.close();
