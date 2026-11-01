"""Local task dashboard for expert-eval-harness. Standard library only.

    python3 dashboard/server.py                       # http://127.0.0.1:8765
    python3 dashboard/server.py --data ~/private/dashboard --port 8765

It binds to 127.0.0.1 only. Project records, uploads and logs stay in the --data folder
(default ~/.expert-eval-dashboard), never in this repository. The API key is read from your
shell environment by the harness process; the dashboard only reports whether one is set.
"Export" writes the public summary (stages, sign-offs, run pass rates; no prompt, key,
traps or file contents) that the read-only page on a website loads as data.json.
"""
import argparse, datetime as dt, glob, json, math, os, re, subprocess, sys, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent.parent          # the harness repository (override: --harness)
WEB = Path(__file__).resolve().parent / "web"
PROCESS = json.loads((Path(__file__).resolve().parent / "process.json").read_text())
SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()\-]{0,150}$")
STATUSES = ["not_started", "in_progress", "waiting_for_human", "done"]
KINDS = {"input": "files", "golden": "golden", "reference": "refs", "other": "."}
RUNS = {}
LOCK = threading.Lock()


def now():
    return dt.datetime.now().replace(microsecond=0).isoformat()


class Store:
    def __init__(self, data):
        self.data = Path(data).expanduser()
        for sub in ("projects", "logs", "export"):
            (self.data / sub).mkdir(parents=True, exist_ok=True)

    def path(self, pid):
        if not SAFE.match(pid):
            raise ValueError("bad project id")
        return self.data / "projects" / f"{pid}.json"

    def all(self):
        return [json.loads(p.read_text()) for p in sorted((self.data / "projects").glob("*.json"))]

    def get(self, pid):
        return json.loads(self.path(pid).read_text())

    def put(self, proj):
        proj["updated"] = now()
        with LOCK:
            self.path(proj["id"]).write_text(json.dumps(proj, indent=1))
        return proj


def task_dir(proj):
    d = proj.get("task_dir")
    return Path(d).expanduser() if d else None


def read_task(proj):
    d = task_dir(proj)
    if not d or not (d / "task.json").is_file():
        return None, d
    try:
        return json.loads((d / "task.json").read_text()), d
    except Exception:
        return None, d


def package_status(proj):
    """Which parts of the grader package exist, read from the task folder itself."""
    task, d = read_task(proj)
    have = {}
    have["prompt.md"] = bool(d and (d / "prompt.md").is_file())
    files = task.get("files", []) if task else []
    have["Input files"] = bool(files) and all((d / f).is_file() for f in files)
    have["Basis of design"] = all((proj.get("basis") or {}).get(k) for k, _ in PROCESS["basis_fields"][:5])
    grader_dir = bool(d and (d / "grader").is_dir())
    have["Answer format"] = bool(task and (task.get("answer_format") or task.get("items"))) or grader_dir
    have["Deterministic checks"] = bool(task and task.get("checks")) or grader_dir
    key_graded = bool(task and task.get("key_file"))
    have["Answer key (key.md)"] = bool(task and task.get("key_file") and (d / task["key_file"]).is_file())
    have["Accepted alternatives"] = bool(proj.get("alternatives"))
    have["Lures"] = bool(proj.get("lures"))
    gold = Path(proj["golden_dir"]).expanduser() if proj.get("golden_dir") else None
    have["Golden solution"] = bool(d and ((d / "golden").is_dir() or (d / "reference").is_dir())) or bool(task and task.get("expert_notes")) or bool(gold and gold.is_dir())
    have["Grader tests"] = bool(d and (d / "tests").is_dir())
    have["Code library (optional)"] = bool(task and task.get("ref_queries"))
    out = []
    for g in PROCESS["grader_package"]:
        present = have.get(g["item"], False)
        if g["item"] == "Deterministic checks" and not present and key_graded:
            present = None          # graded item by item against key.md instead
        out.append({"item": g["item"], "required": g["required"], "present": present, "what": g["what"]})
    return out


def files_of(proj):
    task, d = read_task(proj)
    if not d or not d.is_dir():
        return []
    out = []
    for p in sorted(d.rglob("*")):
        if p.is_file() and not any(part.startswith((".", "__pycache__")) for part in p.relative_to(d).parts):
            out.append({"path": str(p.relative_to(d)), "bytes": p.stat().st_size,
                        "modified": dt.datetime.fromtimestamp(p.stat().st_mtime).replace(microsecond=0).isoformat()})
    return out


def pass_at_k(n, c, k):
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n, c, k):
    return math.comb(c, k) / math.comb(n, k) if n >= k else 0.0


def runs_for(task_ids):
    out = []
    if not (ROOT / "runs").is_dir():
        return out
    for meta_p in sorted((ROOT / "runs").glob("*/meta.json")):
        try:
            meta = json.loads(meta_p.read_text())
            rows = [json.loads(l) for l in open(meta_p.parent / "results.jsonl")]
        except Exception:
            continue
        rows = [r for r in rows if r.get("task") in task_ids]
        if not rows:
            continue
        k = meta.get("k", 1)
        per = {}
        for r in rows:
            s = per.setdefault(r["task"] + "|" + r["model"], {"task": r["task"], "model": r["model"], "n": 0, "c": 0, "scores": []})
            s["n"] += 1
            s["c"] += int(bool(r.get("passed")))
            if r.get("score") is not None:
                s["scores"].append(r["score"])
        res = []
        for s in per.values():
            res.append({**s, "k": k, "pass_rate": s["c"] / s["n"],
                        "pass_at_k": round(pass_at_k(s["n"], s["c"], k), 3),
                        "pass_hat_k": round(pass_hat_k(s["n"], s["c"], k), 3),
                        "mean_score": round(sum(s["scores"]) / len(s["scores"]), 2) if s["scores"] else None,
                        "max_score": rows[0].get("max_score")})
        out.append({"run_id": meta.get("run_id", meta_p.parent.name),
                    "date": dt.datetime.fromtimestamp(meta_p.stat().st_mtime).replace(microsecond=0).isoformat(),
                    "models": meta.get("models"), "k": k, "model_library": meta.get("model_library"),
                    "with_refs": meta.get("with_refs"), "judge_tools": meta.get("judge_tools"),
                    "tokens": meta.get("tokens"), "results": res})
    return out


def task_ids(proj):
    task, _ = read_task(proj)
    ids = set(proj.get("run_task_ids") or [])
    if task and task.get("id"):
        ids.add(task["id"])
    return ids


def enrich(proj):
    p = dict(proj)
    p["package"] = package_status(proj)
    p["files"] = files_of(proj)
    p["runs"] = runs_for(task_ids(proj))
    return p


def public_view(proj):
    """What a website may show: progress, sign-offs and results. Never the prompt, key, traps,
    notes or file contents (a published task is a contaminated task)."""
    e = enrich(proj)
    stages = {sid: {k: v for k, v in st.items() if k in ("status", "date", "signed_by", "minutes")}
              for sid, st in (proj.get("stages") or {}).items()}
    basis = {k: v for k, v in (proj.get("basis") or {}).items() if k in ("location", "adopted_code", "standards", "amendments")}
    return {"id": proj["id"], "title": proj.get("title"), "domain": proj.get("domain"), "structure": proj.get("structure"),
            "summary": proj.get("public_summary", ""), "basis": basis, "stages": stages,
            "package": [{"item": x["item"], "required": x["required"], "present": x["present"]} for x in e["package"]],
            "file_count": len(e["files"]),
            "runs": [{"run_id": r["run_id"], "date": r["date"], "models": r["models"], "k": r["k"],
                      "model_library": r["model_library"],
                      "results": [{key: x[key] for key in ("model", "n", "c", "k", "pass_rate", "pass_at_k", "pass_hat_k", "mean_score", "max_score")}
                                  for x in r["results"]]} for r in e["runs"]
                     if not proj.get("public_runs") or r["run_id"] in proj["public_runs"]],
            "updated": proj.get("updated")}


def export(store, site_dir=None):
    pub = {"mode": "public", "generated": now(), "process": PROCESS,
           "projects": [public_view(x) for x in store.all() if x.get("public")]}
    out = store.data / "export" / "data.json"
    out.write_text(json.dumps(pub, indent=1))
    written = [str(out)]
    if site_dir:
        sd = Path(site_dir).expanduser()
        if sd.is_dir():
            (sd / "data.json").write_text(json.dumps(pub, indent=1))
            written.append(str(sd / "data.json"))
    return {"written": ", ".join(written), "projects": len(pub["projects"])}


class App(BaseHTTPRequestHandler):
    store: Store = None
    port = 8765

    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):
        return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

    def write_ok(self):
        origin = self.headers.get("Origin")
        return self.host_ok() and self.headers.get("X-Dashboard") == "1" and \
            (origin is None or origin in (f"http://127.0.0.1:{self.port}", f"http://localhost:{self.port}"))

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 60 * 1024 * 1024:
            raise ValueError("file too large (60 MB limit)")
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "localhost only"})
        u = urlparse(self.path)
        p = unquote(u.path)
        try:
            if p == "/api/state":
                return self.send(200, {"mode": "local", "generated": now(), "process": PROCESS,
                                       "key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
                                       "data_dir": str(self.store.data), "harness": str(ROOT),
                                       "projects": [enrich(x) for x in self.store.all()],
                                       "active_runs": {k: v["status"] for k, v in RUNS.items()}})
            m = re.match(r"^/api/log/([A-Za-z0-9._\-]+)$", p)
            if m:
                f = self.store.data / "logs" / f"{m.group(1)}.log"
                return self.send(200, {"log": f.read_text()[-20000:] if f.is_file() else "", "status": RUNS.get(m.group(1), {}).get("status", "unknown")})
            m = re.match(r"^/api/file/([A-Za-z0-9._\-]+)/(.+)$", p)
            if m:
                proj = self.store.get(m.group(1)); d = task_dir(proj)
                f = (d / m.group(2)).resolve()
                if d and str(f).startswith(str(d.resolve())) and f.is_file() and f.suffix in (".md", ".txt", ".json", ".csv", ".py"):
                    return self.send(200, f.read_bytes(), "text/plain; charset=utf-8")
                return self.send(404, {"error": "not found"})
            name = "index.html" if p in ("/", "") else p.lstrip("/")
            f = (WEB / name).resolve()
            if str(f).startswith(str(WEB)) and f.is_file():
                ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
                         ".json": "application/json", ".svg": "image/svg+xml"}.get(f.suffix, "application/octet-stream")
                return self.send(200, f.read_bytes(), ctype)
            return self.send(404, {"error": "not found"})
        except FileNotFoundError:
            return self.send(404, {"error": "not found"})
        except Exception as e:
            return self.send(400, {"error": str(e)})

    def do_POST(self):
        if not self.write_ok():
            return self.send(403, {"error": "writes are accepted from this dashboard on localhost only"})
        p = unquote(urlparse(self.path).path)
        try:
            if p == "/api/project":
                b = json.loads(self.body() or b"{}")
                pid = b.get("id", "").strip()
                if not SAFE.match(pid) or " " in pid:
                    raise ValueError("id: letters, digits, dots and dashes only")
                if self.store.path(pid).exists():
                    raise ValueError("a project with this id exists")
                d = Path(b.get("task_dir") or (ROOT / "tasks" / pid)).expanduser()
                d.mkdir(parents=True, exist_ok=True)
                if not (d / "task.json").exists():
                    (d / "task.json").write_text(json.dumps({"id": pid, "domain": b.get("domain", "structural"),
                                                             "prompt": "prompt.md", "files": [], "checks": [], "rubric": []}, indent=1))
                proj = {"id": pid, "title": b.get("title") or pid, "domain": b.get("domain", ""), "structure": b.get("structure", ""),
                        "task_dir": str(d), "public": False, "basis": {}, "alternatives": [], "lures": [],
                        "stages": {s["id"]: {"status": "not_started"} for s in PROCESS["stages"]}, "log": [], "created": now()}
                return self.send(200, enrich(self.store.put(proj)))
            m = re.match(r"^/api/project/([A-Za-z0-9._\-]+)/(stage|basis|meta|log|upload|list)$", p)
            if m:
                pid, what = m.groups()
                proj = self.store.get(pid)
                if what == "upload":
                    kind = self.headers.get("X-Kind", "input")
                    name = os.path.basename(unquote(self.headers.get("X-Filename", "")))
                    if not SAFE.match(name):
                        raise ValueError("file name: letters, digits, spaces, dots, dashes and brackets only")
                    d = task_dir(proj)
                    if kind == "prompt":
                        target = d / "prompt.md"
                    elif kind == "key":
                        target = d / "key.md"
                    elif kind in KINDS:
                        target = d / KINDS[kind] / name
                    else:
                        raise ValueError("unknown kind")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(self.body())
                    if kind == "input":
                        tj = d / "task.json"
                        task = json.loads(tj.read_text()) if tj.is_file() else {"id": pid, "files": []}
                        rel = str(target.relative_to(d))
                        if rel not in task.setdefault("files", []):
                            task["files"].append(rel)
                            tj.write_text(json.dumps(task, indent=1))
                    if kind == "key":
                        tj = d / "task.json"
                        task = json.loads(tj.read_text())
                        task["key_file"] = "key.md"
                        tj.write_text(json.dumps(task, indent=1))
                    proj.setdefault("log", []).append({"date": now(), "stage": self.headers.get("X-Stage", ""), "decision": f"uploaded {kind}: {name}", "reason": ""})
                    return self.send(200, enrich(self.store.put(proj)))
                b = json.loads(self.body() or b"{}")
                if what == "stage":
                    sid = b["stage"]
                    if sid not in {s["id"] for s in PROCESS["stages"]} or b.get("status") not in STATUSES:
                        raise ValueError("bad stage or status")
                    st = proj.setdefault("stages", {}).setdefault(sid, {})
                    st.update({"status": b["status"], "date": now()[:10]})
                    for k in ("note", "minutes"):
                        if k in b:
                            st[k] = b[k]
                    if b.get("sign"):
                        st["signed_by"] = b["sign"]
                        st["signed_at"] = now()
                    proj.setdefault("log", []).append({"date": now(), "stage": sid, "decision": f"{sid} -> {b['status']}" + (f", signed by {b['sign']}" if b.get("sign") else ""), "reason": b.get("note", "")})
                elif what == "basis":
                    proj["basis"] = {k: str(b.get(k, "")) for k, _ in PROCESS["basis_fields"]} | {"signed_by": b.get("signed_by", ""), "signed_at": now() if b.get("signed_by") else ""}
                elif what == "meta":
                    for k in ("title", "domain", "structure", "public", "public_summary", "task_dir"):
                        if k in b:
                            proj[k] = b[k]
                elif what == "list":
                    if b.get("field") not in ("alternatives", "lures"):
                        raise ValueError("field")
                    proj[b["field"]] = [str(x) for x in b.get("items", []) if str(x).strip()]
                elif what == "log":
                    proj.setdefault("log", []).append({"date": now(), "stage": b.get("stage", ""), "decision": b.get("decision", ""), "reason": b.get("reason", ""), "minutes": b.get("minutes")})
                return self.send(200, enrich(self.store.put(proj)))
            if p == "/api/run":
                b = json.loads(self.body() or b"{}")
                proj = self.store.get(b["project"])
                models = [m for m in b.get("models", []) if re.match(r"^[a-z0-9.\-]+$", m)]
                k = max(1, min(int(b.get("k", 3)), 10))
                name = re.sub(r"[^A-Za-z0-9._\-]", "-", b.get("name") or f"{proj['id']}-{dt.datetime.now():%Y%m%d-%H%M%S}")
                if not models:
                    raise ValueError("choose at least one model")
                cmd = [sys.executable, "-m", "harness.run", "run", "--models", *models, "--k", str(k),
                       "--tasks", str(task_dir(proj)), "--name", name, "--max-calls", str(int(b.get("max_calls", 30)))]
                for flag in ("judge_tools", "model_library", "with_refs"):
                    if b.get(flag):
                        cmd.append("--" + flag.replace("_", "-"))
                if b.get("ref_lib"):
                    cmd += ["--ref-lib", str(Path(b["ref_lib"]).expanduser())]
                log = open(self.store.data / "logs" / f"{name}.log", "w")
                log.write("$ " + " ".join(cmd) + "\n\n"); log.flush()
                proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
                RUNS[name] = {"status": "running", "proc": proc}
                def wait():
                    rc = proc.wait(); RUNS[name]["status"] = "finished" if rc == 0 else f"exit {rc}"
                threading.Thread(target=wait, daemon=True).start()
                return self.send(200, {"name": name, "cmd": " ".join(cmd)})
            if p == "/api/export":
                site = json.loads(self.body() or b"{}").get("site_dir")
                return self.send(200, export(self.store, site))
            return self.send(404, {"error": "not found"})
        except FileNotFoundError:
            return self.send(404, {"error": "no such project"})
        except Exception as e:
            return self.send(400, {"error": str(e)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.environ.get("EVAL_DASHBOARD_DATA", "~/.expert-eval-dashboard"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--harness", help="harness repository whose runs/ to read (default: this repository)")
    ap.add_argument("--export", nargs="?", const="", metavar="SITE_DIR",
                    help="write the public data.json (and a copy into SITE_DIR if given) and exit")
    a = ap.parse_args()
    global ROOT
    if a.harness:
        ROOT = Path(a.harness).expanduser().resolve()
    if a.export is not None:
        print(json.dumps(export(Store(a.data), a.export or None)))
        return
    App.store, App.port = Store(a.data), a.port
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), App)
    print(f"dashboard: http://127.0.0.1:{a.port}   data: {App.store.data}   harness: {ROOT}")
    print("API key in this shell:", "set" if os.environ.get("ANTHROPIC_API_KEY") else "not set (runs will use mock models only)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
