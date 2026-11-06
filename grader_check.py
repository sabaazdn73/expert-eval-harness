"""Grader check: does the grader pass what should pass and fail what should fail?

Every task has a folder grader_check/ with answers written by hand against the expert key:
  reference.md  earns every item (must PASS)
  lure.md       falls into the task's main trap, a required item is lost (must FAIL)
  boundary.md   earns every required item but ends one point below the pass score (must FAIL)
and expected.json with the points each item should earn.

This script sends those answers to the graders through the harness's own grading code (the same prompt and
scoring used for the models), then compares the graders with the expected scores:
  false pass  = an answer that must fail was passed
  false fail  = an answer that must pass was failed
  item agreement = share of key items where the grader gave the expected points

Usage:
  python3 grader_check.py --judge claude-opus-5-5 gemini-4-argon            # live graders (API keys needed)
  python3 grader_check.py --judge mock-judge                                 # offline wiring test, no cost
Writes runs/grader-check/ (raw grades) and results/grader_check.md + results/grader_check.json.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ANSWERS = ("reference", "lure", "boundary")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", nargs="+", default=["claude-opus-5-5", "gemini-4-argon"])
    ap.add_argument("--tasks", default=os.path.join(ROOT, "tasks", "*"))
    ap.add_argument("--budget-claude", default="10")
    ap.add_argument("--budget-google", default="10")
    ap.add_argument("--name", default="grader-check")
    ap.add_argument("--retry-errors", action="store_true",
                    help="grade again, in place, only the answers whose grading failed in runs/<name> (no new cost for the rest)")
    ap.add_argument("--results", default=os.path.join(ROOT, "results"), help="folder for grader_check.md/.json")
    a = ap.parse_args()

    rows, expected = [], {}
    for d in sorted(glob.glob(a.tasks)):
        exp_path = os.path.join(d, "grader_check", "expected.json")
        if not os.path.isfile(exp_path):
            continue
        task = json.load(open(os.path.join(d, "task.json")))
        exp = json.load(open(exp_path))
        for name in ANSWERS:
            text = open(os.path.join(d, "grader_check", name + ".md"), encoding="utf-8").read()
            rows.append({"task": task["id"], "domain": task.get("domain"), "model": f"answer-{name}", "trial": 0,
                         "with_refs": False, "passed": False, "checks": [], "rubric": [], "answer": None,
                         "score": None, "max_score": task.get("max_score"), "response": text})
            expected[(task["id"], name)] = exp[name]
    if not rows:
        sys.exit("no grader_check/expected.json found under " + a.tasks)

    src = os.path.join(ROOT, "runs", a.name + "-answers")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "results.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    meta = {"run_id": os.path.basename(src), "models": [f"answer-{n}" for n in ANSWERS], "k": 1,
            "k_per_model": {f"answer-{n}": 1 for n in ANSWERS}, "with_refs": False, "judge": a.judge[0],
            "judges": a.judge, "consensus": "primary", "tasks": sorted({r["task"] for r in rows})}
    json.dump(meta, open(os.path.join(src, "meta.json"), "w"), indent=2)

    out = os.path.join(ROOT, "runs", a.name)
    if a.retry_errors and os.path.isfile(os.path.join(out, "results.jsonl")):
        cmd = [sys.executable, "-m", "harness.run", "regrade", out, "--only-errors", "--tasks", a.tasks, "--judge", *a.judge,
               "--budget-claude", a.budget_claude, "--budget-google", a.budget_google, "--parallel", "2"]
    else:
        cmd = [sys.executable, "-m", "harness.run", "regrade", src, "--tasks", a.tasks, "--judge", *a.judge,
               "--name", a.name, "--budget-claude", a.budget_claude, "--budget-google", a.budget_google, "--parallel", "2"]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)

    graded = {}
    for line in open(os.path.join(out, "results.jsonl")):
        if line.strip():
            r = json.loads(line)
            graded[(r["task"], r["model"].removeprefix("answer-"))] = r
    task_meta = {}
    for d in glob.glob(a.tasks):
        if os.path.isfile(os.path.join(d, "task.json")):
            t = json.load(open(os.path.join(d, "task.json")))
            task_meta[t["id"]] = t

    summary = {j: {"answers": 0, "correct_verdict": 0, "false_pass": [], "false_fail": [], "items": 0,
                   "items_agree": 0, "errors": []} for j in a.judge}
    detail = []
    for (tid, name), exp in sorted(expected.items()):
        r = graded.get((tid, name), {})
        t = task_meta[tid]
        exp_items = {str(k): float(v) for k, v in exp["items"].items()}
        line = {"task": tid, "answer": name, "expected_pass": exp["pass"],
                "expected_score": sum(exp_items.values()), "pass_score": t["pass_score"], "graders": {}}
        for j in a.judge:
            g = (r.get("grades") or {}).get(j)
            s = summary[j]
            if not g or g.get("error"):
                s["errors"].append(f"{tid}/{name}: {(g or {}).get('error', 'not graded')}")
                line["graders"][j] = {"error": (g or {}).get("error", "not graded")}
                continue
            got = {str(v["id"]): float(v["points"]) for v in g["rubric"]}
            agree = [i for i in exp_items if got.get(i) == exp_items[i]]
            s["answers"] += 1
            s["items"] += len(exp_items)
            s["items_agree"] += len(agree)
            ok = g["passed"] == exp["pass"]
            s["correct_verdict"] += ok
            if g["passed"] and not exp["pass"]:
                s["false_pass"].append(f"{tid}/{name}")
            if exp["pass"] and not g["passed"]:
                s["false_fail"].append(f"{tid}/{name}")
            line["graders"][j] = {"passed": g["passed"], "score": g["score"],
                                  "item_differences": {i: {"expected": exp_items[i], "got": got.get(i)}
                                                       for i in exp_items if got.get(i) != exp_items[i]}}
        detail.append(line)

    res = {"judges": a.judge, "summary": summary, "detail": detail}
    os.makedirs(a.results, exist_ok=True)
    json.dump(res, open(os.path.join(a.results, "grader_check.json"), "w"), indent=2)

    md = ["# Grader check", "",
          "Hand-written answers per task, graded by the same code and prompt as the model answers. "
          "reference must pass; lure (falls into the task's main trap) and boundary (all required items, "
          "one point below the pass score) must fail.", "",
          "| Grader | Verdicts right | False passes | False fails | Item agreement | Not graded |",
          "|---|---|---|---|---|---|"]
    for j, s in summary.items():
        ia = f"{s['items_agree']}/{s['items']} ({100 * s['items_agree'] / s['items']:.0f}%)" if s["items"] else "-"
        md.append(f"| {j} | {s['correct_verdict']}/{s['answers']} | {len(s['false_pass'])} | {len(s['false_fail'])} | "
                  f"{ia} | {len(s['errors'])} |")
    md += ["", "| Task | Answer | Expected | " + " | ".join(a.judge) + " |", "|---|---|---|" + "---|" * len(a.judge)]
    for l in detail:
        cells = []
        for j in a.judge:
            g = l["graders"][j]
            if "error" in g:
                cells.append("error")
                continue
            diff = ", ".join(f"item {i}: {v['got']:g} not {v['expected']:g}" for i, v in g["item_differences"].items()
                             if v["got"] is not None)
            cells.append(("PASS" if g["passed"] else "fail") + f" {g['score']:g}" + (f" ({diff})" if diff else ""))
        md.append(f"| {l['task']} | {l['answer']} | {'PASS' if l['expected_pass'] else 'fail'} "
                  f"{l['expected_score']:g}/{l['pass_score']} | " + " | ".join(cells) + " |")
    for j, s in summary.items():
        if s["false_pass"] or s["false_fail"]:
            md += ["", f"{j}: false passes {s['false_pass'] or 'none'}; false fails {s['false_fail'] or 'none'}"]
    open(os.path.join(a.results, "grader_check.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
