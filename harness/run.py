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
from harness import gemini

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_VERSION = "2026-11-02 (separate Claude/Google budgets, second grader, adjudication, preflight)"
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
    """One deterministic check. "also" lists other accepted values (each with its own expected and tolerance), for a
    key that accepts two defensible readings; the check passes if the main value or any alternative matches."""
    ok, detail = _check_value(check, answer)
    for alt in ([] if ok else check.get("also", [])):
        ok2, d2 = _check_value(dict(check, **alt), answer)
        if ok2:
            return True, d2 + " (accepted alternative)"
    return ok, detail


def _check_value(check, answer):
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
    (regrade --only-errors, or run --resume) without paying for the answer twice. `grades` carries the graders that
    did succeed, so a retry does not pay for them again."""

    def __init__(self, msg, grades=None):
        super().__init__(msg)
        self.grades = grades or {}


def _verdict(v):
    """A grader's pass/fail word, case- and space-insensitive ("Pass", " PASS " -> "pass")."""
    return "pass" if str(v or "").strip().lower() in ("pass", "passed", "yes", "true") else "fail"


def _points(v, max_points):
    """A grader's points for an item as a number. "2", 2, "2/2" and "2 points" are read; anything else is a grading
    error, never a silent zero."""
    if isinstance(v, bool):
        raise GradeError(f"points is not a number: {v!r}")
    if isinstance(v, (int, float)):
        x = float(v)
    else:
        m = re.match(r"\s*(-?\d+(?:\.\d+)?)", str(v if v is not None else ""))
        if not m:
            raise GradeError(f"points is not a number: {v!r}")
        x = float(m.group(1))
    if x != x:
        raise GradeError("points is NaN")
    return max(0.0, min(x, float(max_points)))


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
    """Run the grader; raise GradeError if it stopped early or gave no parsable items. One retry.
    A Claude grader is equipped with code execution + task files + the local code library; a Gemini grader with
    code execution + task files (its own server-side sandbox)."""
    last = ""
    for attempt in range(2):
        trace = []
        if gemini.is_gemini(judge_model):
            # same output allowance as the Claude grader (32k plain, 64k equipped), inside Gemini's 65,536 limit
            text, usage, trace = gemini.run(judge_model, content, system=None, code_execution=equipped,
                                            max_tokens=64000 if equipped else 32000)
        elif equipped:
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
    return [dict(by_id[str(r["id"])], id=r["id"], verdict=_verdict(by_id[str(r["id"])].get("verdict"))) for r in rubric], usage


def _item_id(x):
    """An item id as the grader may write it: "1", 1, "item 1", "Item 5a", "#3", "1." all read as the key's id."""
    s = str(x if x is not None else "").strip().lower()
    s = re.sub(r"^(item|criterion|criteria)[\s_-]*", "", s)
    return s.lstrip("#").rstrip(".:)").strip()


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
            guide = grader_tools.GUIDE_GEMINI if gemini.is_gemini(judge_model) else grader_tools.GUIDE
            content.append({"type": "text", "text": guide + "\n" + static, "cache_control": dict(api.CACHE_1H)})
        else:
            content = [{"type": "text", "text": static, "cache_control": dict(api.CACHE_1H)}]
        content.append({"type": "text", "text": dynamic})
        _, parsed, usage, trace = _judge_call(judge_model, content, equipped, lib)
        got = {_item_id(v.get("id", v.get("item_id", v.get("item")))): v for v in parsed["items"] if isinstance(v, dict)}
        flags = parsed.get("key_flags", []) or []
        missing = [str(i["id"]) for i in items if _item_id(i["id"]) not in got]
        if missing:
            raise GradeError(f"grader gave no score for items {missing} (grader item ids: {list(got)[:15]})")
    scored = []
    for i in items:
        v = got.get(_item_id(i["id"]), {})
        pts = _points(v.get("points"), i["points"]) if not judge_model.startswith("mock") else float(v.get("points", 0))
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

def wilson(c, n, z=1.96):
    """95 % Wilson score interval for a pass rate c/n (sound for small n and rates near 0 or 1)."""
    if not n:
        return 0.0, 0.0
    p = c / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, mid - half), min(1.0, mid + half)


def pass_at_k(n, c, k):
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def grade(task, text, judge_model, judge_tools, lib, lib_block):
    """Grade one answer with one grader. Returns (passed, score, verdicts, checks, answer, grader usage);
    raises GradeError. Deterministic checks (task "checks") gate the pass in rubric mode; in key mode they are
    reported and gate the pass only if the task sets "checks_gate": true (the key's own ranges normally govern)."""
    answer = extract_json(text)
    checks = [dict(zip(("ok", "detail"), check_one(c, answer))) for c in task.get("checks", [])]
    checks_ok = all(c["ok"] for c in checks)
    if task.get("key_file"):
        verdicts, jusage = judge_key(task, text, judge_model, judge_tools, lib)
        score, passed = key_pass(task, verdicts)
        passed = passed and (checks_ok or not task.get("checks_gate"))
    else:
        verdicts, jusage = judge(task, text, judge_model, lib_block)
        score, passed = None, checks_ok and all(v["verdict"] == "pass" for v in verdicts)
    return passed, score, verdicts, checks, answer, jusage


def grade_multi(task, text, judges, judge_tools, lib, lib_block, consensus="primary", prior=None):
    """Grade one answer with every grader in `judges` (the first is the primary). Graders already stored in `prior`
    without an error are kept, so a retry only pays for the missing ones.
    Returns (row fields, grader usage by judge). Raises GradeError only if the primary grader failed; a failed
    secondary grader is stored with its error and retried on --resume / regrade --only-errors."""
    grades = {j: g for j, g in (prior or {}).items() if j in judges and not g.get("error")}
    usage_by = {}
    answer, checks = extract_json(text), None
    for j in judges:
        if j in grades:
            continue
        try:
            passed, score, verdicts, checks, answer, ju = grade(task, text, j, judge_tools, lib, lib_block)
            grades[j] = {"passed": passed, "score": score, "rubric": verdicts,
                         "key_flags": ju.get("key_flags", []) if score is not None else [],
                         "tool_calls": ju.get("tool_calls", 0) if score is not None else 0}
            usage_by[j] = ju
        except Exception as e:
            grades[j] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
    if checks is None:
        checks = [dict(zip(("ok", "detail"), check_one(c, answer))) for c in task.get("checks", [])]
    prim = grades[judges[0]]
    if prim.get("error"):
        raise GradeError(f"primary grader {judges[0]}: {prim['error']}", grades=grades)
    ok = [g for g in grades.values() if not g.get("error")]
    incomplete = len(ok) < len(judges)
    if consensus == "strict" and not incomplete:
        passed = all(g["passed"] for g in ok)
        score = min(g["score"] for g in ok) if prim["score"] is not None else None
    else:
        # strict with a missing grader falls back to the primary for now and is flagged; --resume completes it
        passed, score = prim["passed"], prim["score"]
    fields = {"passed": passed, "score": score, "rubric": prim["rubric"], "checks": checks, "answer": answer,
              "key_flags": sorted({f for g in ok for f in g.get("key_flags", [])}),
              "grader_tool_calls": prim.get("tool_calls", 0), "grades": grades,
              "secondary_grade_error": incomplete, "consensus_incomplete": consensus == "strict" and incomplete,
              "checks_gate": bool(task.get("checks_gate"))}
    return fields, usage_by


def legacy_grades(row, judge):
    """A row saved before graders were stored per grader: its own fields are the primary grader's grade, so a resume
    that adds a second grader does not pay the first one again."""
    if row.get("grades") or row.get("grade_error") or row.get("no_answer") or not judge or "passed" not in row:
        return row.get("grades")
    if not row.get("rubric") and row.get("score") is None:
        return row.get("grades")
    return {judge: {"passed": row["passed"], "score": row.get("score"), "rubric": row.get("rubric", []),
                    "key_flags": row.get("key_flags", []), "tool_calls": row.get("grader_tool_calls", 0)}}


# ---------------- cost estimate before a run ----------------

def _pdf_pages(path):
    """Page count of a PDF, standard library only: the largest /Count of the page tree, also inside compressed
    object streams (Word and LaTeX exports), else the number of page objects."""
    import zlib
    try:
        data = open(path, "rb").read()
    except OSError:
        return 0
    blobs = [data]
    for m in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", m.end())
        if end < 0:
            continue
        try:
            blobs.append(zlib.decompress(data[m.end():end]))
        except zlib.error:
            pass
    counts, pages = [], 0
    for b in blobs:
        for pm in re.finditer(rb"/Type\s*/Pages\b", b):
            win = b[max(0, pm.start() - 400):pm.end() + 400]
            counts += [int(x) for x in re.findall(rb"/Count\s+(\d+)", win)]
        pages += len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", b))
    return max(counts) if counts else max(1, pages)


def task_input_tokens(task, with_refs=False):
    """(low, high) estimate of the prompt tokens one trial sends: files + prompt. PDFs are read as text plus a page
    image, about 1,500 to 3,000 tokens a page."""
    lo = hi = len(task["prompt_text"]) / 4 + 600
    for p in list(task.get("files", [])) + (list(task.get("refs", [])) if with_refs else []):
        path = os.path.join(task["dir"], p)
        if p.lower().endswith(".pdf"):
            n = _pdf_pages(path)
            lo, hi = lo + 1500 * n, hi + 3000 * n
        elif p.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            lo, hi = lo + 1200, hi + 1800
        else:
            try:
                t = os.path.getsize(path) / 4
            except OSError:
                t = 0
            lo, hi = lo + t, hi + t
    return lo, hi


def _price(model):
    return next((v for k, v in api.PRICES.items() if model.startswith(k)), None)


def estimate_cost(tasks, ks, judges, a):
    """Low and high estimate (USD) of a run, by provider and by model, before it starts. Model trials: the first
    trial of each (task, model) writes the prompt to the cache (Claude, 1-hour rate), later ones read it; Gemini is
    taken without caching (its caching is implicit). Gradings: the static grading prompt (task prompt, key, and the
    files for an equipped grader) plus the response. Output per trial between --est-output-low and --est-output."""
    est = {"low": {p: 0.0 for p in api.PROVIDERS}, "high": {p: 0.0 for p in api.PROVIDERS}, "by_model": {}, "unpriced": set()}

    def add(model, side, usd):
        p = api.provider(model)
        if p in est[side]:
            est[side][p] += usd
        est["by_model"].setdefault(model, {"low": 0.0, "high": 0.0})[side] += usd

    for task in tasks:
        tin = task_input_tokens(task, getattr(a, "with_refs", False))
        key_tok = 0
        if task.get("key_file"):
            try:
                key_tok = os.path.getsize(os.path.join(task["dir"], task["key_file"])) / 4
            except OSError:
                pass
        turns = 8 if task.get("code_execution") else 1
        for side, i, out in (("low", 0, a.est_output_low), ("high", 1, a.est_output)):
            n_trials = 0
            for m, k in ks.items():
                pr = _price(m)
                if not pr:
                    if not m.startswith("mock"):
                        est["unpriced"].add(m)
                    continue
                n_trials += k
                inp, outp, rd = pr
                if m.startswith("claude-haiku-5-5") and tin[i] > 100_000:
                    inp, outp = inp * 5, outp * 5
                # a tool loop resends the conversation each turn; it grows by about the output written so far
                growth = (out / 2) * (turns - 1)
                if api.provider(m) == "google":
                    cost = k * ((tin[i] * turns + growth) * inp + out * outp) / 1e6
                else:
                    first = tin[i] * inp * 2 + (tin[i] * (turns - 1) + growth) * inp * rd
                    later = (tin[i] * turns + growth) * inp * rd
                    cost = (first + (k - 1) * later + k * out * outp) / 1e6
                add(m, side, cost)
            # gradings: every trial of every model is graded by every judge
            answer_tok = min(out, 12000)  # the graded text is the answer, not the thinking
            static = len(task["prompt_text"]) / 4 + key_tok + 1500 + (tin[i] if a.judge_tools else 0)
            jturns = 6 if a.judge_tools else 1
            jout = (2500, 9000)[i] * (2 if a.judge_tools else 1)
            for j in judges:
                pr = _price(j)
                if not pr:
                    if not j.startswith("mock"):
                        est["unpriced"].add(j)
                    continue
                inp, outp, rd = pr
                if api.provider(j) == "google":
                    cost = n_trials * ((static + answer_tok) * jturns * inp + jout * outp) / 1e6
                else:
                    cost = (static * inp * 2 + (n_trials - 1) * static * jturns * inp * rd
                            + n_trials * answer_tok * jturns * inp + n_trials * jout * outp) / 1e6 if n_trials else 0
                add(j, side, cost)
    return est


def print_estimate(est, budgets):
    names = {"anthropic": "Claude (Anthropic Console)", "google": "Gemini (Google Cloud)"}
    print("cost estimate before the run (USD; rough, from file sizes and assumed output length):")
    for m, v in est["by_model"].items():
        print(f"  {m:<24} {v['low']:7.2f} – {v['high']:7.2f}")
    for p in api.PROVIDERS:
        b = budgets.get(p)
        print(f"  {names[p]:<28} {est['low'][p]:7.2f} – {est['high'][p]:7.2f}" + (f"   budget {b:.2f}" if b is not None else ""))
    if est["unpriced"]:
        print("  no price for " + ", ".join(sorted(est["unpriced"])) + ": not in the estimate or the budget")


# ---------------- human adjudication ----------------

def load_adjudications(path):
    """runs/<run>/adjudications.json: the expert's final calls on grader disagreements, a list of
    {"task", "model", "trial" (1-based), "item", "points" (key mode) or "verdict" (rubric mode), "note"}.
    They override the primary grader's item scores in the report's adjudicated results."""
    f = os.path.join(path, "adjudications.json")
    if not os.path.exists(f):
        return []
    return json.load(open(f))


def unmatched_adjudications(rows, adj):
    """Filled-in expert calls that match no graded trial and item (a typo in task, model, trial or item id)."""
    have = {(r["task"], r["model"], r["trial"] + 1, str(v["id"])) for r in rows for v in r.get("rubric", [])}
    return [x for x in adj if (x.get("points") is not None or x.get("verdict") is not None)
            and (x["task"], x["model"], int(x["trial"]), str(x["item"])) not in have]


def apply_adjudications(rows, adj):
    """Rows with the expert's item calls applied (copies). Pass/score recomputed from the items for key mode."""
    if not adj:
        return rows
    by = {}
    for x in adj:
        if x.get("points") is None and x.get("verdict") is None:
            continue  # an entry not filled in yet
        by.setdefault((x["task"], x["model"], int(x["trial"]) - 1), {})[str(x["item"])] = x
    out = []
    for r in rows:
        calls = by.get((r["task"], r["model"], r["trial"]))
        if not calls or r.get("grade_error") or r.get("no_answer"):
            out.append(r)
            continue
        r = dict(r, rubric=[dict(v) for v in r.get("rubric", [])], adjudicated=True)
        for v in r["rubric"]:
            c = calls.get(str(v["id"]))
            if not c:
                continue
            if "max" in v:
                if c.get("points") is not None:
                    v["points"] = max(0.0, min(float(c["points"]), float(v["max"])))
                else:
                    v["points"] = float(v["max"]) if _verdict(c.get("verdict")) == "pass" else 0.0
                v["verdict"] = "pass" if v["points"] >= v["max"] else "fail"
            else:  # rubric mode: a verdict, or points (any positive points = pass)
                v["verdict"] = _verdict(c["verdict"]) if c.get("verdict") is not None else (
                    "pass" if float(c["points"]) > 0 else "fail")
            v["reason"] = "expert: " + c.get("note", "")
        if any("max" in v for v in r["rubric"]):
            total = sum(v["points"] for v in r["rubric"])
            req_ok = all(v["points"] >= v["max"] for v in r["rubric"] if v.get("required"))
            ps = r.get("pass_score")
            r["score"] = total
            checks_ok = all(c.get("ok") for c in r.get("checks", [])) or not r.get("checks_gate")
            r["passed"] = (total >= ps if ps is not None else r["passed"]) and req_ok and checks_ok
        else:
            r["passed"] = all(c.get("ok") for c in r.get("checks", [])) and all(v["verdict"] == "pass" for v in r["rubric"])
        out.append(r)
    return out


# ---------------- grader agreement ----------------

def _kappa(pairs):
    """Cohen's kappa for two raters on binary labels; None if undefined."""
    n = len(pairs)
    if not n:
        return None
    po = sum(1 for x, y in pairs if x == y) / n
    pa, pb = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def grader_agreement(rows, judges):
    """Item-level and trial-level agreement between the primary grader and each other grader, and the list of
    item disagreements for the expert to adjudicate."""
    res = {}
    if len(judges) < 2:
        return res
    a0 = judges[0]
    for b in judges[1:]:
        items, trials, dis = [], [], []
        for r in rows:
            g = r.get("grades") or {}
            ga, gb = g.get(a0), g.get(b)
            if r.get("grade_error") or r.get("no_answer") or not ga or not gb or ga.get("error") or gb.get("error"):
                continue
            trials.append((int(bool(ga["passed"])), int(bool(gb["passed"]))))
            vb = {str(v["id"]): v for v in gb.get("rubric", [])}
            for va in ga.get("rubric", []):
                w = vb.get(str(va["id"]))
                if not w:
                    continue
                ea, eb = va["verdict"] == "pass", w["verdict"] == "pass"
                items.append((int(ea), int(eb)))
                if ea != eb or ("max" in va and va.get("points") != w.get("points")):
                    dis.append({"task": r["task"], "model": r["model"], "trial": r["trial"] + 1, "item": va["id"],
                                a0: va.get("points", va["verdict"]), b: w.get("points", w["verdict"]),
                                "reason_" + a0: va.get("reason", ""), "reason_" + b: w.get("reason", "")})
        res[b] = {"items": len(items), "item_agreement": (sum(x == y for x, y in items) / len(items)) if items else None,
                  "item_kappa": _kappa(items), "trials": len(trials),
                  "pass_agreement": (sum(x == y for x, y in trials) / len(trials)) if trials else None,
                  "pass_kappa": _kappa(trials), "disagreements": dis}
    return res


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
    judges = list(dict.fromkeys(a.judge or (["mock-judge"] if mock else ["claude-sonnet-5-5"])))
    judge_model = judges[0]  # primary grader; any further graders are scored alongside it for agreement
    if a.model_library and any(gemini.is_gemini(m) for m in a.models):
        sys.exit("--model-library works with Claude models only; run Gemini without it")
    if any(gemini.is_gemini(m) for m in a.models + judges) and not a.dry_run:
        gemini._key()  # fail now, not after the Claude trials
    if any(api.provider(m) == "anthropic" for m in a.models + judges) and not a.dry_run:
        api._key()
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
    planned = len(task_dirs) * sum(ks.values())
    print(f"{len(task_dirs)} tasks; trials per task: " + ", ".join(f"{m} x{ks[m]}" for m in a.models)
          + f" = {planned} model calls; graders: {', '.join(judges)}" + (f" (equipped)" if a.judge_tools else "")
          + f" = {planned * len(judges)} gradings")
    budgets = {"anthropic": a.budget_claude, "google": a.budget_google}
    est = estimate_cost([load_task(d) for d in task_dirs], ks, judges, a)
    print_estimate(est, budgets)
    if a.dry_run:
        return
    if planned > a.max_calls:
        sys.exit(f"refusing: {planned} calls is above --max-calls {a.max_calls}")
    over = [p for p in budgets if budgets[p] is not None and est["high"][p] > budgets[p]]
    if over and not a.yes and not a.resume:
        sys.exit("refusing: the high estimate is above the budget for " + ", ".join(over)
                 + ". Lower k, drop a model, or raise the budget; add --yes to start anyway (the budget still stops new trials).")
    os.makedirs(out, exist_ok=True)
    rows = []
    tokens = {"model": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
              "grader": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    for p, b in budgets.items():
        if b is not None:
            api.set_budget(b, p)
    started = dt.datetime.now().isoformat(timespec="seconds")
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()
    done, old_meta = set(), {}
    res_path = os.path.join(out, "results.jsonl")
    gemini.TRACE_DIR = os.path.join(out, "traces")  # what goes to each Gemini model under test and what comes back
    if a.resume and os.path.exists(res_path):
        rows = read_results(res_path)
        done = {(r["task"], r["model"], r["trial"]) for r in rows}
        try:
            old_meta = json.load(open(os.path.join(out, "meta.json")))
        except (OSError, ValueError):
            pass
        # the budget covers the whole run: start the meter from what earlier sessions of this run spent
        prior = old_meta.get("est_cost_by_provider")
        if not prior and old_meta.get("est_cost_by_model"):
            prior = {}
            for m, v in old_meta["est_cost_by_model"].items():
                prior[api.provider(m)] = prior.get(api.provider(m), 0) + (v or 0)
        elif not prior and old_meta.get("est_cost_usd"):
            prior = {"anthropic": old_meta["est_cost_usd"]}
        for p, v in (prior or {}).items():
            api.add_spend(p, v or 0)
        legacy_judge = old_meta.get("judge")
        for r in rows:
            if not r.get("grades"):
                g = legacy_grades(r, legacy_judge)
                if g:
                    r["grades"] = g
        print(f"resuming: {len(done)} trials already saved" + (
            "; earlier spend " + ", ".join(f"{p} ${v:.2f}" for p, v in (prior or {}).items()) if prior else ""), flush=True)
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
        """Grade an answer into its row with every grader. On primary-grader failure the answer is kept with
        grade_error; graders that already scored it are kept, so a retry only pays for the missing ones."""
        try:
            fields, usage_by = grade_multi(task, text, judges, a.judge_tools, lib, lib_block, a.consensus,
                                           prior=row.get("grades"))
        except Exception as e:
            row.update(passed=False, score=None, grade_error=f"{type(e).__name__}: {str(e)[:300]}")
            if isinstance(e, GradeError) and e.grades:
                row["grades"] = e.grades  # keep the graders that did succeed
            return row, {}, "GRADER ERROR (answer kept; regrade with --resume or regrade --only-errors)"
        row.pop("grade_error", None)
        row.update(fields, pass_score=task.get("pass_score"))
        jusage = {}
        for u in usage_by.values():
            for k2 in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                jusage[k2] = jusage.get(k2, 0) + (u.get(k2, 0) or 0)
        score = fields["score"]
        sc = f"  ({score:g}/{task.get('max_score')})" if score is not None else ""
        others = [f"{j.replace('claude-', '').replace('gemini-', '')}: " + ("err" if g.get("error") else
                  (f"{g['score']:g}" if g.get("score") is not None else ("pass" if g["passed"] else "fail")))
                  for j, g in fields["grades"].items() if j != judges[0]]
        return row, jusage, ("PASS" if fields["passed"] else "fail") + sc + (f"  [also {'; '.join(others)}]" if others else "")

    def one(task, content, lib_block, model, trial):
        head = f"{task['id']:<28} {model:<22} trial {trial + 1}: "
        try:
            api.check_budget({api.provider(model)} | {api.provider(j) for j in judges})
        except api.BudgetExceeded as e:
            print(head + f"skipped: {e} (not saved; raise --budget and use --resume)", flush=True)
            return
        try:
            if gemini.is_gemini(model):
                # Gemini under test, via Vertex AI; same prompt and files, its own sandbox for code tasks
                code = bool(task.get("code_execution"))
                text, usage, mtrace = gemini.run(model, content, system=CODE_SYSTEM if code else SYSTEM,
                                                 code_execution=code, max_tokens=a.max_tokens, effort=a.effort,
                                                 tag=f"{task['id']}__{model}__trial{trial + 1}")
                note = f"ran code {len(mtrace)} times" if code else ""
            elif a.model_library and lib and not mock:
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
                   else f"Vertex ended the request after {len(mtrace)} code runs without a final answer"
                   if stop == "code_loop_cut"
                   else f"empty answer (stop_reason {stop})")
            row["no_answer"] = why
            record(row, usage, {}, head + f"NO ANSWER - {why}; not graded" + (f"  [{note}]" if note else ""))
            return
        row, jusage, verdict = grade_into(row, task, text, lib_block)
        record(row, usage, jusage, head + verdict + (f"  [{note}]" if note else ""))

    def regrade_one(i, task, lib_block):
        r = rows[i]
        need = [j for j in judges if r.get("grade_error") or j not in (r.get("grades") or {})
                or (r.get("grades") or {}).get(j, {}).get("error")]
        try:
            api.check_budget({api.provider(j) for j in need})
        except api.BudgetExceeded as e:
            print(f"{r['task']:<28} {r['model']:<22} trial {r['trial'] + 1}: regrade skipped: {e}", flush=True)
            return
        r2, jusage, verdict = grade_into(dict(r), task, r["response"], lib_block)
        with lock:
            rows[i] = r2
            add_tokens("grader", jusage)
            f.write(json.dumps(r2) + "\n")  # saved now; the last line for a trial wins when the file is read
            f.flush()
            print(f"{r['task']:<28} {r['model']:<22} trial {r['trial'] + 1}: regraded: {verdict}", flush=True)

    jobs, regrades = [], []
    for d in task_dirs:
        task = load_task(d)
        tasks_by_id[task["id"]] = task
        lib_block = lib.block_for(task) if lib else ""
        content = build_content(task, a.with_refs, mock, lib_block)
        jobs += [(task, content, lib_block, m, t) for m in a.models for t in range(ks[m]) if (task["id"], m, t) not in done]
        regrades += [(i, task, lib_block) for i, r in enumerate(rows) if r["task"] == task["id"] and not r.get("no_answer")
                     and (r.get("grade_error") or r.get("secondary_grade_error")
                          or any(j not in (r.get("grades") or {}) for j in judges))]
    print(f"running {len(jobs)} trials, {a.parallel} at a time" + (f"; regrading {len(regrades)} saved answers" if regrades else "")
          + "".join(f"; {p} budget ${b:.2f}" for p, b in budgets.items() if b is not None), flush=True)
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
    by_prov = api.spent_by_provider()  # on a resume the meter started from the earlier sessions' spend
    for m, v in (old_meta.get("est_cost_by_model") or {}).items():
        by_model[m] = by_model.get(m, 0) + (v or 0)
    usd = sum(by_prov.values())
    meta = {"run_id": run_id, "models": order, "k": max(ks.values()), "k_per_model": ks, "judge_tools": a.judge_tools,
            "model_library": a.model_library, "effort": a.effort, "max_tokens": a.max_tokens, "with_refs": a.with_refs,
            "judge": judge_model, "judges": judges, "consensus": a.consensus, "ref_library": bool(lib),
            "tasks": [os.path.basename(d) for d in task_dirs], "budgets": budgets,
            "task_sha256": {t: task_fingerprint(tk) for t, tk in tasks_by_id.items()},
            "harness_version": HARNESS_VERSION, "started": started,
            "tokens": tokens, "est_cost_usd": round(usd, 2),
            "est_cost_by_provider": {p: round(v, 2) for p, v in by_prov.items()},
            "est_cost_by_model": {m: round(v, 2) for m, v in by_model.items()}}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=2)
    write_report(out)
    print(f"\nreport: {os.path.join(out, 'report.md')}")
    print("estimated cost of this run: Claude (Anthropic Console) ${:.2f}, Gemini (Google Cloud) ${:.2f}  ".format(
        by_prov.get("anthropic", 0), by_prov.get("google", 0)) + json.dumps(meta["est_cost_by_model"])
        + "  (check each provider's billing page for the billed amount)")


def read_results(path):
    """results.jsonl rows, one per (task, model, trial): a later line for the same trial (a regrade appended during
    a run) replaces the earlier one."""
    by = {}
    for l in open(path):
        if l.strip():
            r = json.loads(l)
            by[(r["task"], r["model"], r["trial"])] = r
    return list(by.values())


def load_run(path):
    meta = json.load(open(os.path.join(path, "meta.json")))
    rows = read_results(os.path.join(path, "results.jsonl"))
    return meta, rows


def _view(rows, judge):
    """Rows as one grader scored them (for a secondary grader: its own pass/score/items)."""
    out = []
    for r in rows:
        if r.get("no_answer"):
            out.append(r)  # no answer is a failed trial for every grader
            continue
        g = (r.get("grades") or {}).get(judge)
        if g is None or g.get("error"):
            out.append(dict(r, grade_error=r.get("grade_error") or (g or {}).get("error") or "not graded by " + judge,
                            passed=False))
        else:
            out.append(dict(r, passed=g["passed"], score=g["score"], rubric=g["rubric"]))
    return out


def _tables(rows, meta, tasks):
    summ = summarise(rows)
    k = meta["k"]
    lines = ["| Task | " + " | ".join(meta["models"]) + " |", "|---|" + "---|" * len(meta["models"])]
    for t in tasks:
        cells = []
        for m in meta["models"]:
            s = summ.get((t, m), {"n": 0, "c": 0})
            sc = [r["score"] for r in rows if r["task"] == t and r["model"] == m and r.get("score") is not None
                  and not r.get("grade_error")]
            mx = next((r["max_score"] for r in rows if r["task"] == t), None)
            extra = f" (scores {', '.join(f'{x:g}' for x in sc)} of {mx})" if sc else ""
            na = sum(1 for r in rows if r["task"] == t and r["model"] == m and r.get("no_answer"))
            extra += f" [{na} no answer]" if na else ""
            ge = sum(1 for r in rows if r["task"] == t and r["model"] == m and r.get("grade_error"))
            extra += f" [{ge} not graded yet]" if ge else ""
            cells.append(f"{s['c']}/{s['n']}{extra}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    kpm = meta.get("k_per_model") or {m: k for m in meta["models"]}
    lines += ["", "| Model | trials per task (k) | pass rate (95% CI) | pass@k | pass^k (all k trials pass) | mean score share |",
              "|---|---|---|---|---|---|"]
    for m in meta["models"]:
        ss = [summ[(t, m)] for t in tasks if (t, m) in summ]
        if not ss:
            continue
        km = kpm.get(m, k)
        n, c = sum(s["n"] for s in ss), sum(s["c"] for s in ss)
        pak = sum(pass_at_k(s["n"], s["c"], min(km, s["n"])) for s in ss) / len(ss)
        pck = sum(1 for s in ss if s["n"] >= km and s["c"] == s["n"]) / len(ss)  # fewer than k graded: not claimed
        shares = [(0.0 if r.get("no_answer") else r["score"] / r["max_score"]) for r in rows
                  if r["model"] == m and r.get("max_score") and not r.get("grade_error")
                  and (r.get("no_answer") or r.get("score") is not None)]
        lo, hi = wilson(c, n)
        lines.append(f"| {m} | {km} | {c / n:.0%} ({lo:.0%}–{hi:.0%}, {c}/{n}) | {pak:.0%} | {pck:.0%} | "
                     + (f"{sum(shares) / len(shares):.0%}" if shares else "–") + " |")
    return lines


def write_report(path):
    meta, rows = load_run(path)
    judges = meta.get("judges") or [meta["judge"]]
    k = meta["k"]
    tasks = list(dict.fromkeys(r["task"] for r in rows))
    cost = ""
    if meta.get("est_cost_by_provider"):
        bp = meta["est_cost_by_provider"]
        cost = f" · estimated cost: Claude ${bp.get('anthropic', 0):.2f}, Gemini ${bp.get('google', 0):.2f}"
    elif meta.get("est_cost_usd") is not None:
        cost = f" · estimated cost ${meta['est_cost_usd']:.2f}"
    lines = [f"# Eval run {meta['run_id']}", "",
             "Models: " + ", ".join(f"{m} (k={(meta.get('k_per_model') or {}).get(m, k)})" for m in meta["models"])
             + f" · references given: {meta['with_refs']} · code library as a tool: {meta.get('model_library', False)}"
             + f" · graders: {', '.join(judges)} (primary {judges[0]}" + (", equipped" if meta.get("judge_tools") else "")
             + (f", consensus {meta.get('consensus')}" if len(judges) > 1 else "") + ")" + cost
             + (f" · regraded from {meta['regraded_from']}" if meta.get("regraded_from") else ""), ""]
    adj = load_adjudications(path)
    final = apply_adjudications(rows, adj)
    filled = [x for x in adj if x.get("points") is not None or x.get("verdict") is not None]
    if filled:
        lines += [f"## Results after expert adjudication ({len(filled)} item calls in adjudications.json)", ""]
        bad = unmatched_adjudications(rows, adj)
        if bad:
            lines += ["**Warning:** these adjudications match no graded trial and item and were not applied: "
                      + "; ".join(f"{x['task']} · {x['model']} · trial {x['trial']} · item {x['item']}" for x in bad), ""]
        lines += _tables(final, meta, tasks) + [""]
    inc = sum(1 for r in rows if r.get("consensus_incomplete"))
    if inc:
        lines += [f"**Note:** {inc} trials were scored by the primary grader alone because a second grader failed; "
                  "strict consensus applies once `--resume` or `regrade --only-errors` completes them.", ""]
    lines += [f"## Results by the primary grader ({judges[0]})" + (" - consensus: " + meta.get("consensus") if len(judges) > 1 and meta.get("consensus") == "strict" else ""), ""]
    lines += _tables(rows, meta, tasks)
    for j in judges[1:]:
        lines += ["", f"## Results by the second grader ({j})", ""] + _tables(_view(rows, j), meta, tasks)
    agr = grader_agreement(rows, judges)
    if agr:
        lines += ["", "## Grader agreement", "",
                  "| Primary vs | items compared | item agreement | item kappa | trials compared | pass/fail agreement | pass/fail kappa |",
                  "|---|---|---|---|---|---|---|"]
        fmt = lambda x, pct=True: "–" if x is None else (f"{x:.0%}" if pct else f"{x:.2f}")
        for b, v in agr.items():
            lines.append(f"| {b} | {v['items']} | {fmt(v['item_agreement'])} | {fmt(v['item_kappa'], False)} | {v['trials']} | "
                         f"{fmt(v['pass_agreement'])} | {fmt(v['pass_kappa'], False)} |")
        alld = [d for v in agr.values() for d in v["disagreements"]]
        if alld:
            lines += ["", "### Item disagreements for expert adjudication", "",
                      "Each line: task · model · trial · item: what each grader gave. Write your call in adjudications.json "
                      "(a template with these lines is saved as adjudications_template.json).", ""]
            for d in alld:
                gs = [x for x in d if x not in ("task", "model", "trial", "item") and not x.startswith("reason_")]
                lines.append(f"- **{d['task']}** · {d['model']} · trial {d['trial']} · item {d['item']}: "
                             + "; ".join(f"{g} {d[g]} ({d.get('reason_' + g, '')})" for g in gs))
            tmpl = [{"task": d["task"], "model": d["model"], "trial": d["trial"], "item": d["item"],
                     "points": None, "verdict": None, "note": ""} for d in alld]
            json.dump(tmpl, open(os.path.join(path, "adjudications_template.json"), "w"), indent=1)
    lines += ["", "## Failures (" + ("after adjudication" if adj else f"primary grader {judges[0]}") + ")", ""]
    for r in final:
        if not r["passed"]:
            if r.get("grade_error"):
                lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: NOT GRADED ({r['grade_error']}); "
                             "the answer is saved: run with --resume or regrade --only-errors")
                continue
            why = [r["no_answer"]] if r.get("no_answer") else ["answer cut off at max_tokens, no JSON block"] if r.get("stop_reason") == "max_tokens" and r.get("answer") is None else []
            why += [c["detail"] for c in r["checks"] if not c["ok"]] + \
                  [(f'item {v["id"]} {v["points"]:g}/{v["max"]:g}' if "max" in v else v["id"]) + f': {v.get("reason", "")}'
                   for v in r["rubric"] if v["verdict"] != "pass"]
            for j, g in (r.get("grades") or {}).items():
                if j == judges[0] or g.get("error") or g.get("passed"):
                    continue
                why += [f"[{j}] " + (f'item {v["id"]} {v["points"]:g}/{v["max"]:g}' if "max" in v else str(v["id"]))
                        + f': {v.get("reason", "")}' for v in g.get("rubric", []) if v.get("verdict") != "pass"]
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
                  "Possible problems in the answer key that a grader found while checking. Scores still follow the key.", ""]
        for r, f in flagged:
            lines.append(f"- **{r['task']}** · {r['model']} · trial {r['trial'] + 1}: {f}")
    open(os.path.join(path, "report.md"), "w").write("\n".join(lines) + "\n")


def cmd_report(a):
    write_report(a.run)
    print(open(os.path.join(a.run, "report.md")).read())


def task_fingerprint(task):
    """sha256 of everything a task sends and is graded on (task.json, prompt, key, files), for the run record."""
    import hashlib
    h = hashlib.sha256()
    names = ["task.json", task.get("prompt", "prompt.md")] + ([task["key_file"]] if task.get("key_file") else []) \
        + list(task.get("files", [])) + list(task.get("refs", []))
    for n in names:
        p = os.path.join(task["dir"], n)
        h.update(n.encode() + b"\0")
        try:
            h.update(open(p, "rb").read())
        except OSError:
            h.update(b"<missing>")
    return h.hexdigest()


def validate_task(task):
    """Problems that would waste a paid run: missing files, inconsistent key items, unreadable answer format."""
    errs = []
    for n in [task.get("prompt", "prompt.md")] + list(task.get("files", [])) + ([task["key_file"]] if task.get("key_file") else []):
        if not os.path.isfile(os.path.join(task["dir"], n)):
            errs.append(f"missing file {n}")
    if not task.get("id"):
        errs.append("task.json has no id")
    if task.get("key_file"):
        items = task.get("items") or []
        ids = [str(i.get("id")) for i in items]
        if not items:
            errs.append("key_file set but no items")
        if len(set(ids)) != len(ids):
            errs.append("duplicate item ids")
        if any(not isinstance(i.get("points"), (int, float)) or isinstance(i.get("points"), bool) for i in items):
            errs.append("an item has no numeric points")
        tot = sum(float(i["points"]) for i in items if isinstance(i.get("points"), (int, float)))
        if task.get("max_score") is not None and abs(tot - float(task["max_score"])) > 1e-9:
            errs.append(f"max_score {task['max_score']} != sum of item points {tot:g}")
        if task.get("pass_score") is None or float(task["pass_score"]) > tot:
            errs.append("pass_score missing or above the maximum")
    elif not task.get("rubric") and not task.get("checks"):
        errs.append("no key_file, rubric or checks: nothing to grade")
    for c in task.get("checks", []):
        if c.get("field") not in (task.get("answer_format") or {}):
            errs.append(f"check field {c.get('field')} is not in answer_format")
    return errs


def cmd_preflight(a):
    """Before the one paid run: validate every task, check the API keys, and (with --ping) send one tiny request to
    every model and grader so a wrong model id or endpoint fails now, for a few cents, not mid-run."""
    task_dirs = sorted(d for pat in a.tasks for d in glob.glob(pat) if os.path.isfile(os.path.join(d, "task.json")))
    if not task_dirs:
        sys.exit("no tasks found")
    bad = 0
    for d in task_dirs:
        t = load_task(d)
        errs = validate_task(t)
        bad += bool(errs)
        lo, hi = task_input_tokens(t)
        print(f"{t.get('id', d):<32} {'OK ' if not errs else 'ERR'}  ~{lo / 1000:.0f}-{hi / 1000:.0f}k input tokens  "
              f"sha256 {task_fingerprint(t)[:12]}" + ("  " + "; ".join(errs) if errs else ""))
    models = list(dict.fromkeys([m.partition(":")[0] for m in (a.models or [])] + (a.judge or [])))
    for m in models:
        p = api.provider(m)
        try:
            (gemini._key() if p == "google" else api._key() if p == "anthropic" else None)
        except Exception as e:
            bad += 1
            print(f"{m:<32} ERR  {e}")
            continue
        if not a.ping or p == "mock":
            print(f"{m:<32} key OK ({p})")
            continue
        try:
            msg = [{"type": "text", "text": "Reply with the single word OK."}]
            if p == "google":
                text, _, _ = gemini.run(m, msg, max_tokens=2048)
            else:
                text, _ = api.call(m, msg, max_tokens=1024, cache=False)
            print(f"{m:<32} reachable ({p}): {text.strip()[:20]!r}")
        except Exception as e:
            bad += 1
            print(f"{m:<32} ERR  {str(e)[:300]}")
    if a.ping:
        bp = api.spent_by_provider()
        print(f"ping cost (estimate): Claude ${bp['anthropic']:.3f}, Gemini ${bp['google']:.3f}")
    sys.exit(1 if bad else 0)


def cmd_regrade(a):
    """Grade the stored answers of an earlier run again with the current task files (a corrected key, say), or add a
    grader. The models are not called again; only the graders run. Each graded row is saved as it finishes, and a row
    whose grading fails keeps its answer with grade_error, so nothing already paid for is lost.
    --only-errors: in place, grade only answers with a failed or missing grader (keeps the graders that succeeded)."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    meta, rows = load_run(a.run)
    dirs = {}
    for pat in a.tasks:
        for d in glob.glob(pat):
            if os.path.isfile(os.path.join(d, "task.json")):
                t = load_task(d)
                dirs[t["id"]] = t
    judges = list(dict.fromkeys(a.judge or meta.get("judges") or [meta.get("judge", "claude-sonnet-5-5")]))
    consensus = a.consensus or meta.get("consensus", "primary")
    judge_tools = a.judge_tools or (a.only_errors and meta.get("judge_tools", False))
    lib_dir = a.ref_lib or os.environ.get("CODE_REF_DIR")
    lib = RefLibrary(lib_dir) if lib_dir else None
    in_place = a.only_errors and not a.name
    out = a.run if in_place else os.path.join(ROOT, "runs", a.name or os.path.basename(os.path.normpath(a.run)) + "-regraded")
    os.makedirs(out, exist_ok=True)
    for p, b in (("anthropic", a.budget_claude), ("google", a.budget_google)):
        if b is not None:
            api.set_budget(b, p)
    gtok = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    lock = threading.Lock()
    new = [dict(r) for r in rows]
    todo = [i for i, r in enumerate(new) if dirs.get(r["task"]) and not r.get("no_answer") and r.get("response")
            and (not a.only_errors or r.get("grade_error") or r.get("secondary_grade_error")
                 or any(j not in (r.get("grades") or {}) for j in judges))]
    print(f"regrading {len(todo)} of {len(new)} saved answers with {', '.join(judges)}", flush=True)

    def save():
        with open(os.path.join(out, "results.jsonl"), "w") as f:
            for r in new:
                f.write(json.dumps(r) + "\n")

    legacy_judge = meta.get("judge")

    def one(i):
        r, task = new[i], dirs[new[i]["task"]]
        lib_block = lib.block_for(task) if lib else ""
        prior = (r.get("grades") or legacy_grades(r, legacy_judge)) if a.only_errors else None
        need = [j for j in judges if not (prior or {}).get(j) or (prior or {}).get(j, {}).get("error")]
        try:
            api.check_budget({api.provider(j) for j in need})
        except api.BudgetExceeded as e:  # leave the row exactly as it was
            print(f"{r['task']:<28} {r['model']:<22} trial {r['trial'] + 1}: skipped: {e}", flush=True)
            return
        try:
            fields, usage_by = grade_multi(task, r["response"], judges, judge_tools, lib, lib_block, consensus,
                                           prior=prior)
            r2 = dict(r, max_score=task.get("max_score"), pass_score=task.get("pass_score"), **fields)
            r2.pop("grade_error", None)
            ju = {}
            for u in usage_by.values():
                for k2 in gtok:
                    ju[k2] = ju.get(k2, 0) + (u.get(k2, 0) or 0)
            score = fields["score"]
            line = ("PASS" if fields["passed"] else "fail") + (f"  ({score:g}/{task.get('max_score')})" if score is not None else "")
        except Exception as e:
            r2, ju = dict(r, passed=False, score=None, grade_error=f"{type(e).__name__}: {str(e)[:300]}"), {}
            r2["grades"] = e.grades if isinstance(e, GradeError) else {}
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
    bp = {p: round(v, 2) for p, v in api.spent_by_provider().items()}
    if in_place:
        meta = dict(meta, judge=judges[0], judges=judges, consensus=consensus)
        meta["regrade_cost_usd"] = round((meta.get("regrade_cost_usd") or 0) + usd, 2)
        old = meta.get("regrade_cost_by_provider") or {}
        meta["regrade_cost_by_provider"] = {p: round(old.get(p, 0) + v, 2) for p, v in bp.items()}
    else:
        # the answers' own cost belongs to the source run: this run only records what the grading cost
        meta = dict(meta, run_id=os.path.basename(out), judge=judges[0], judges=judges, consensus=consensus,
                    regraded_from=os.path.basename(os.path.normpath(a.run)), judge_tools=judge_tools,
                    tokens={"grader": gtok}, est_cost_usd=round(usd, 2), est_cost_by_provider=bp, est_cost_by_model={})
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=2)
    write_report(out)
    left = sum(1 for r in new if r.get("grade_error"))
    print(f"\nreport: {os.path.join(out, 'report.md')}   grading cost (estimate): Claude ${bp.get('anthropic', 0):.2f}, "
          f"Gemini ${bp.get('google', 0):.2f}" + (f"   {left} still not graded" if left else ""))


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
    rows = apply_adjudications(rows, load_adjudications(a.run))
    summ = summarise(rows)
    tasks = list(dict.fromkeys(r["task"] for r in rows))
    failed = False
    if a.mode == "difficulty":
        # A task is kept only if the models do not find it easy: overall pass rate at or below --max-pass.
        for t in tasks:
            ss = [s for (tt, _), s in summ.items() if tt == t]
            if not sum(s["n"] for s in ss):
                print(f"{t:<28} no graded trials")
                continue
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
    s.add_argument("--judge", nargs="+", help="grader model(s); the first is the primary, any others are scored alongside "
                   "it for agreement, e.g. --judge claude-opus-5-5 gemini-4-argon (default claude-sonnet-5-5)")
    s.add_argument("--consensus", choices=["primary", "strict"], default="primary",
                   help="primary: the first grader decides pass/score, the others give agreement and a list for expert "
                        "adjudication; strict: a trial passes only if every grader passes it")
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
    s.add_argument("--budget-claude", "--budget", dest="budget_claude", type=float, default=20.0,
                   help="estimated USD on the Anthropic Console (Claude models under test and Claude graders) after which no "
                        "new trial starts (default 20; trials under way finish and are graded)")
    s.add_argument("--budget-google", dest="budget_google", type=float, default=20.0,
                   help="estimated USD on Google Cloud (Gemini models under test and Gemini graders), metered separately (default 20)")
    s.add_argument("--dry-run", action="store_true", help="print the plan and the cost estimate, call nothing")
    s.add_argument("--yes", action="store_true", help="start even if the high cost estimate is above a budget")
    s.add_argument("--est-output", type=int, default=40000, help="high estimate of output (thinking + answer) tokens per trial")
    s.add_argument("--est-output-low", type=int, default=12000, help="low estimate of output tokens per trial")
    s.add_argument("--max-turns", type=int, default=25, help="tool-loop turns per trial before it is stopped")
    s.add_argument("--overwrite", action="store_true", help="start the named run again, discarding its saved results")
    s.add_argument("--resume", action="store_true", help="keep the trials already saved in runs/<name> and run only the missing ones")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("preflight", help="validate tasks and API keys before the paid run; --ping sends one tiny request per model")
    s.add_argument("--tasks", nargs="+", default=[os.path.join(ROOT, "tasks", "*")])
    s.add_argument("--models", nargs="+", default=[])
    s.add_argument("--judge", nargs="+", default=[])
    s.add_argument("--ping", action="store_true")
    s.set_defaults(fn=cmd_preflight)
    s = sub.add_parser("report")
    s.add_argument("run")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("regrade", help="grade a run's stored answers again with the current task files")
    s.add_argument("run")
    s.add_argument("--tasks", nargs="+", default=[os.path.join(ROOT, "tasks", "*")])
    s.add_argument("--judge", nargs="+")
    s.add_argument("--consensus", choices=["primary", "strict"])
    s.add_argument("--budget-claude", dest="budget_claude", type=float, default=20.0)
    s.add_argument("--budget-google", dest="budget_google", type=float, default=20.0)
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
