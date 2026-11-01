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


if __name__ == "__main__":
    unittest.main()
