"""Offline tests for the parts of the harness that decide grades and spend money. No API key needed.

    python3 -m unittest discover -s tests -v
"""
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from harness import api, grader_tools, run
from harness.refs import RefLibrary


def key_task(tmp, items=((1, 2, True), (2, 1, False))):
    os.makedirs(tmp, exist_ok=True)
    open(os.path.join(tmp, "prompt.md"), "w").write("Review the beam.")
    open(os.path.join(tmp, "key.md"), "w").write("Item 1: find X. Item 2: find Y.")
    t = {"id": "t", "key_file": "key.md",
         "items": [{"id": str(i), "points": p, "required": r} for i, p, r in items],
         "max_score": sum(p for _, p, _ in items), "pass_score": 2}
    json.dump(t, open(os.path.join(tmp, "task.json"), "w"))
    return run.load_task(tmp)


class JudgeParsing(unittest.TestCase):
    verdicts = {"items": [{"id": "1", "points": 2, "reason": "ok"}, {"id": "2", "points": 1, "reason": "ok"}]}

    def test_compact_indented_fenced(self):
        for text in (json.dumps(self.verdicts),
                     json.dumps(self.verdicts, indent=2),
                     "Thinking...\n```json\n" + json.dumps(self.verdicts, indent=4) + "\n```\n"):
            self.assertEqual(len(run.parse_judge_json(text)["items"]), 2, text[:40])

    def test_last_object_wins(self):
        example = '{"items": [{"id": "x", "points": 0}]}'
        text = "Format example " + example + " and my grade:\n" + json.dumps(self.verdicts, indent=2)
        self.assertEqual(run.parse_judge_json(text)["items"][0]["id"], "1")

    def test_no_json(self):
        self.assertEqual(run.parse_judge_json("no json here {not json}"), {})

    def test_judge_key_scores_indented_reply(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            reply = json.dumps(self.verdicts, indent=2)
            with mock.patch.object(api, "call", return_value=(reply, {"stop_reason": "end_turn"})):
                scored, _ = run.judge_key(task, "answer", "claude-sonnet-5-5")
            self.assertEqual([v["points"] for v in scored], [2.0, 1.0])
            self.assertEqual(run.key_pass(task, scored), (3.0, True))

    def test_missing_items_is_a_grade_error_not_a_zero(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            reply = json.dumps({"items": [{"id": "1", "points": 2}]})
            with mock.patch.object(api, "call", return_value=(reply, {"stop_reason": "end_turn"})):
                with self.assertRaises(run.GradeError):
                    run.judge_key(task, "answer", "claude-sonnet-5-5")

    def test_cut_off_judge_retries_then_errors(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            with mock.patch.object(api, "call", return_value=("", {"stop_reason": "max_tokens"})) as c:
                with self.assertRaises(run.GradeError):
                    run.judge_key(task, "answer", "claude-sonnet-5-5")
            self.assertEqual(c.call_count, 2)

    def test_all_or_nothing_and_required(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            reply = json.dumps({"items": [{"id": "1", "points": 1}, {"id": "2", "points": 1}]})
            with mock.patch.object(api, "call", return_value=(reply, {"stop_reason": "end_turn"})):
                scored, _ = run.judge_key(task, "answer", "claude-sonnet-5-5")
            self.assertEqual([v["points"] for v in scored], [0.0, 1.0])  # partial 1/2 on item 1 earns nothing
            self.assertFalse(run.key_pass(task, scored)[1])  # required item 1 missed

    def test_judge_prompt_puts_key_before_response_with_cache_point(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            seen = {}

            def fake(model, content, **kw):
                seen["content"] = content
                return json.dumps(self.verdicts), {"stop_reason": "end_turn"}
            with mock.patch.object(api, "call", side_effect=fake):
                run.judge_key(task, "THE ANSWER", "claude-sonnet-5-5")
            first, second = seen["content"]
            self.assertIn("answer_key", first["text"])
            self.assertNotIn("THE ANSWER", first["text"])
            self.assertIn("cache_control", first)
            self.assertIn("THE ANSWER", second["text"])
            self.assertNotIn("cache_control", second)


class Streams(unittest.TestCase):
    def sse(self, events):
        return io.BytesIO("".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode())

    def test_complete_stream(self):
        msg = api._assemble(self.sse([
            {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hi"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
            {"type": "message_stop"}]))
        self.assertEqual(msg["content"][0]["text"], "hi")
        self.assertEqual(msg["stop_reason"], "end_turn")

    def test_cut_stream_is_retried_not_accepted(self):
        with self.assertRaises(api.StreamCut):
            api._assemble(self.sse([
                {"type": "message_start", "message": {}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "half an ans"}}]))

    def test_overloaded_event_is_retryable(self):
        with self.assertRaises(api.StreamCut):
            api._assemble(self.sse([{"type": "message_start", "message": {}},
                                    {"type": "error", "error": {"type": "overloaded_error"}}]))

    def test_cost_estimate(self):
        self.assertAlmostEqual(api.cost_of("claude-sonnet-5-5", {"input_tokens": 1_000_000}), 2.0)
        self.assertAlmostEqual(api.cost_of("claude-sonnet-5-5", {"cache_read_input_tokens": 1_000_000}), 0.1)
        self.assertAlmostEqual(api.cost_of("claude-haiku-5-5", {"input_tokens": 50_000}), 0.005)
        self.assertAlmostEqual(api.cost_of("claude-haiku-5-5", {"input_tokens": 200_000}), 0.1)


class Library(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        lib = os.path.join(self.tmp.name, "lib")
        os.makedirs(lib)
        c = sqlite3.connect(os.path.join(lib, "refs.sqlite"))
        c.execute("CREATE VIRTUAL TABLE pages USING fts5(source UNINDEXED, page UNINDEXED, body)")
        for i in range(1, 50):
            c.execute("INSERT INTO pages VALUES ('A', ?, ?)", (i, f"clause 18.10.{i} wall boundary element page {i}"))
        c.commit()
        json.dump({"sources": [{"id": "A", "family": "ACI 318", "edition": "318-19", "status": "superseded", "kind": "standard",
                                "path": "x.pdf"}],
                   "ibc_adoption": {"IBC 2024": {"ACI 318": "318-19"}}}, open(os.path.join(lib, "sources.json"), "w"))
        self.lib = RefLibrary(lib)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bad_queries_do_not_raise(self):
        for args in ({"query": '"wall" "'}, {"query": 'ACI "318-19" 18.10'}, {"query": "(*)"}):
            self.assertNotIn("Traceback", grader_tools._client_tool("code_ref_search", args, self.lib))
        out = grader_tools._client_tool("code_ref_page", {"source": "A", "pdf_page": "12a"}, self.lib)
        self.assertTrue(out.startswith("error:"))
        self.assertTrue(grader_tools._client_tool("code_ref_page", {"source": "NOPE", "pdf_page": 1}, self.lib).startswith("error:"))

    def test_superseded_but_adopted_edition_is_found_and_labelled(self):
        hits = json.loads(grader_tools._client_tool("code_ref_search", {"query": "boundary element"}, self.lib))
        self.assertTrue(hits)
        self.assertEqual(hits[0]["adopted_by"], ["IBC 2024"])

    def test_threads_get_correct_rows(self):
        errors = []

        def work():
            for _ in range(200):
                try:
                    if len(self.lib.search("boundary element", current_only=False, limit=5)) != 5:
                        errors.append("count")
                except Exception as e:
                    errors.append(repr(e))
        ts = [threading.Thread(target=work) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])


@mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "GOOGLE_API_KEY": "test-key"})
class Runs(unittest.TestCase):
    def test_grade_error_keeps_answer_and_resume_regrades_it(self):
        with tempfile.TemporaryDirectory() as d:
            task_dir = os.path.join(d, "t")
            key_task(task_dir)
            name = "zz_unit_" + str(os.getpid())
            out = os.path.join(run.ROOT, "runs", name)
            argv = ["run", "--models", "fake-model:2", "--tasks", task_dir, "--name", name, "--warmup", "0", "--judge", "claude-sonnet-5-5"]
            good = json.dumps({"items": [{"id": "1", "points": 2}, {"id": "2", "points": 1}]})
            calls = {"n": 0}

            def fake_call(model, content, **kw):
                if model == "fake-model":
                    return "my answer", {"stop_reason": "end_turn", "output_tokens": 10}
                calls["n"] += 1
                return ("garbage", {"stop_reason": "end_turn"}) if calls["n"] <= 4 else (good, {"stop_reason": "end_turn"})
            try:
                with mock.patch.object(api, "call", side_effect=fake_call), mock.patch("sys.argv", ["x"] + argv):
                    run.main()
                rows = [json.loads(l) for l in open(os.path.join(out, "results.jsonl"))]
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(r.get("grade_error") and r["response"] == "my answer" for r in rows))
                model_calls = []

                def fake_call2(model, content, **kw):
                    if model == "fake-model":
                        model_calls.append(1)
                    return fake_call(model, content, **kw)
                with mock.patch.object(api, "call", side_effect=fake_call2), mock.patch("sys.argv", ["x"] + argv + ["--resume"]):
                    run.main()
                rows = [json.loads(l) for l in open(os.path.join(out, "results.jsonl"))]
                self.assertEqual(model_calls, [])  # no answer paid for twice
                self.assertTrue(all(r["passed"] and not r.get("grade_error") for r in rows))
            finally:
                import shutil
                shutil.rmtree(out, ignore_errors=True)


class Gemini(unittest.TestCase):
    def test_parts_from_claude_content(self):
        from harness import gemini
        content = [{"type": "text", "text": "(File loads.csv is in the sandbox; also shown below.)"},
                   {"type": "container_upload", "file_id": "f1"},
                   {"type": "text", "text": '<file name="loads.csv">\na,b\n1,2\n</file>'},
                   {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "UERG"}},
                   {"type": "text", "text": "Prompt", "cache_control": {"type": "ephemeral"}}]
        b = gemini.body_for(content, system="S", code_execution=True, max_tokens=128000, effort="xhigh")
        parts = b["contents"][0]["parts"]
        self.assertIn("attached for code execution", parts[0]["text"])
        self.assertEqual(parts[2]["inlineData"]["mimeType"], "text/csv")
        self.assertEqual(base64_decode(parts[2]["inlineData"]["data"]), "a,b\n1,2")
        self.assertEqual(parts[3]["inlineData"]["mimeType"], "application/pdf")
        self.assertNotIn("cache_control", json.dumps(b))
        self.assertEqual(b["generationConfig"]["maxOutputTokens"], 65536)
        self.assertEqual(b["generationConfig"]["thinkingConfig"]["thinkingLevel"], "high")
        self.assertEqual(b["tools"], [{"codeExecution": {}}])

    def test_stream(self):
        from harness import gemini
        ev = [{"candidates": [{"content": {"parts": [{"text": "plan", "thought": True}, {"text": "Let me compute. "}]}}]},
              {"candidates": [{"content": {"parts": [{"executableCode": {"code": "print(1+1)"}},
                                                     {"codeExecutionResult": {"output": "2"}}, {"text": "Answer 2"}]},
                               "finishReason": "STOP"}],
               "usageMetadata": {"promptTokenCount": 1000, "cachedContentTokenCount": 400, "candidatesTokenCount": 50,
                                 "thoughtsTokenCount": 200}}]
        text, u, trace = gemini.assemble([("data: " + json.dumps(e)).encode() for e in ev])
        self.assertEqual(text, "Let me compute. Answer 2")
        self.assertEqual((u["input_tokens"], u["cache_read_input_tokens"], u["output_tokens"], u["stop_reason"]),
                         (600, 400, 250, "end_turn"))
        self.assertEqual(len(trace), 1)
        with self.assertRaises(api.StreamCut):
            gemini.assemble([("data: " + json.dumps(ev[0])).encode()])

    def test_key_never_in_url(self):
        from harness import gemini
        with mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "SECRET", "GOOGLE_CLOUD_PROJECT": "p1"}):
            url = gemini.endpoint("gemini-4-argon")
        self.assertNotIn("SECRET", url)
        self.assertEqual(url, "https://aiplatform.googleapis.com/v1/projects/p1/locations/global/publishers/google/models/"
                              "gemini-4-argon:streamGenerateContent?alt=sse")


def base64_decode(s):
    import base64
    return base64.b64decode(s).decode()


if __name__ == "__main__":
    unittest.main()


class Providers(unittest.TestCase):
    """Claude (Anthropic Console) and Gemini (Google Cloud) are metered and budgeted separately."""

    def setUp(self):
        api.reset_meter()

    def tearDown(self):
        api.reset_meter()

    def test_provider_of_models(self):
        self.assertEqual(api.provider("claude-opus-5-5"), "anthropic")
        self.assertEqual(api.provider("gemini-4-argon"), "google")
        self.assertEqual(api.provider("mock-good"), "mock")

    def test_separate_meters_and_budgets(self):
        api.set_budget(1.0, "anthropic")
        api.set_budget(100.0, "google")
        api._charge("gemini-4-argon", {"input_tokens": 1_000_000})  # $2 on Google
        by = api.spent_by_provider()
        self.assertAlmostEqual(by["google"], 2.0)
        self.assertAlmostEqual(by["anthropic"], 0.0)
        api.check_budget("anthropic")  # Google spend does not touch the Claude budget
        api._charge("claude-opus-5-5", {"input_tokens": 300_000})  # $1.20 on Anthropic
        with self.assertRaises(api.BudgetExceeded):
            api.check_budget("anthropic")
        api.check_budget("google")  # Google still under its own budget
        with self.assertRaises(api.BudgetExceeded):
            api.check_budget({"google", "anthropic"})  # a Gemini trial graded by Opus needs both

    def test_flash_is_priced(self):
        self.assertGreater(api.cost_of("gemini-3.8-flash", {"input_tokens": 1_000_000}), 0)


class TwoGraders(unittest.TestCase):
    def test_primary_decides_secondary_kept_and_agreement(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            full = json.dumps({"items": [{"id": "1", "points": 2, "reason": "a"}, {"id": "2", "points": 1, "reason": "b"}]})
            part = json.dumps({"items": [{"id": "1", "points": 2, "reason": "a"}, {"id": "2", "points": 0, "reason": "c"}]})
            from harness import gemini
            with mock.patch.object(api, "call", return_value=(full, {"stop_reason": "end_turn"})), \
                 mock.patch.object(gemini, "run", return_value=(part, {"stop_reason": "end_turn"}, [])) as g:
                fields, _ = run.grade_multi(task, "answer", ["claude-opus-5-5", "gemini-4-argon"], False, None, "")
            self.assertEqual(g.call_count, 1)
            self.assertTrue(fields["passed"])
            self.assertEqual(fields["score"], 3.0)
            self.assertEqual(fields["grades"]["gemini-4-argon"]["score"], 2.0)
            rows = [dict(fields, task="t", model="m", trial=0)]
            agr = run.grader_agreement(rows, ["claude-opus-5-5", "gemini-4-argon"])["gemini-4-argon"]
            self.assertEqual(agr["items"], 2)
            self.assertEqual(agr["item_agreement"], 0.5)
            self.assertEqual(len(agr["disagreements"]), 1)
            self.assertEqual(agr["disagreements"][0]["item"], "2")

    def test_strict_consensus(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            full = json.dumps({"items": [{"id": "1", "points": 2}, {"id": "2", "points": 1}]})
            fail1 = json.dumps({"items": [{"id": "1", "points": 0}, {"id": "2", "points": 1}]})
            from harness import gemini
            with mock.patch.object(api, "call", return_value=(full, {"stop_reason": "end_turn"})), \
                 mock.patch.object(gemini, "run", return_value=(fail1, {"stop_reason": "end_turn"}, [])):
                fields, _ = run.grade_multi(task, "x", ["claude-opus-5-5", "gemini-4-argon"], False, None, "", "strict")
            self.assertFalse(fields["passed"])
            self.assertEqual(fields["score"], 1.0)

    def test_failed_secondary_is_retried_alone(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            full = json.dumps({"items": [{"id": "1", "points": 2}, {"id": "2", "points": 1}]})
            from harness import gemini
            with mock.patch.object(api, "call", return_value=(full, {"stop_reason": "end_turn"})) as c, \
                 mock.patch.object(gemini, "run", return_value=("no json", {"stop_reason": "end_turn"}, [])):
                fields, _ = run.grade_multi(task, "x", ["claude-opus-5-5", "gemini-4-argon"], False, None, "")
            self.assertTrue(fields["secondary_grade_error"])
            self.assertTrue(fields["passed"])  # the primary decides
            with mock.patch.object(api, "call", return_value=(full, {"stop_reason": "end_turn"})) as c2, \
                 mock.patch.object(gemini, "run", return_value=(full, {"stop_reason": "end_turn"}, [])):
                fields2, _ = run.grade_multi(task, "x", ["claude-opus-5-5", "gemini-4-argon"], False, None, "",
                                             prior=fields["grades"])
            self.assertEqual(c2.call_count, 0)  # the primary's grade is kept, not paid for again
            self.assertFalse(fields2["secondary_grade_error"])

    def test_failed_primary_is_a_grade_error(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            with mock.patch.object(api, "call", return_value=("no json", {"stop_reason": "end_turn"})):
                with self.assertRaises(run.GradeError):
                    run.grade_multi(task, "x", ["claude-opus-5-5"], False, None, "")


class Adjudication(unittest.TestCase):
    def test_expert_call_overrides_item_and_recomputes_pass(self):
        row = {"task": "t", "model": "m", "trial": 0, "passed": True, "score": 3.0, "pass_score": 3, "checks": [],
               "rubric": [{"id": "1", "points": 2.0, "max": 2, "required": True, "verdict": "pass"},
                          {"id": "2", "points": 1.0, "max": 1, "required": False, "verdict": "pass"}]}
        out = run.apply_adjudications([row], [{"task": "t", "model": "m", "trial": 1, "item": "2", "points": 0, "note": "wrong"}])
        self.assertFalse(out[0]["passed"])
        self.assertEqual(out[0]["score"], 2.0)
        self.assertTrue(row["passed"])  # the stored grader result is not changed


class Estimate(unittest.TestCase):
    def test_estimate_by_provider(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            a = mock.Mock(judge_tools=False, est_output=40000, est_output_low=12000)
            est = run.estimate_cost([task], {"claude-haiku-5-5": 2, "claude-sonnet-5-5": 1, "gemini-4-argon": 2},
                                    ["claude-opus-5-5", "gemini-4-argon"], a)
            self.assertGreater(est["high"]["anthropic"], est["low"]["anthropic"])
            self.assertGreater(est["high"]["google"], 0)
            self.assertIn("claude-opus-5-5", est["by_model"])


class ReviewFixes(unittest.TestCase):
    def test_verdict_and_points_parsing(self):
        self.assertEqual(run._verdict(" PASS "), "pass")
        self.assertEqual(run._verdict("Fail"), "fail")
        self.assertEqual(run._points("2/2", 2), 2.0)
        self.assertEqual(run._points(5, 2), 2.0)
        with self.assertRaises(run.GradeError):
            run._points("full marks", 2)
        with self.assertRaises(run.GradeError):
            run._points(None, 2)

    def test_primary_failure_keeps_secondary_grade(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            full = json.dumps({"items": [{"id": "1", "points": 2}, {"id": "2", "points": 1}]})
            from harness import gemini
            with mock.patch.object(api, "call", return_value=("no json", {"stop_reason": "end_turn"})), \
                 mock.patch.object(gemini, "run", return_value=(full, {"stop_reason": "end_turn"}, [])):
                with self.assertRaises(run.GradeError) as cm:
                    run.grade_multi(task, "x", ["claude-opus-5-5", "gemini-4-argon"], False, None, "")
            self.assertIn("gemini-4-argon", cm.exception.grades)
            self.assertFalse(cm.exception.grades["gemini-4-argon"].get("error"))

    def test_legacy_row_primary_not_paid_again(self):
        with tempfile.TemporaryDirectory() as d:
            task = key_task(d)
            row = {"task": "t", "model": "m", "trial": 0, "passed": True, "score": 3.0,
                   "rubric": [{"id": "1", "points": 2.0, "max": 2, "required": True, "verdict": "pass"}]}
            prior = run.legacy_grades(row, "claude-opus-5-5")
            full = json.dumps({"items": [{"id": "1", "points": 2}, {"id": "2", "points": 1}]})
            from harness import gemini
            with mock.patch.object(api, "call") as c, \
                 mock.patch.object(gemini, "run", return_value=(full, {"stop_reason": "end_turn"}, [])) as g:
                fields, _ = run.grade_multi(task, "x", ["claude-opus-5-5", "gemini-4-argon"], False, None, "", prior=prior)
            self.assertEqual(c.call_count, 0)
            self.assertEqual(g.call_count, 1)
            self.assertTrue(fields["passed"])

    def test_no_answer_counts_as_fail_for_second_grader(self):
        rows = [{"task": "t", "model": "m", "trial": 0, "no_answer": "cut off", "passed": False, "score": None},
                {"task": "t", "model": "m", "trial": 1, "passed": True, "score": 1.0,
                 "grades": {"a": {"passed": True, "score": 1.0, "rubric": []}, "b": {"passed": True, "score": 1.0, "rubric": []}}}]
        v = run._view(rows, "b")
        self.assertEqual(run.summarise(v)[("t", "m")], {"n": 2, "c": 1})

    def test_unfilled_adjudication_is_ignored(self):
        row = {"task": "t", "model": "m", "trial": 0, "passed": True, "score": 2.0, "pass_score": 2, "checks": [],
               "rubric": [{"id": "1", "points": 2.0, "max": 2, "required": False, "verdict": "pass"}]}
        adj = [{"task": "t", "model": "m", "trial": 1, "item": "1", "points": None, "verdict": None, "note": ""}]
        self.assertTrue(run.apply_adjudications([row], adj)[0]["passed"])
        self.assertEqual(run.unmatched_adjudications([row], [{"task": "t", "model": "m", "trial": 1, "item": "9", "points": 1}])[0]["item"], "9")

    def test_compressed_pdf_page_count(self):
        import zlib
        body = b"<< /Type /Pages /Kids [] /Count 40 >>"
        stream = zlib.compress(body)
        pdf = b"%PDF-1.5\n1 0 obj\n<< /Type /ObjStm /Filter /FlateDecode >>\nstream\n" + stream + b"\nendstream\nendobj\n"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf)
        try:
            self.assertEqual(run._pdf_pages(f.name), 40)
        finally:
            os.unlink(f.name)

    def test_results_last_line_wins(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "results.jsonl")
            with open(p, "w") as f:
                f.write(json.dumps({"task": "t", "model": "m", "trial": 0, "passed": False}) + "\n")
                f.write(json.dumps({"task": "t", "model": "m", "trial": 0, "passed": True}) + "\n")
            rows = run.read_results(p)
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["passed"])

    def test_resume_meter_starts_from_earlier_spend(self):
        api.reset_meter()
        api.set_budget(1.0, "anthropic")
        api.add_spend("anthropic", 1.5)
        with self.assertRaises(api.BudgetExceeded):
            api.check_budget("anthropic")
        api.reset_meter()


def test_check_accepts_listed_alternative():
    from harness.run import check_one
    c = {"field": "x", "type": "number", "expected": 14.26, "tol_abs": 0.25, "also": [{"expected": 19.0, "tol_abs": 0.3}]}
    assert check_one(c, {"x": 14.3})[0]
    assert check_one(c, {"x": 19.1})[0]
    assert not check_one(c, {"x": 17.0})[0]
    ch = {"field": "a", "type": "choice", "expected": "revise and resubmit", "also": [{"expected": "rejected"}]}
    assert check_one(ch, {"a": "Rejected"})[0]
    assert not check_one(ch, {"a": "approve"})[0]


def test_item_ids_written_as_the_grader_may_write_them():
    from harness.run import _item_id
    assert [_item_id(x) for x in ["1", 1, "item 1", "Item 5a", "#3", "1.", "item_2"]] == ["1", "1", "1", "5a", "3", "1", "2"]
