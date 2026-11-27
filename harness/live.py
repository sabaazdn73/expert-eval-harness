"""Live view of a --team run: watch the agents talk while they work.

    python3 -m harness.run run --team --live ...      opens the page in the browser when the run starts
    python3 -m harness.run watch runs/<name>          opens it for a run going on in another terminal, or a past run

The run writes runs/<name>/channels/live.json after every event (an agent starts or stops working, a post, a grade).
A small web server on this computer only (127.0.0.1) serves the run's folder, and channels/live.html reads live.json
every second and a half: each trial is a channel in the sidebar, posts appear as they are written, and the agents at
work show as "working" with how long they have been at it.
"""
import json
import os
import threading
import time
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Board:
    """The state of every team trial of a run, written to channels/live.json on each change."""

    def __init__(self, run_dir, run_id):
        self.dir = os.path.join(run_dir, "channels")
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "live.json")
        self.lock = threading.Lock()
        self.data = {"run": run_id, "started": time.time(), "finished": None, "trials": {}, "order": []}
        with open(os.path.join(self.dir, "live.html"), "w") as f:
            f.write(PAGE)
        self._write()

    def add(self, key, task, model, trial):
        with self.lock:
            self.data["order"].append(key)
            self.data["trials"][key] = {"task": task, "model": model, "trial": trial + 1, "state": "waiting",
                                        "verdict": "", "agents": [], "working": {}, "posts": [],
                                        "started": None, "ended": None}
            self._write()

    def event(self, key, e):
        with self.lock:
            t = self.data["trials"].get(key)
            if t is None:
                return
            if e["type"] == "working":
                t["working"][e["agent"]] = {"kind": e.get("kind"), "since": time.time()}
            elif e["type"] == "idle":
                t["working"].pop(e["agent"], None)
            elif e["type"] == "plan":
                t["agents"] = [{"id": a["id"], "member": a.get("member", "")} for a in e["agents"]]
            elif e["type"] == "post":
                t["posts"].append(e["msg"])
            self._write()

    def state(self, key, state, verdict=None):
        with self.lock:
            t = self.data["trials"].get(key)
            if t is None:
                return
            t["state"] = state
            if state == "working" and not t["started"]:
                t["started"] = time.time()
            if state in ("done", "error"):
                t["ended"] = time.time()
                t["working"] = {}
            if verdict is not None:
                t["verdict"] = verdict
            self._write()

    def finish(self):
        with self.lock:
            self.data["finished"] = time.time()
            self._write()

    def _write(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)  # the page never reads a half-written file


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(run_dir, port=8765, open_browser=True):
    """Serve the run's folder on this computer only. Returns (server, url); the server runs in a background thread."""
    handler = partial(_Quiet, directory=os.path.abspath(run_dir))
    srv = None
    for p in (port, 0):  # 0: any free port
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), handler)
            break
        except OSError:
            continue
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/channels/live.html"
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    return srv, url


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Team review, live</title>
<style>
:root { --bg:#f7f6f3; --panel:#ffffff; --ink:#1f2328; --muted:#5d6470; --line:#e2dfd8; --side:#22313f; --sideink:#e8edf2;
  --sidemuted:#9fb0bf; --sel:#33475a; --ask:#fff4d6; --askink:#6b4e00; --at:#1d5fa8; --final:#eef6f1;
  --pass:#2e7d4f; --fail:#b3412f; --work:#c98a12; --grade:#3b6fb0; --wait:#7d8794; --banner:#eef3f8; }
@media (prefers-color-scheme: dark) { :root { --bg:#15181c; --panel:#1d2126; --ink:#e6e8eb; --muted:#9aa3ad; --line:#2c3239;
  --side:#0f1418; --sideink:#cfd8e0; --sidemuted:#7d8b97; --sel:#1f2b36; --ask:#3a3020; --askink:#f1d38a; --at:#7fb0ea;
  --final:#1d2a23; --pass:#5cbf86; --fail:#e0705c; --work:#e0a93a; --grade:#7fa6dc; --wait:#8a939d; --banner:#1c2530; } }
* { box-sizing:border-box }
html, body { height:100% }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system, "Segoe UI", Inter, sans-serif; }
.app { display:flex; height:100vh }
aside { width:270px; flex:none; background:var(--side); color:var(--sideink); display:flex; flex-direction:column; min-height:0 }
.runhead { padding:16px 16px 10px }
.runhead h1 { font-size:15px; margin:0 0 2px }
.runhead p { margin:0; font-size:12px; color:var(--sidemuted) }
nav { overflow-y:auto; padding:4px 8px 16px; flex:1 }
nav button { all:unset; display:flex; gap:9px; align-items:flex-start; width:100%; box-sizing:border-box; padding:7px 8px;
  border-radius:6px; cursor:pointer; }
nav button:hover { background:var(--sel) } nav button.sel { background:var(--sel) }
nav button:focus-visible { outline:2px solid var(--at) }
.st { width:9px; height:9px; border-radius:50%; margin-top:5px; flex:none; background:var(--wait) }
.st.working { background:var(--work); animation:pulse 1.2s ease-in-out infinite } .st.grading { background:var(--grade) }
.st.pass { background:var(--pass) } .st.fail, .st.error { background:var(--fail) }
@keyframes pulse { 50% { opacity:.35 } }
.ch { min-width:0; flex:1 } .ch b { display:block; font-weight:600; font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
.ch span { display:block; font-size:12px; color:var(--sidemuted) }
.badge { background:var(--at); color:#fff; border-radius:9px; font-size:11px; padding:0 6px; margin-top:2px; font-weight:700 }
main { flex:1; min-width:0; display:flex; flex-direction:column; min-height:0 }
.top { padding:14px 22px 10px; border-bottom:1px solid var(--line); background:var(--panel) }
.top h2 { margin:0; font-size:17px } .top .sub { color:var(--muted); font-size:12px; margin-top:2px }
.members { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px }
.chip { display:flex; align-items:center; gap:6px; font-size:12px; border:1px solid var(--line); border-radius:12px; padding:1px 9px 1px 4px }
.chip i { width:16px; height:16px; border-radius:4px; display:inline-block }
.chip.busy { border-color:var(--work) }
.banner { margin:12px 22px 0; padding:8px 12px; border-radius:8px; background:var(--banner); font-size:13px }
.banner[hidden] { display:none }
.banner a { color:var(--at) }
#feed { flex:1; overflow-y:auto; padding:14px 22px 8px }
.msg { display:flex; gap:12px; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin-bottom:10px }
.msg.final { background:var(--final) }
.msg.new { animation:arrive .5s ease-out }
@keyframes arrive { from { opacity:0; transform:translateY(6px) } }
.av { width:36px; height:36px; flex:none; border-radius:8px; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:12px }
.body { min-width:0; flex:1 } .msg header { display:flex; flex-wrap:wrap; gap:8px; align-items:baseline }
.meta { color:var(--muted); font-size:12px }
pre { white-space:pre-wrap; word-wrap:break-word; margin:6px 0 0; font:13px/1.5 ui-monospace, Menlo, Consolas, monospace }
.ask { background:var(--ask); color:var(--askink); border-radius:4px; padding:0 3px } .at { color:var(--at); font-weight:600 }
.empty { color:var(--muted); padding:30px 0; text-align:center }
#typing { padding:6px 22px 14px; min-height:34px; color:var(--muted); font-size:13px }
#typing div { display:flex; gap:8px; align-items:center; padding:2px 0 }
.dots { display:inline-flex; gap:3px } .dots i { width:5px; height:5px; border-radius:50%; background:var(--work); animation:pulse 1s infinite }
.dots i:nth-child(2) { animation-delay:.2s } .dots i:nth-child(3) { animation-delay:.4s }
@media (prefers-reduced-motion: reduce) { * { animation:none !important } }
@media (max-width:760px) { .app { flex-direction:column; height:auto; min-height:100vh } aside { width:auto; max-height:40vh }
  #feed { overflow:visible } }
</style></head><body><div class="app">
<aside><div class="runhead"><h1 id="run">Team review</h1><p id="counts">connecting…</p></div><nav id="list"></nav></aside>
<main><div class="top"><h2 id="title">Waiting for the run</h2><div class="sub" id="sub"></div><div class="members" id="members"></div></div>
<div class="banner" id="banner" hidden></div>
<div id="feed"><div class="empty">Nothing yet.</div></div><div id="typing"></div></main></div>
<script>
const COLORS = ["#2f6f62", "#7a4fb0", "#b5562e", "#2f5d8a", "#8a6d1f", "#a03f6b", "#3f7f2f", "#5a5f6b"];
const DOING = {basis: "is settling the code basis", plan: "is splitting the review", findings: "is checking its part",
  answer: "is answering a question", check: "is checking the team's work", revision: "is fixing its part",
  final: "is writing the team's answer"};
const KIND = {basis: "code basis", plan: "plan", findings: "findings", answer: "answer", review: "sent back",
  revision: "revision", final: "final answer"};
let data = null, sel = null, shown = {key: null, n: 0}, seen = {}, lost = false, chosen = false;

function esc(s) { return s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }
function fmt(t) {
  t = esc(t).replace(/^(\s*\**(?:ASK|REVISE)\**\s+@[A-Za-z0-9_\-]+.*)$/gm, '<span class="ask">$1</span>');
  return t.replace(/(@[A-Za-z0-9_\-]+)/g, '<span class="at">$1</span>');
}
function initials(w) { const p = w.split(/[-_]/).filter(Boolean); return (p.slice(0, 2).map(x => x[0]).join("") || w.slice(0, 2)).toUpperCase(); }
function clock(s) { s = Math.max(0, Math.floor(s)); const m = Math.floor(s / 60); return m >= 60 ? Math.floor(m / 60) + "h " + (m % 60) + "m" : m + ":" + String(s % 60).padStart(2, "0"); }
function people(t) {
  const order = ["code-basis", "lead"].concat(t.agents.map(a => a.id));
  t.posts.forEach(p => { if (!order.includes(p.from) && p.from !== "checker") order.push(p.from); });
  Object.keys(t.working).forEach(w => { if (!order.includes(w) && w !== "checker") order.push(w); });
  order.push("checker");
  const col = {}; order.forEach((w, i) => col[w] = COLORS[i % COLORS.length]);
  return {order, col};
}
function statusOf(t) {
  if (t.state === "done") return /^PASS/.test(t.verdict) ? "pass" : "fail";
  return t.state;
}
function label(t) {
  if (t.state === "done") return t.verdict || "done";
  if (t.state === "working") return Object.keys(t.working).length ? Object.keys(t.working).length + " working" : "working";
  return {waiting: "waiting", grading: "grading", error: "error"}[t.state] || t.state;
}
function renderList() {
  const nav = document.getElementById("list"); nav.innerHTML = "";
  let w = 0, d = 0, wait = 0;
  data.order.forEach(k => {
    const t = data.trials[k];
    if (t.state === "done" || t.state === "error") d++; else if (t.state === "waiting") wait++; else w++;
    const b = document.createElement("button");
    b.className = k === sel ? "sel" : "";
    const unread = k === sel ? 0 : t.posts.length - (seen[k] || 0);
    b.innerHTML = `<span class="st ${statusOf(t)}"></span><span class="ch"><b>${esc(t.task)}</b><span>${esc(t.model)} · trial ${t.trial} · ${esc(label(t))}</span></span>` + (unread > 0 ? `<span class="badge">${unread}</span>` : "");
    b.onclick = () => { sel = k; chosen = true; render(); };
    nav.appendChild(b);
  });
  document.getElementById("run").textContent = "#" + data.run;
  counts.text = `${w} running · ${d} done · ${wait} waiting`;
  renderClock();
}
const counts = {text: ""};
function renderClock() {
  if (!data) return;
  document.getElementById("counts").textContent = counts.text + " · " + clock((data.finished || Date.now() / 1000) - data.started);
}
function renderChannel() {
  const t = data.trials[sel], feed = document.getElementById("feed");
  const {order, col} = people(t);
  document.getElementById("title").textContent = `${t.task} · ${t.model} · trial ${t.trial}`;
  document.getElementById("sub").textContent = t.state === "done" ? "Graded: " + t.verdict : label(t);
  document.getElementById("members").innerHTML = order.map(w =>
    `<span class="chip${t.working[w] ? " busy" : ""}"><i style="background:${col[w]}"></i>@${esc(w)}</span>`).join("");
  const near = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 120;
  if (shown.key !== sel) { feed.innerHTML = ""; shown = {key: sel, n: 0}; }
  if (!t.posts.length && !feed.children.length) {
    feed.innerHTML = `<div class="empty">${t.state === "waiting" ? "This trial has not started yet; trials run --parallel at a time." : "No posts yet."}</div>`;
  }
  if (t.posts.length > shown.n) {
    if (shown.n === 0) feed.innerHTML = "";
    t.posts.slice(shown.n).forEach(m => {
      const a = document.createElement("article");
      a.className = "msg" + (m.kind === "final" ? " final" : "") + (shown.n ? " new" : "");
      const to = m.to && m.to.length ? " → " + m.to.map(x => "@" + x).join(", ") : "";
      a.innerHTML = `<div class="av" style="background:${col[m.from] || COLORS[7]}">${esc(initials(m.from))}</div><div class="body"><header><b>@${esc(m.from)}</b><span class="meta">${KIND[m.kind] || m.kind} · round ${m.round}${esc(to)}</span></header><pre>${fmt(m.text)}</pre></div>`;
      feed.appendChild(a);
    });
    const first = shown.n === 0;
    shown.n = t.posts.length;
    if (near || first) feed.scrollTop = feed.scrollHeight;
  }
  seen[sel] = t.posts.length;
}
function renderTyping() {
  const box = document.getElementById("typing");
  if (!data || !sel) { box.innerHTML = ""; return; }
  const t = data.trials[sel], now = Date.now() / 1000;
  box.innerHTML = Object.entries(t.working).map(([w, v]) =>
    `<div><span class="dots"><i></i><i></i><i></i></span><b>@${esc(w)}</b> ${DOING[v.kind] || "is working"} · ${clock(now - v.since)}</div>`).join("")
    + (t.state === "grading" ? "<div>Grading the checker's answer…</div>" : "");
}
function renderBanner() {
  const b = document.getElementById("banner");
  if (data && data.finished) { b.hidden = false; b.innerHTML = 'The run is finished. Results: <a href="../report.md" target="_blank">report.md</a>'; }
  else if (lost) { b.hidden = false; b.textContent = "Lost the connection to the run. If it is still going, this page reconnects by itself."; }
  else b.hidden = true;
}
function render() {
  if (!data) return;
  if (!chosen) {  // follow the work until the viewer picks a channel
    const cur = sel && data.trials[sel];
    if (!cur || cur.state !== "working") sel = data.order.find(k => data.trials[k].state === "working") || (cur ? sel : data.order[0]);
  } else if (!data.trials[sel]) sel = data.order[0];
  renderList();
  if (sel) renderChannel();
  renderTyping(); renderBanner();
}
async function poll() {
  try {
    const r = await fetch("live.json", {cache: "no-store"});
    if (!r.ok) throw new Error(r.status);
    data = await r.json(); lost = false; render();
    if (data.finished) return;
  } catch (e) { lost = true; renderBanner(); }
  setTimeout(poll, 1500);
}
setInterval(() => { renderTyping(); renderClock(); }, 1000);
poll();
</script></body></html>
"""
