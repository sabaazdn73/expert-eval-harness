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


LIB_NOTE = (" You also have the firm's code library through the code_ref tools (editions, search, page). "
            "Use it as an engineer would use the standards on their desk.")


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


class GradeError(RuntimeError):
    """The grader did not produce a usable grade. The model's answer is kept, so it can be graded again
    (regrade --only-errors, or run --resume) without paying for the answer twice."""


def parse_judge_json(text):
    """The judge's JSON object that holds "items": the last such object in the reply, whether compact or indented.
    Returns {} if there is none."""
    dec = json.JSONDecoder()
    found = {}
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("items"), list):
            found = obj  # keep the last complete one (a reply may quote an example first)
    return found


def _judge_call(judge_model, content, equipped, lib):
    """Run the grader; raise GradeError if it stopped early or gave no parsable items. One retry."""
    last = ""
    for attempt in range(2):
        trace = []
        if equipped:
            text, usage, trace = grader_tools.run_equipped(judge_model, content, lib)
        else:
            text, usage = api.call(judge_model, content, max_tokens=32000, cache=False)
        stop = usage.get("stop_reason")
        parsed = parse_judge_json(text) if text else {}
        if judge_model.startswith("mock") or (parsed.get("items") and stop in ("end_turn", "stop_sequence", None)):
            return text, parsed, usage, trace
        last = f"grader stop_reason={stop}, items parsed={len(parsed.get('items', []))}"
    raise GradeError(last)


def judge(task, response, judge_model, lib_block=""):
    rubric = task.get("rubric", [])
    if not rubric:
        return [], {}
    items = "\n".join(f'- {r["id"]}: {r["text"]}' for r in rubric)
    static = (
        "GRADER. You are grading a response to an expert task against a rubric written by a domain expert. "
        "Judge each rubric item strictly and independently. Use the expert notes as ground truth.\n\n"
        f"<task>\n{task['prompt_text']}\n</task>\n\n<expert_notes>\n{task.get('expert_notes', '')}\n</expert_notes>\n\n"
        + (f"<reference_library>\nUse these excerpts to check any clause, edition or citation the response relies on. "
           f"A response that applies an edition other than the one the task's code basis requires, where the two differ, or "
           f"cites a clause that does not exist, fails the relevant item.\n{lib_block}\n</reference_library>\n\n" if lib_block else "")
        + f"<rubric>\n{items}\n</rubric>\n\n")
    dynamic = (f"<response>\n{response}\n</response>\n\n"
               'Reply with only JSON: {"items": [{"id": "...", "verdict": "pass" or "fail", "reason": "one sentence"}]}')
    if judge_model.startswith("mock"):
        usage = {}
        v = "pass" if "MOCK_GOOD" in response else "fail"
        return [{"id": r["id"], "verdict": v, "reason": "mock judge"} for r in rubric], usage
    content = [{"type": "text", "text": static, "cache_control": dict(api.CACHE_1H)}, {"type": "text", "text": dynamic}]
    _, parsed, usage, _ = _judge_call(judge_model, content, False, None)
    by_id = {str(v.get("id")): v for v in parsed["items"]}
    missing = [r["id"] for r in rubric if str(r["id"]) not in by_id]
    if missing:
        raise GradeError(f"grader gave no verdict for {missing}")
    return [dict(by_id[str(r["id"])], id=r["id"]) for r in rubric], usage


def judge_key(task, response, judge_model, equipped=False, lib=None):
    """Score a response against an expert's full answer key with point items (key mode)."""
    key = open(os.path.join(task["dir"], task["key_file"]), encoding="utf-8").read()
    items = task["items"]
    listing = "\n".join(f'- item {i["id"]}: max {i["points"]} points' + (" (required)" if i.get("required") else "")
                         for i in items)
    static = (
        "GRADER. Score the response against the expert answer key below. Follow the key exactly: its items, "
        "tolerances, accepted alternative readings, carry-over rules and common errors. No partial credit within an item. "
        "Do not reward findings the key marks as not valid.\n\n"
        + (f"<harness_note>\n{task['judge_note']}\n</harness_note>\n\n" if task.get("judge_note") else "")
        + f"<task_prompt>\n{task['prompt_text']}\n</task_prompt>\n\n<answer_key>\n{key}\n</answer_key>\n\n"
        f"<items_to_score>\n{listing}\n</items_to_score>\n\n")
    dynamic = (f"<response>\n{response}\n</response>\n\n"
               + ('Score every item listed above. Reply with only JSON: {"items": [{"id": "...", "points": <awarded>, "reason": "one sentence"}]}'
                  if not equipped else
                  'Score every item listed above. End with only JSON: {"items": [{"id": "...", "points": <awarded>, "reason": "one sentence", '
                  '"checked": "what you verified with a tool, if anything"}], "key_flags": ["possible problem in the key, with the evidence", ...]}'))
    trace, flags = [], []
    if judge_model.startswith("mock"):
        usage = {}
        full = "MOCK_GOOD" in response
        got = {str(i["id"]): {"points": i["points"] if full else 0, "reason": "mock judge"} for i in items}
    else:
        # the key and task are the same for every trial: cached once, then only the response is new
        if equipped:
            content = [api.file_block(os.path.join(task["dir"], p)) for p in task.get("files", [])]
            content.append({"type": "text", "text": grader_tools.GUIDE + "\n" + static, "cache_control": dict(api.CACHE_1H)})
        else:
            content = [{"type": "text", "text": static, "cache_control": dict(api.CACHE_1H)}]
        content.append({"type": "text", "text": dynamic})
        _, parsed, usage, trace = _judge_call(judge_model, content, equipped, lib)
        got = {str(v.get("id")): v for v in parsed["items"]}
        flags = parsed.get("key_flags", []) or []
        missing = [str(i["id"]) for i in items if str(i["id"]) not in got]
        if missing:
            raise GradeError(f"grader gave no score for items {missing}")
    scored = []
    for i in items:
        v = got.get(str(i["id"]), {})
        try:
            pts = float(v.get("points", 0))
            pts = 0.0 if pts != pts else max(0.0, min(pts, float(i["points"])))
        except (TypeError, ValueError):
            pts = 0.0
        if not task.get("partial_credit") and pts < i["points"]:
            pts = 0.0  # keys are all-or-nothing per item unless the task says otherwise
        scored.append({"id": str(i["id"]), "points": pts, "max": i["points"], "required": bool(i.get("required")),
                       "verdict": "pass" if pts >= i["points"] else "fail", "reason": v.get("reason", ""),
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


def grade(task, text, judge_model, judge_tools, lib, lib_block):
    """Grade one answer. Returns (passed, score, verdicts, checks, answer, grader usage); raises GradeError."""
    answer = extract_json(text)
    checks = [dict(zip(("ok", "detail"), check_one(c, answer))) for c in task.get("checks", [])]
    if task.get("key_file"):
        verdicts, jusage = judge_key(task, text, judge_model, judge_tools, lib)
        score, passed = key_pass(task, verdicts)
    else:
        verdicts, jusage = judge(task, text, judge_model, lib_block)
        score, passed = None, all(c["ok"] for c in checks) and all(v["verdict"] == "pass" for v in verdicts)
    return passed, score, verdicts, checks, answer, jusage


def summarise(rows):
    """Pass counts per (task, model). Rows whose grading failed (grade_error) are left out until regraded."""
    summ = {}
    for r in rows:
        if r.get("grade_error"):
            continue
        s = summ.setdefault((r["task"], r["model"]), {"n": 0, "c": 0})
        s["n"] += 1
        s["c"] += int(r["passed"])
    return summ


# ---------------- commands ----------------

def cmd_run(a):
    # "model:k" sets the number of trials for one model, e.g. claude-haiku-5-5:3 claude-sonnet-5-5:2 claude-opus-5-5:1
    ks = {}
    for m in list(a.models):
        name, _, n = m.partition(":")
        ks[name] = int(n) if n.isdigit() else a.k
    a.models = list(ks)
    mock = all(m.startswith("mock") for m in a.models)
    judge_model = a.judge or ("mock-judge" if mock else "claude-sonnet-5-5")
    lib_dir = a.ref_lib or os.environ.get("CODE_REF_DIR")
    lib = RefLibrary(lib_dir) if lib_dir else None
    judge_lib = lib
    if lib:
        print(f"reference library: {lib_dir}" + (" (model: excerpts)" if a.with_refs else "") + (" (model: as tools)" if a.model_library else "") + " (grader)")
    if a.judge_tools:
        print(f"equipped grader: code execution + task files" + (f" + code library {lib_dir}" if judge_lib else ""))
    task_dirs = sorted(d for pat in a.tasks for d in glob.glob(pat) if os.path.isfile(os.path.join(d, "task.json")))
    if not task_dirs:
        sys.exit("no tasks found")
    run_id = a.name or dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ("-refs" if a.with_refs else "")
    out = os.path.join(ROOT, "runs", run_id)
    os.makedirs(out, exist_ok=True)
    planned = len(task_dirs) * sum(ks.values())
    print(f"{len(task_dirs)} tasks; trials per task: " + ", ".join(f"{m} x{ks[m]}" for m in a.models)
          + f" = {planned} model calls (+ judge calls)")
    if planned > a.max_calls:
        sys.exit(f"refusing: {planned} calls is above --max-calls {a.max_calls}")
    rows = []
    tokens = {"model": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
              "grader": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    if a.budget is not None:
        api.set_budget(a.budget)
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()
    done, old_meta = set(), {}
    res_path = os.path.join(out, "results.jsonl")
    if a.resume and os.path.exists(res_path):
        for l in open(res_path):
            r = json.loads(l)
            rows.append(r)
            done.add((r["task"], r["model"], r["trial"]))
        try:
            old_meta = json.load(open(os.path.join(out, "meta.json")))
        except (OSError, ValueError):
            pass
        print(f"resuming: {len(done)} trials already saved", flush=True)
    elif os.path.exists(res_path) and os.path.getsize(res_path) and not a.overwrite:
        sys.exit(f"runs/{run_id} already has results: add --resume to continue it, or --overwrite to start again")
    f = open(res_path, "a" if a.resume else "w")

    def add_tokens(kind, u):
        for key in tokens[kind]:
            tokens[kind][key] += u.get(key, 0) or 0

    def record(row, model_usage, grader_usage, line):
        with lock:
            add_tokens("model", model_usage or {})
            add_tokens("grader", grader_usage or {})
            f.write(json.dumps(row) + "\n")
            f.flush()
            rows.append(row)
            print(line, flush=True)

    tasks_by_id = {}

    def grade_into(row, task, text, lib_block):
        """Grade an answer into its row. On grader failure the answer is kept with grade_error."""
        try:
            passed, score, verdicts, checks, answer, jusage = grade(task, text, judge_model, a.judge_tools, lib, lib_block)
        except Exception as e:
            row.update(passed=False, score=None, grade_error=f"{type(e).__name__}: {str(e)[:300]}")
            return row, {}, "GRADER ERROR (answer kept; regrade with --resume or regrade --only-errors)"
        row.pop("grade_error", None)
        row.update(passed=passed, score=score, rubric=verdicts, checks=checks, answer=answer,
                   key_flags=jusage.get("key_flags", []) if score is not None else [],
                   grader_tool_calls=jusage.get("tool_calls", 0) if score is not None else 0)
        sc = f"  ({score:g}/{task.get('max_score')})" if score is not None else ""
        return row, jusage, ("PASS" if passed else "fail") + sc

    def one(task, content, lib_block, model, trial):
        head = f"{task['id']:<28} {model:<22} trial {trial + 1}: "
        try:
            api.check_budget()
        except api.BudgetExceeded as e:
            print(head + f"skipped: {e} (not saved; raise --budget and use --resume)", flush=True)
            return
        try:
            if a.model_library and lib and not mock:
                # case study: the model under test can look up the code library itself
                mtools = ([grader_tools.CODE_EXEC] if task.get("code_execution") else []) + grader_tools.CLIENT_TOOLS
                text, usage, mtrace = grader_tools.run_equipped(
                    model, content, lib, max_tokens=a.max_tokens, tools=mtools, max_turns=a.max_turns,
                    system=(CODE_SYSTEM if task.get("code_execution") else SYSTEM) + LIB_NOTE, effort=a.effort)
                looked = [t for t in mtrace if str(t.get("tool", "")).startswith("code_ref")]
                note = f"{len(mtrace)} tool calls, {len(looked)} library look-ups"
                usage["library_lookups"] = [t.get("input") for t in looked]
            elif task.get("code_execution") and not mock:
                # the task needs computation: the model under test gets a Python sandbox
                text, usage, mtrace = grader_tools.run_equipped(
                    model, content, None, max_tokens=a.max_tokens, max_turns=a.max_turns,
                    tools=[grader_tools.CODE_EXEC], system=CODE_SYSTEM, effort=a.effort)
                note = f"ran code {sum(1 for t in mtrace if t.get('tool') != 'harness')} times"
            else:
                text, usage = api.call(model, content, system=SYSTEM, max_tokens=a.max_tokens, effort=a.effort)
                note = ""
        except Exception as e:  # one failed trial must not stop the run
            print(head + f"ERROR {str(e)[:300]} (not saved; rerun with --resume)", flush=True)
            return
        row = {"task": task["id"], "domain": task.get("domain"), "model": model, "trial": trial,
               "with_refs": a.with_refs, "passed": False, "checks": [], "rubric": [], "answer": None, "score": None,
               "max_score": task.get("max_score"), "library_lookups": usage.get("library_lookups"),
               "stop_reason": usage.get("stop_reason"), "response": text}
        if not text.strip():
            stop = usage.get("stop_reason")
            why = ("cut off at max_tokens before any answer (thinking used the whole budget)" if stop == "max_tokens"
                   else f"stopped after {a.max_turns} tool turns without a final answer" if stop == "max_turns"
                   else f"empty answer (stop_reason {stop})")
            row["no_answer"] = why
            record(row, usage, {}, head + f"NO ANSWER - {why}; not graded" + (f"  [{note}]" if note else ""))
            return
        row, jusage, verdict = grade_into(row, task, text, lib_block)
        record(row, usage, jusage, head + verdict + (f"  [{note}]" if note else ""))

    def regrade_one(i, task, lib_block):
        r = rows[i]
        r2, jusage, verdict = grade_into(dict(r), task, r["response"], lib_block)
        with lock:
            rows[i] = r2
            add_tokens("grader", jusage)
            print(f"{r['task']:<28} {r['model']:<22} trial {r['trial'] + 1}: regraded: {verdict}", flush=True)

    jobs, regrades = [], []
    for d in task_dirs:
        task = load_task(d)
        tasks_by_id[task["id"]] = task
        lib_block = lib.block_for(task) if lib else ""
        content = build_content(task, a.with_refs, mock, lib_block)
        jobs += [(task, content, lib_block, m, t) for m in a.models for t in range(ks[m]) if (task["id"], m, t) not in done]
        regrades += [(i, task, lib_block) for i, r in enumerate(rows) if r["task"] == task["id"] and r.get("grade_error")]
    print(f"running {len(jobs)} trials, {a.parallel} at a time" + (f"; regrading {len(regrades)} saved answers" if regrades else "")
          + (f"; budget ${a.budget:.2f}" if a.budget is not None else ""), flush=True)
    # Warm the prompt cache: the first trial of each (task, model) starts alone; the other trials of that
    # pair start a little later, once the first request has written the task files to the cache.
    import time as _time
    first, rest, seen = [], [], set()
    for j in jobs:
        key = (j[0]["id"], j[3])
        (rest if key in seen else first).append(j)
        seen.add(key)
    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as pool:
        futs = [pool.submit(regrade_one, *g) for g in regrades]
        futs += [pool.submit(one, *j) for j in first]
        if rest and not mock:
            _time.sleep(a.warmup)
        futs += [pool.submit(one, *j) for j in rest]
        for fut in futs:
            try:
                fut.result()
            except Exception as e:
                print(f"ERROR in a trial: {e}", flush=True)
    f.close()
    planned_keys = {(t, m, k) for t in tasks_by_id for m in a.models for k in range(ks[m])}
    saved_keys = {(r["task"], r["model"], r["trial"]) for r in rows}
    missing = len(planned_keys - saved_keys)
    errs = sum(1 for r in rows if r.get("grade_error"))
    if missing:
        print(f"{missing} trials not saved; run the same command again with --resume to fill them in", flush=True)
    if errs:
        print(f"{errs} answers could not be graded; run the same command with --resume to grade them again (no model calls)", flush=True)
    order = a.models + sorted({r["model"] for r in rows} - set(a.models))
    rows.sort(key=lambda r: (r["task"], order.index(r["model"]), r["trial"]))
    with open(res_path, "w") as f2:
        for r in rows:
            f2.write(json.dumps(r) + "\n")
    if old_meta.get("tokens", {}).get("model"):  # resumed: add what earlier sessions of this run used
        for kind in tokens:
            for key in tokens[kind]:
                tokens[kind][key] += old_meta["tokens"].get(kind, {}).get(key, 0)
    usd, by_model = api.spent()
    usd += old_meta.get("est_cost_usd", 0) or 0
    meta = {"run_id": run_id, "models": order, "k": max(ks.values()), "k_per_model": ks, "judge_tools": a.judge_tools,
            "model_library": a.model_library, "effort": a.effort, "max_tokens": a.max_tokens, "with_refs": a.with_refs,
            "judge": judge_model, "ref_library": bool(lib), "tasks": [os.path.basename(d) for d in task_dirs],
            "tokens": tokens, "est_cost_usd": round(usd, 2),
            "est_cost_by_model": {m: round(v, 2) for m, v in by_model.items()}}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=2)
    write_report(out)
    print(f"\nreport: {os.path.join(out, 'report.md')}")
    print(f"estimated cost of this run: ${usd:.2f} " + json.dumps(meta["est_cost_by_model"]) + "  (check the Console for the billed amount)")


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
             "Models: " + ", ".join(f"{m} (k={(meta.get('k_per_model') or {}).get(m, k)})" for m in meta["models"]) + f" · references given: {meta['with_refs']} · "
             f"code library as a tool: {meta.get('model_library', False)} · judge: {meta['judge']}"
             + (f" · estimated cost ${meta['est_cost_usd']:.2f}" if meta.get("est_cost_usd") is not None else "")
             + (f" · regraded from {meta['regraded_from']}" if meta.get("regraded_from") else ""), "",
             "| Task | " + " | ".join(meta["models"]) + " |", "|---|" + "---|" * len(meta["models"])]
    for t in tasks:
        cells = []
        for m in meta["models"]:
            s = summ.get((t, m), {"n": 0, "c": 0})
            sc = [r["score"] for r in rows if r["task"] == t and r["model"] == m and r.get("score") is not None]
            extra = f" (scores {', '.join(f'{x:g}' for x in sc)} of {next(r['max_score'] for r in rows if r['task'] == t)})" if sc else ""
            na = sum(1 for r in rows if r["task"] == t and r["model"] == m and r.get("no_answer"))
            extra += f" [{na} no answer]" if na else ""
            ge = sum(1 for r in rows if r["task"] == t and r["model"] == m and r.get("grade_error"))
            extra += f" [{ge} not graded yet]" if ge else ""
            cells.append(f"{s['c']}/{s['n']}{extra}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    kpm = meta.get("k_per_model") or {m: k for m in meta["models"]}
    lines += ["", "| Model | trials per task (k) | pass rate | pass@k | pass^k (all k trials pass) |", "|---|---|---|---|---|"]
    for m in meta["models"]:
        ss = [summ[(t, m)] for t in tasks if (t, m) in summ]
        if not ss:
            continue
        km = kpm.get(m, k)
        n, c = sum(s["n"] for s in ss), sum(s["c"] for s in ss)
        pak = sum(pass_at_k(s["n"], s["c"], min(km, s["n"])) for s in ss) / len(ss)
        pck = sum(1 for s in ss if s["c"] == s["n"]) / len(ss)
        lines.append(f"| {m} | {km} | {c / n:.0%} | {pak:.0%} | {pck:.0%} |")
    lines += ["", "## Failures", ""]
    for r in rows:
        if not r["passed"]:
            if r.get("grade_error"):
                lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: NOT GRADED ({r['grade_error']}); "
                             "the answer is saved: run with --resume or regrade --only-errors")
                continue
            why = [r["no_answer"]] if r.get("no_answer") else ["answer cut off at max_tokens, no JSON block"] if r.get("stop_reason") == "max_tokens" and r.get("answer") is None else []
            why += [c["detail"] for c in r["checks"] if not c["ok"]] + \
                  [(f'item {v["id"]} {v["points"]:g}/{v["max"]:g}' if "max" in v else v["id"]) + f': {v.get("reason", "")}'
                   for v in r["rubric"] if v["verdict"] != "pass"]
            lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: " + "; ".join(why))
    looked = [r for r in rows if r.get("library_lookups") is not None]
    if looked:
        lines += ["", "## Code library look-ups by the model", ""]
        for r in looked:
            qs = [q.get("query") or (f"page {q.get('source')} p.{q.get('pdf_page')}" if q.get("source") else "editions")
                  for q in r["library_lookups"] if isinstance(q, dict)]
            lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: {len(qs)} look-ups"
                         + (": " + "; ".join(qs[:25]) if qs else ""))
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


def cmd_regrade(a):
    """Grade the stored answers of an earlier run again with the current task files (a corrected key, say).
    The models are not called again; only the grader runs. Each graded row is saved as it finishes, and a row
    whose grading fails keeps its answer with grade_error, so nothing already paid for is lost."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    meta, rows = load_run(a.run)
    dirs = {}
    for pat in a.tasks:
        for d in glob.glob(pat):
            if os.path.isfile(os.path.join(d, "task.json")):
                t = load_task(d)
                dirs[t["id"]] = t
    judge_model = a.judge or meta.get("judge", "claude-sonnet-5-5")
    lib_dir = a.ref_lib or os.environ.get("CODE_REF_DIR")
    lib = RefLibrary(lib_dir) if lib_dir else None
    in_place = a.only_errors and not a.name
    out = a.run if in_place else os.path.join(ROOT, "runs", a.name or os.path.basename(os.path.normpath(a.run)) + "-regraded")
    os.makedirs(out, exist_ok=True)
    gtok = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    lock = threading.Lock()
    new = [dict(r) for r in rows]
    todo = [i for i, r in enumerate(new) if dirs.get(r["task"]) and not r.get("no_answer") and r.get("response")
            and (not a.only_errors or r.get("grade_error"))]
    print(f"regrading {len(todo)} of {len(new)} saved answers with {judge_model}", flush=True)

    def save():
        with open(os.path.join(out, "results.jsonl"), "w") as f:
            for r in new:
                f.write(json.dumps(r) + "\n")

    def one(i):
        r, task = new[i], dirs[new[i]["task"]]
        lib_block = lib.block_for(task) if lib else ""
        try:
            passed, score, verdicts, checks, answer, ju = grade(task, r["response"], judge_model, a.judge_tools, lib, lib_block)
            r2 = dict(r, passed=passed, score=score, rubric=verdicts, checks=checks, max_score=task.get("max_score"),
                      key_flags=ju.get("key_flags", []) if score is not None else [])
            r2.pop("grade_error", None)
            line = ("PASS" if passed else "fail") + (f"  ({score:g}/{task.get('max_score')})" if score is not None else "")
        except Exception as e:
            r2, ju = dict(r, passed=False, score=None, grade_error=f"{type(e).__name__}: {str(e)[:300]}"), {}
            line = "GRADER ERROR (answer kept)"
        with lock:
            new[i] = r2
            for k in gtok:
                gtok[k] += ju.get(k, 0) or 0
            save()
            print(f"{r['task']:<28} {r['model']:<22} trial {r['trial'] + 1}: {line}", flush=True)

    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as pool:
        for fut in [pool.submit(one, i) for i in todo]:
            fut.result()
    save()
    usd, _ = api.spent()
    if in_place:
        meta = dict(meta, judge=judge_model)
        meta["regrade_cost_usd"] = round((meta.get("regrade_cost_usd") or 0) + usd, 2)
    else:
        # the answers' own cost belongs to the source run: this run only records what the grading cost
        meta = dict(meta, run_id=os.path.basename(out), judge=judge_model, regraded_from=os.path.basename(os.path.normpath(a.run)),
                    judge_tools=a.judge_tools, tokens={"grader": gtok}, est_cost_usd=round(usd, 2), est_cost_by_model={})
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=2)
    write_report(out)
    left = sum(1 for r in new if r.get("grade_error"))
    print(f"\nreport: {os.path.join(out, 'report.md')}   grading cost (estimate): ${usd:.2f}"
          + (f"   {left} still not graded" if left else ""))


def cmd_compare(a):
    """Side-by-side comparison of two or more runs: pass counts, scores, and how often each key item was earned."""
    runs = []
    for path in a.runs:
        meta, rows = load_run(path)
        runs.append((os.path.basename(os.path.normpath(path)), rows))
    names = [n for n, _ in runs]
    pairs = list(dict.fromkeys((r["task"], r["model"]) for _, rows in runs for r in rows))
    out = [f"# Comparison: {' vs '.join(names)}", "",
           "| Task | Model | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for t, m in pairs:
        cells = []
        for _, rows in runs:
            allr = [r for r in rows if r["task"] == t and r["model"] == m]
            rr = [r for r in allr if not r.get("grade_error")]
            if not allr:
                cells.append("–")
                continue
            c = f"{sum(r['passed'] for r in rr)}/{len(rr)} pass"
            ge = len(allr) - len(rr)
            c += f", {ge} not graded" if ge else ""
            sc = [r["score"] for r in rr if r.get("score") is not None]
            if sc and rr:
                c += f", mean {sum(sc) / len(rr):.1f}/{rr[0]['max_score']} ({', '.join(f'{x:g}' for x in sc)})"
            na = sum(1 for r in rr if r.get("no_answer"))
            c += f", {na} no answer" if na else ""
            cells.append(c)
        out.append(f"| {t} | {m} | " + " | ".join(cells) + " |")
    # item by item, for key-scored tasks
    for t, m in pairs:
        items = {}
        for i, (_, rows) in enumerate(runs):
            for r in rows:
                if r["task"] == t and r["model"] == m and not r.get("grade_error"):
                    for v in r.get("rubric", []):
                        if "max" in v:
                            items.setdefault(v["id"], [[0, 0] for _ in runs])
                            items[v["id"]][i][0] += v["points"] >= v["max"]
                            items[v["id"]][i][1] += 1
        if not items:
            continue
        out += ["", f"## {t} · {m}: how often each item was earned", "",
                "| Item | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for iid in sorted(items, key=lambda x: (len(x), x)):
            out.append(f"| {iid} | " + " | ".join(f"{e}/{n}" if n else "–" for e, n in items[iid]) + " |")
    text = "\n".join(out) + "\n"
    if a.out:
        open(a.out, "w").write(text)
    print(text)


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
    s.add_argument("--k", type=int, default=3, help="trials per task per model (or per model: --models haiku:3 sonnet:2)")
    s.add_argument("--with-refs", action="store_true", help="include each task's reference notes")
    s.add_argument("--ref-lib", help="folder of a local code-ref library (refs.sqlite + sources.json); also CODE_REF_DIR")
    s.add_argument("--judge", help="model that grades rubric items (default claude-sonnet-5-5)")
    s.add_argument("--model-library", action="store_true",
                   help="case study: give the model under test the --ref-lib code library as tools (editions, search, page)")
    s.add_argument("--judge-tools", action="store_true",
                   help="equipped grader for key-scored tasks: code execution, the task's files and the --ref-lib code library")
    s.add_argument("--max-tokens", type=int, default=128000,
                   help="cap on thinking + answer tokens per call; default 128000 is the API maximum for current models")
    s.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="output_config.effort; default is each model's own default")
    s.add_argument("--max-calls", type=int, default=60, help="safety cap on model calls per run")
    s.add_argument("--parallel", type=int, default=3, help="trials run at the same time (lower it if you hit rate limits)")
    s.add_argument("--warmup", type=int, default=45, help="seconds to wait after the first trial of each task before the others start, so they read the files from the prompt cache")
    s.add_argument("--budget", type=float, default=20.0,
                   help="estimated USD after which no new trial starts (default 20; trials under way finish and are graded)")
    s.add_argument("--max-turns", type=int, default=25, help="tool-loop turns per trial before it is stopped")
    s.add_argument("--overwrite", action="store_true", help="start the named run again, discarding its saved results")
    s.add_argument("--resume", action="store_true", help="keep the trials already saved in runs/<name> and run only the missing ones")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("report")
    s.add_argument("run")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("regrade", help="grade a run's stored answers again with the current task files")
    s.add_argument("run")
    s.add_argument("--tasks", nargs="+", default=[os.path.join(ROOT, "tasks", "*")])
    s.add_argument("--judge")
    s.add_argument("--judge-tools", action="store_true")
    s.add_argument("--ref-lib")
    s.add_argument("--parallel", type=int, default=3)
    s.add_argument("--only-errors", action="store_true", help="grade only the answers whose grading failed (in place)")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_regrade)
    s = sub.add_parser("compare", help="compare two or more runs side by side")
    s.add_argument("runs", nargs="+")
    s.add_argument("--out", help="also write the comparison to this file")
    s.set_defaults(fn=cmd_compare)
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
