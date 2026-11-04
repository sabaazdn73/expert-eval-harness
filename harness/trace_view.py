"""Read a Gemini trace written during a run, as a timeline: what was sent, what the model thought, the code it ran
and what that code printed, and the answer.

    python3 -m harness.trace_view runs/main/traces/<task>__<model>__trial1.jsonl
    python3 -m harness.trace_view runs/main/traces            (one line per trace file)
"""
import json
import os
import sys


def _short(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 3] + "..."


def show(path, width=300):
    t0 = None
    for line in open(path):
        r = json.loads(line)
        t0 = t0 or r.get("t", 0)
        at = f"{r.get('t', 0) - t0:7.1f}s"
        k = r["kind"]
        if k == "request":
            parts = [p for c in r["body"].get("contents", []) for p in c.get("parts", [])]
            texts = sum(len(p.get("text", "")) for p in parts)
            files = [p["inlineData"]["mimeType"] for p in parts if "inlineData" in p]
            cfg = r["body"].get("generationConfig", {})
            print(f"{at} REQUEST {r.get('model')}: {texts} chars of text, attachments {files}, "
                  f"tools {[list(x) for x in r['body'].get('tools', [])]}, config {cfg}")
        elif k == "attempt":
            print(f"{at} ATTEMPT {r['n']} ({'streaming' if r['stream'] else 'one piece'})")
        elif k == "event":
            for c in r["data"].get("candidates", [])[:1]:
                for p in (c.get("content") or {}).get("parts", []):
                    if p.get("thought") and "text" in p:
                        print(f"{at}   thought: {_short(p['text'], width)}")
                    elif "executableCode" in p:
                        print(f"{at}   CODE: {_short(p['executableCode'].get('code', ''), width)}")
                    elif "codeExecutionResult" in p:
                        res = p["codeExecutionResult"]
                        print(f"{at}   RESULT [{res.get('outcome', '')}]: {_short(res.get('output', ''), width)}")
                    elif "text" in p:
                        print(f"{at}   answer: {_short(p['text'], width)}")
                    elif "inlineData" in p:
                        print(f"{at}   (model returned {p['inlineData'].get('mimeType')})")
                if c.get("finishReason"):
                    print(f"{at}   finishReason {c['finishReason']}")
        elif k == "error":
            print(f"{at} ERROR {r.get('http') or r.get('type')}: {_short(r.get('message') or r.get('body', ''), width)}")
        elif k == "done":
            print(f"{at} DONE: {r['chars']} chars of answer, {r['code_runs']} code runs")


def summary(folder):
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".jsonl"):
            continue
        attempts = codes = errors = 0
        done = False
        for line in open(os.path.join(folder, name)):
            r = json.loads(line)
            attempts += r["kind"] == "attempt"
            errors += r["kind"] == "error"
            done = done or r["kind"] == "done"
            if r["kind"] == "event":
                for c in r["data"].get("candidates", [])[:1]:
                    codes += sum("executableCode" in p for p in (c.get("content") or {}).get("parts", []))
        print(f"{name:70s} attempts {attempts}  code runs {codes}  errors {errors}  {'answered' if done else 'NO ANSWER'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    (summary if os.path.isdir(sys.argv[1]) else show)(sys.argv[1])
