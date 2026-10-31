#!/usr/bin/env python3
"""Expert eval harness: run expert tasks on several models, grade against answer keys, report and gate.

  python3 -m harness.run run --models claude-haiku-5-5 claude-sonnet-5-5 --k 3
  python3 -m harness.run run --models mock-good mock-bad --k 2          # offline test, no API key
  python3 -m harness.run run --models claude-haiku-5-5 --with-refs      # give the model the reference notes
  python3 -m harness.run report runs/<run_id>
  python3 -m harness.run gate runs/<run_id> --mode difficulty --max-pass 0.5
  python3 -m harness.run gate runs/<run_id> --mode quality --model claude-haiku-5-5 --min-pass 0.8
"""
import argparse
import datetime as dt
import glob
import json
import math
import os
import re
import sys

from harness import api
from harness.refs import RefLibrary
from harness import grader_tools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEM = ("You are an expert answering a professional task. Work carefully, state assumptions, "
          "and do not invent facts, standards or citations. If the task's premise or figures are wrong "
          "or inconsistent, say so instead of forcing an answer.")


CODE_SYSTEM = SYSTEM + (
    " You have a Python sandbox through the code_execution tool. Work like an engineer at a computer: start by loading "
    "the data files with code, then build the analysis step by step in code and check intermediate results. Do the "
    "arithmetic in code, not in your head, and keep your private reasoning short between tool calls. When the analysis "
    "is done, write the final answer as text.")


# ---------------- tasks ----------------

def load_task(task_dir):
    with open(os.path.join(task_dir, "task.json")) as f:
        t = json.load(f)
    t["dir"] = task_dir
    t["prompt_text"] = open(os.path.join(task_dir, t.get("prompt", "prompt.md")), encoding="utf-8").read()
    return t


DATA_EXT = (".csv", ".xlsx", ".xls", ".json", ".txt")


def build_content(task, with_refs, mock, lib_block=""):
    content = []
    for p in task.get("files", []):
        path = os.path.join(task["dir"], p)
        if task.get("code_execution") and not mock and p.lower().endswith(DATA_EXT):
            # data files go into the sandbox, so the model can load them with code instead of retyping them
            content.append({"type": "text", "text": f"(File {os.path.basename(p)} is in the sandbox; also shown below.)"})
            content.append({"type": "container_upload", "file_id": api.upload_file(path)})
        content.append(api.file_block(path))
    if with_refs:
        for p in task.get("refs", []):
            content.append(api.file_block(os.path.join(task["dir"], p)))
        if lib_block:
            content.append({"type": "text", "text": "<reference_library>\n" + lib_block + "\n</reference_library>"})
    fmt = task.get("answer_format", {})
    tail = ""
    if fmt:
        lines = "\n".join(f'  "{k}": {v}' for k, v in fmt.items())
        tail = ("\n\nAfter your working, end your reply with a fenced ```json block containing exactly these keys:\n"
                "{\n" + lines + "\n}")
    content.append({"type": "text", "text": task["prompt_text"] + tail})
    if mock:
        content.append({"type": "text", "text": "<mock_answer>" + json.dumps(task.get("mock_answer", {})) + "</mock_answer>"})
    return content


# ---------------- grading ----------------

def extract_json(text):
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    for b in reversed(blocks):
        try:
            return json.loads(b)
        except ValueError:
            continue
    return None


def check_one(check, answer):
    field = check["field"]
    if answer is None or field not in answer:
        return False, f"{field}: missing"
    got = answer[field]
    kind = check.get("type", "number")
    exp = check["expected"]
    if kind == "number":
        try:
            g = float(str(got).replace(",", ""))
        except ValueError:
            return False, f"{field}: not a number ({got!r})"
        tol = max(check.get("tol_abs", 0), abs(exp) * check.get("tol_rel", 0))
        ok = abs(g - exp) <= tol
        return ok, f"{field}: got {g}, expected {exp} ± {tol:g}"
    if kind == "bool":
        g = got if isinstance(got, bool) else str(got).strip().lower() in ("true", "yes", "1")
        return g == exp, f"{field}: got {g}, expected {exp}"
    if kind == "choice":
        ok = str(got).strip().lower() == str(exp).strip().lower()
        return ok, f"{field}: got {got!r}, expected {exp!r}"
    return False, f"{field}: unknown check type {kind}"


def judge(task, response, judge_model, lib_block=""):
    rubric = task.get("rubric", [])
    if not rubric:
        return [], {}
    items = "\n".join(f'- {r["id"]}: {r["text"]}' for r in rubric)
    prompt = (
        "GRADER. You are grading a response to an expert task against a rubric written by a domain expert. "
        "Judge each rubric item strictly and independently. Use the expert notes as ground truth.\n\n"
        f"<task>\n{task['prompt_text']}\n</task>\n\n<expert_notes>\n{task.get('expert_notes', '')}\n</expert_notes>\n\n"
        + (f"<reference_library>\nUse these current-edition excerpts to check any clause, edition or citation the response relies on. "
           f"A response that applies a superseded edition where the current one differs, or cites a clause that does not exist, fails the relevant item.\n{lib_block}\n</reference_library>\n\n" if lib_block else "") +
        f""
        f"<response>\n{response}\n</response>\n\n<rubric>\n{items}\n</rubric>\n\n"
        'Reply with only JSON: {"items": [{"id": "...", "verdict": "pass" or "fail", "reason": "one sentence"}]}'
    )
    text, usage = api.call(judge_model, [{"type": "text", "text": prompt}], max_tokens=32000)
    m = re.search(r"\{.*\}", text, flags=re.S)
    try:
        verdicts = json.loads(m.group(0))["items"] if m else []
    except (ValueError, KeyError):
        verdicts = []
    if judge_model.startswith("mock"):  # the mock judge returns one verdict for everything
        v = verdicts[0]["verdict"] if verdicts else "fail"
        verdicts = [{"id": r["id"], "verdict": v, "reason": "mock judge"} for r in rubric]
    by_id = {v.get("id"): v for v in verdicts}
    return [by_id.get(r["id"], {"id": r["id"], "verdict": "fail", "reason": "judge gave no verdict"}) for r in rubric], usage


def judge_key(task, response, judge_model, equipped=False, lib=None):
    """Score a response against an expert's full answer key with point items (key mode)."""
    key = open(os.path.join(task["dir"], task["key_file"]), encoding="utf-8").read()
    items = task["items"]
    listing = "\n".join(f'- item {i["id"]}: max {i["points"]} points' + (" (required)" if i.get("required") else "")
                         for i in items)
    prompt = (
        "GRADER. Score the response against the expert answer key below. Follow the key exactly: its items, "
        "tolerances, accepted alternative readings, carry-over rules and common errors. No partial credit within an item. "
        "Do not reward findings the key marks as not valid.\n\n"
        + (f"<harness_note>\n{task['judge_note']}\n</harness_note>\n\n" if task.get("judge_note") else "")
        + f"<task_prompt>\n{task['prompt_text']}\n</task_prompt>\n\n<answer_key>\n{key}\n</answer_key>\n\n"
        f"<response>\n{response}\n</response>\n\n<items_to_score>\n{listing}\n</items_to_score>\n\n"
        + ('Reply with only JSON: {"items": [{"id": "...", "points": <awarded>, "reason": "one sentence"}]}' if not equipped else
           'End with only JSON: {"items": [{"id": "...", "points": <awarded>, "reason": "one sentence", "checked": "what you verified with a tool, if anything"}], '
           '"key_flags": ["possible problem in the key, with the evidence", ...]}')
    )
    trace, flags = [], []
    if equipped and not judge_model.startswith("mock"):
        content = [api.file_block(os.path.join(task["dir"], p)) for p in task.get("files", [])]
        content.append({"type": "text", "text": grader_tools.GUIDE + "\n" + prompt})
        text, usage, trace = grader_tools.run_equipped(judge_model, content, lib)
    else:
        text, usage = api.call(judge_model, [{"type": "text", "text": prompt}], max_tokens=32000)
    i = max(text.rfind('{"items"'), text.rfind('{ "items"'), text.rfind('{\n'))
    try:
        parsed = json.JSONDecoder().raw_decode(text[i:])[0] if i >= 0 else {}
        got = {str(v.get("id")): v for v in parsed.get("items", [])}
        flags = parsed.get("key_flags", []) or []
    except (ValueError, KeyError, AttributeError):
        got = {}
    if judge_model.startswith("mock"):
        full = "MOCK_GOOD" in response
        got = {str(i["id"]): {"points": i["points"] if full else 0, "reason": "mock judge"} for i in items}
    scored = []
    for i in items:
        v = got.get(str(i["id"]), {})
        try:
            pts = max(0.0, min(float(v.get("points", 0)), float(i["points"])))
        except (TypeError, ValueError):
            pts = 0.0
        scored.append({"id": str(i["id"]), "points": pts, "max": i["points"], "required": bool(i.get("required")),
                       "verdict": "pass" if pts >= i["points"] else "fail", "reason": v.get("reason", "judge gave no score"),
                       "checked": v.get("checked", "")})
    usage = dict(usage, key_flags=flags, tool_calls=len(trace))
    return scored, usage


def key_pass(task, scored):
    total = sum(v["points"] for v in scored)
    req_ok = all(v["points"] >= v["max"] for v in scored if v["required"])
    return total, total >= task["pass_score"] and req_ok


# ---------------- metrics ----------------

def pass_at_k(n, c, k):
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def summarise(rows):
    summ = {}
    for r in rows:
        s = summ.setdefault((r["task"], r["model"]), {"n": 0, "c": 0})
        s["n"] += 1
        s["c"] += int(r["passed"])
    return summ


# ---------------- commands ----------------

def cmd_run(a):
    mock = all(m.startswith("mock") for m in a.models)
    judge_model = a.judge or ("mock-judge" if mock else "claude-sonnet-5-5")
    lib_dir = a.ref_lib or os.environ.get("CODE_REF_DIR")
    lib = RefLibrary(lib_dir) if lib_dir else None
    judge_lib = lib
    if lib:
        print(f"reference library: {lib_dir}" + ("" if a.with_refs else " (grader only)"))
    if a.judge_tools:
        print(f"equipped grader: code execution + task files" + (f" + code library {lib_dir}" if judge_lib else ""))
    task_dirs = sorted(d for pat in a.tasks for d in glob.glob(pat) if os.path.isfile(os.path.join(d, "task.json")))
    if not task_dirs:
        sys.exit("no tasks found")
    run_id = a.name or dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ("-refs" if a.with_refs else "")
    out = os.path.join(ROOT, "runs", run_id)
    os.makedirs(out, exist_ok=True)
    planned = len(task_dirs) * len(a.models) * a.k
    print(f"{len(task_dirs)} tasks x {len(a.models)} models x k={a.k} = {planned} model calls (+ judge calls)")
    if planned > a.max_calls:
        sys.exit(f"refusing: {planned} calls is above --max-calls {a.max_calls}")
    rows, tokens = [], {"input_tokens": 0, "output_tokens": 0}
    with open(os.path.join(out, "results.jsonl"), "w") as f:
        for d in task_dirs:
            task = load_task(d)
            lib_block = lib.block_for(task) if lib else ""
            content = build_content(task, a.with_refs, mock, lib_block)
            for model in a.models:
                for trial in range(a.k):
                    try:
                        if task.get("code_execution") and not mock:
                            # the task needs computation: the model under test gets a Python sandbox
                            text, usage, mtrace = grader_tools.run_equipped(
                                model, content, None, max_tokens=a.max_tokens,
                                tools=[grader_tools.CODE_EXEC], system=CODE_SYSTEM, effort=a.effort)
                            print(f"{'':<28} {model:<22} trial {trial + 1}: ran code {sum(1 for t in mtrace if t.get('tool') != 'harness')} times")
                        else:
                            text, usage = api.call(model, content, system=SYSTEM, max_tokens=a.max_tokens, effort=a.effort)
                    except api.APIError as e:
                        sys.exit(f"stopped: {e}")
                    if not text.strip():
                        why = "cut off at max_tokens before any answer (thinking used the whole budget)" \
                            if usage.get("stop_reason") == "max_tokens" else f"empty answer (stop_reason {usage.get('stop_reason')})"
                        print(f"{task['id']:<28} {model:<22} trial {trial + 1}: NO ANSWER - {why}; not graded")
                        row = {"task": task["id"], "domain": task.get("domain"), "model": model, "trial": trial,
                               "with_refs": a.with_refs, "passed": False, "no_answer": why, "checks": [], "rubric": [],
                               "answer": None, "score": None, "max_score": task.get("max_score"),
                               "stop_reason": usage.get("stop_reason"), "response": ""}
                        for key in tokens:
                            tokens[key] += usage.get(key, 0)
                        f.write(json.dumps(row) + "\n")
                        rows.append(row)
                        continue
                    answer = extract_json(text)
                    checks = [dict(zip(("ok", "detail"), check_one(c, answer))) for c in task.get("checks", [])]
                    score = None
                    if task.get("key_file"):
                        verdicts, jusage = judge_key(task, text, judge_model, a.judge_tools, lib or judge_lib)
                        score, passed = key_pass(task, verdicts)
                    else:
                        verdicts, jusage = judge(task, text, judge_model, lib_block)
                        passed = all(c["ok"] for c in checks) and all(v["verdict"] == "pass" for v in verdicts)
                    for u in (usage, jusage):
                        for key in tokens:
                            tokens[key] += u.get(key, 0)
                    row = {"task": task["id"], "domain": task.get("domain"), "model": model, "trial": trial,
                           "with_refs": a.with_refs, "passed": passed, "checks": checks, "rubric": verdicts,
                           "answer": answer, "score": score, "key_flags": jusage.get("key_flags", []) if score is not None else [],
                           "grader_tool_calls": jusage.get("tool_calls", 0) if score is not None else 0, "max_score": task.get("max_score"), "stop_reason": usage.get("stop_reason"), "response": text}
                    f.write(json.dumps(row) + "\n")
                    rows.append(row)
                    sc = f"  ({score:g}/{task.get('max_score')})" if score is not None else ""
                    print(f"{task['id']:<28} {model:<22} trial {trial + 1}: {'PASS' if passed else 'fail'}{sc}")
    meta = {"run_id": run_id, "models": a.models, "k": a.k, "judge_tools": a.judge_tools, "effort": a.effort, "max_tokens": a.max_tokens, "with_refs": a.with_refs, "judge": judge_model,
            "ref_library": bool(lib),
            "tasks": [os.path.basename(d) for d in task_dirs], "tokens": tokens}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=2)
    write_report(out)
    print(f"\nreport: {os.path.join(out, 'report.md')}   tokens used: {tokens}")


def load_run(path):
    meta = json.load(open(os.path.join(path, "meta.json")))
    rows = [json.loads(l) for l in open(os.path.join(path, "results.jsonl"))]
    return meta, rows


def write_report(path):
    meta, rows = load_run(path)
    summ = summarise(rows)
    k = meta["k"]
    tasks = list(dict.fromkeys(r["task"] for r in rows))
    lines = [f"# Eval run {meta['run_id']}", "",
             f"Models: {', '.join(meta['models'])} · k = {k} · references given: {meta['with_refs']} · judge: {meta['judge']}", "",
             "| Task | " + " | ".join(meta["models"]) + " |", "|---|" + "---|" * len(meta["models"])]
    for t in tasks:
        cells = []
        for m in meta["models"]:
            s = summ.get((t, m), {"n": 0, "c": 0})
            sc = [r["score"] for r in rows if r["task"] == t and r["model"] == m and r.get("score") is not None]
            extra = f" (scores {', '.join(f'{x:g}' for x in sc)} of {next(r['max_score'] for r in rows if r['task'] == t)})" if sc else ""
            na = sum(1 for r in rows if r["task"] == t and r["model"] == m and r.get("no_answer"))
            extra += f" [{na} no answer]" if na else ""
            cells.append(f"{s['c']}/{s['n']}{extra}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines += ["", f"| Model | pass rate | pass@{k} | pass^{k} (all {k} trials pass) |", "|---|---|---|---|"]
    for m in meta["models"]:
        ss = [summ[(t, m)] for t in tasks if (t, m) in summ]
        n, c = sum(s["n"] for s in ss), sum(s["c"] for s in ss)
        pak = sum(pass_at_k(s["n"], s["c"], k) for s in ss) / len(ss)
        pck = sum(1 for s in ss if s["c"] == s["n"]) / len(ss)
        lines.append(f"| {m} | {c / n:.0%} | {pak:.0%} | {pck:.0%} |")
    lines += ["", "## Failures", ""]
    for r in rows:
        if not r["passed"]:
            why = [r["no_answer"]] if r.get("no_answer") else ["answer cut off at max_tokens, no JSON block"] if r.get("stop_reason") == "max_tokens" and r.get("answer") is None else []
            why += [c["detail"] for c in r["checks"] if not c["ok"]] + \
                  [(f'item {v["id"]} {v["points"]:g}/{v["max"]:g}' if "max" in v else v["id"]) + f': {v.get("reason", "")}'
                   for v in r["rubric"] if v["verdict"] != "pass"]
            lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: " + "; ".join(why))
    flagged = [(r, f) for r in rows for f in (r.get("key_flags") or [])]
    if flagged:
        lines += ["", "## Grader flags for human review", "",
                  "Possible problems in the answer key that the grader found while checking. Scores still follow the key.", ""]
        for r, f in flagged:
            lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: {f}")
    open(os.path.join(path, "report.md"), "w").write("\n".join(lines) + "\n")


def cmd_report(a):
    write_report(a.run)
    print(open(os.path.join(a.run, "report.md")).read())


def cmd_gate(a):
    meta, rows = load_run(a.run)
    summ = summarise(rows)
    tasks = list(dict.fromkeys(r["task"] for r in rows))
    failed = False
    if a.mode == "difficulty":
        # A task is kept only if the models do not find it easy: overall pass rate at or below --max-pass.
        for t in tasks:
            ss = [s for (tt, _), s in summ.items() if tt == t]
            rate = sum(s["c"] for s in ss) / sum(s["n"] for s in ss)
            keep = rate <= a.max_pass
            print(f"{t:<28} pass rate {rate:.0%}  -> {'KEEP (hard enough)' if keep else 'too easy'}")
    else:
        ss = [summ[(t, a.model)] for t in tasks if (t, a.model) in summ]
        if not ss:
            sys.exit(f"model {a.model} not in this run")
        rate = sum(s["c"] for s in ss) / sum(s["n"] for s in ss)
        failed = rate < a.min_pass
        print(f"{a.model}: pass rate {rate:.0%} (threshold {a.min_pass:.0%}) -> {'BLOCK' if failed else 'PASS'}")
    sys.exit(1 if failed else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run")
    s.add_argument("--models", nargs="+", required=True)
    s.add_argument("--tasks", nargs="+", default=[os.path.join(ROOT, "tasks", "*")])
    s.add_argument("--k", type=int, default=3, help="trials per task per model")
    s.add_argument("--with-refs", action="store_true", help="include each task's reference notes")
    s.add_argument("--ref-lib", help="folder of a local code-ref library (refs.sqlite + sources.json); also CODE_REF_DIR")
    s.add_argument("--judge", help="model that grades rubric items (default claude-sonnet-5-5)")
    s.add_argument("--judge-tools", action="store_true",
                   help="equipped grader for key-scored tasks: code execution, the task's files and the --ref-lib code library")
    s.add_argument("--max-tokens", type=int, default=128000,
                   help="cap on thinking + answer tokens per call; default 128000 is the API maximum for current models")
    s.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="output_config.effort; default is each model's own default")
    s.add_argument("--max-calls", type=int, default=60, help="safety cap on model calls per run")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("report")
    s.add_argument("run")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("gate")
    s.add_argument("run")
    s.add_argument("--mode", choices=["difficulty", "quality"], default="difficulty")
    s.add_argument("--max-pass", type=float, default=0.5)
    s.add_argument("--model")
    s.add_argument("--min-pass", type=float, default=0.8)
    s.set_defaults(fn=cmd_gate)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
