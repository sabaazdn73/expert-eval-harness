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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEM = ("You are an expert answering a professional task. Work carefully, state assumptions, "
          "and do not invent facts, standards or citations. If the task's premise or figures are wrong "
          "or inconsistent, say so instead of forcing an answer.")


# ---------------- tasks ----------------

def load_task(task_dir):
    with open(os.path.join(task_dir, "task.json")) as f:
        t = json.load(f)
    t["dir"] = task_dir
    t["prompt_text"] = open(os.path.join(task_dir, t.get("prompt", "prompt.md")), encoding="utf-8").read()
    return t


def build_content(task, with_refs, mock):
    content = [api.file_block(os.path.join(task["dir"], p)) for p in task.get("files", [])]
    if with_refs:
        for p in task.get("refs", []):
            content.append(api.file_block(os.path.join(task["dir"], p)))
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


def judge(task, response, judge_model):
    rubric = task.get("rubric", [])
    if not rubric:
        return [], {}
    items = "\n".join(f'- {r["id"]}: {r["text"]}' for r in rubric)
    prompt = (
        "GRADER. You are grading a response to an expert task against a rubric written by a domain expert. "
        "Judge each rubric item strictly and independently. Use the expert notes as ground truth.\n\n"
        f"<task>\n{task['prompt_text']}\n</task>\n\n<expert_notes>\n{task.get('expert_notes', '')}\n</expert_notes>\n\n"
        f"<response>\n{response}\n</response>\n\n<rubric>\n{items}\n</rubric>\n\n"
        'Reply with only JSON: {"items": [{"id": "...", "verdict": "pass" or "fail", "reason": "one sentence"}]}'
    )
    text, usage = api.call(judge_model, [{"type": "text", "text": prompt}], max_tokens=1500, temperature=0)
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
            content = build_content(task, a.with_refs, mock)
            for model in a.models:
                for trial in range(a.k):
                    try:
                        text, usage = api.call(model, content, system=SYSTEM, max_tokens=a.max_tokens)
                    except api.APIError as e:
                        sys.exit(f"stopped: {e}")
                    answer = extract_json(text)
                    checks = [dict(zip(("ok", "detail"), check_one(c, answer))) for c in task.get("checks", [])]
                    verdicts, jusage = judge(task, text, judge_model)
                    for u in (usage, jusage):
                        for key in tokens:
                            tokens[key] += u.get(key, 0)
                    passed = all(c["ok"] for c in checks) and all(v["verdict"] == "pass" for v in verdicts)
                    row = {"task": task["id"], "domain": task.get("domain"), "model": model, "trial": trial,
                           "with_refs": a.with_refs, "passed": passed, "checks": checks, "rubric": verdicts,
                           "answer": answer, "response": text}
                    f.write(json.dumps(row) + "\n")
                    rows.append(row)
                    print(f"{task['id']:<28} {model:<22} trial {trial + 1}: {'PASS' if passed else 'fail'}")
    meta = {"run_id": run_id, "models": a.models, "k": a.k, "with_refs": a.with_refs, "judge": judge_model,
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
            cells.append(f"{s['c']}/{s['n']}")
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
            why = [c["detail"] for c in r["checks"] if not c["ok"]] + \
                  [f'{v["id"]}: {v.get("reason", "")}' for v in r["rubric"] if v["verdict"] != "pass"]
            lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: " + "; ".join(why))
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
    s.add_argument("--judge", help="model that grades rubric items (default claude-sonnet-5-5)")
    s.add_argument("--max-tokens", type=int, default=4000)
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
