"""Gemini through Vertex AI (Google Cloud's Agent Platform), standard library only: as a model under test and as
a second grader.

Gemini gets the same prompt, files and system prompt as Claude; tasks with code_execution get Gemini's own Python
sandbox (it runs server side, inside one request), and data files are attached so code can load them. As a grader it
gets the same grading prompt as the Claude grader; the equipped grader gets code execution and the task files (the
local code library is a Claude client tool and is not offered to Gemini). Gemini usage is metered and budgeted on
the Google account, separately from Claude.

Auth: export GOOGLE_API_KEY (an Agent Platform API key; usage is billed to the key's project) and GOOGLE_CLOUD_PROJECT
(the project id, so requests go to its global endpoint). Never commit the key.
The key goes in a request header, never in the URL.
"""
import base64
import json
import os
import socket
import ssl
import urllib.error
import urllib.request

from harness import api

RETRY_CODES = (429, 500, 502, 503, 504)
MAX_OUT = 65536  # Gemini's synchronous output limit
CUT_RETRIES = 2  # retries after a timeout or a cut stream (rate limits and 5xx keep api.TRIES)
LOOP_RUNS = 20  # a cut stream with at least this many code runs and no answer is not retried


TRACE_DIR = None  # set by the run: every Gemini request under test and every event it streams back is written here


def _redact(body):
    """The request as sent, with attached file bytes replaced by their size (the key is in a header, never here)."""
    b = json.loads(json.dumps(body))
    for c in b.get("contents", []):
        for p in c.get("parts", []):
            if "inlineData" in p:
                p["inlineData"] = {"mimeType": p["inlineData"].get("mimeType"),
                                   "data": f"<{len(p['inlineData'].get('data', ''))} base64 chars>"}
    return b


def _tracer(tag):
    if not (TRACE_DIR and tag):
        return None
    os.makedirs(TRACE_DIR, exist_ok=True)
    path = os.path.join(TRACE_DIR, "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in tag) + ".jsonl")

    def write(rec):
        import time
        rec = {"t": round(time.time(), 2), **rec}
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    return write


def _note(model, attempt, why):
    """Say why a request is retried, so a long silence in the run log has a visible cause."""
    import sys
    print(f"  [{model}] retry {attempt + 1}/{api.TRIES - 1}: {why}", file=sys.stderr, flush=True)


def is_gemini(model):
    return model.startswith("gemini")


def _key():
    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise api.APIError("GOOGLE_API_KEY is not set. Create an API key in Google Cloud (Agent Platform > Authenticate) "
                           "and export it in your own shell; never commit it.")
    return key


def endpoint(model, stream=True):
    """With GOOGLE_CLOUD_PROJECT set: the project's endpoint in GOOGLE_CLOUD_LOCATION (default global), which newer
    models such as gemini-4-argon need (without a project, API-key requests resolve to us-central1).
    Without it: the publisher URL Google documents for express-mode API keys."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    loc = os.environ.get("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
    host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
    path = (f"projects/{project}/locations/{loc}/publishers/google/models/{model}" if project
            else f"publishers/google/models/{model}")
    return f"https://{host}/v1/{path}:" + ("streamGenerateContent?alt=sse" if stream else "generateContent")


DATA_MIME = {".csv": "text/csv", ".txt": "text/plain", ".json": "application/json"}


def to_parts(content, code_execution):
    """Claude content blocks -> Gemini parts. Same files and prompt; cache markers dropped."""
    parts = []
    for b in content:
        t = b.get("type")
        if t == "container_upload":
            continue  # Claude-only sandbox upload; the file itself follows as a text block
        if t == "text":
            text = b["text"]
            if text.startswith("(File ") and text.endswith("is in the sandbox; also shown below.)"):
                name = text[len("(File "):-len(" is in the sandbox; also shown below.)")]
                # Gemini's sandbox does not keep the file name: say so, or the model keeps opening a path that is
                # not there until Vertex ends the request (a01r3 looped this way, 15 to 23 code runs, no answer).
                text = (f"(File {name} is shown below and attached as data. In the code sandbox it does not have this "
                        f"file name: list the working directory to find it, or copy the values you need from below.)")
            parts.append({"text": text})
            # a data file shown inline: also attach it, so Gemini's sandbox can load it with code
            if code_execution and text.startswith('<file name="'):
                name = text[len('<file name="'):text.index('"', len('<file name="'))]
                mime = DATA_MIME.get(os.path.splitext(name)[1].lower())
                if mime:
                    body = text.split(">", 1)[1].rsplit("</file>", 1)[0].strip("\n")
                    parts.append({"inlineData": {"mimeType": mime, "data": base64.b64encode(body.encode()).decode()}})
        elif t in ("document", "image"):
            src = b.get("source", {})
            if src.get("type") == "base64":
                parts.append({"inlineData": {"mimeType": src["media_type"], "data": src["data"]}})
    return parts


def body_for(content, system=None, code_execution=False, max_tokens=MAX_OUT, effort=None):
    body = {"contents": [{"role": "user", "parts": to_parts(content, code_execution)}],
            "generationConfig": {"maxOutputTokens": min(int(max_tokens), MAX_OUT)}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if code_execution:
        body["tools"] = [{"codeExecution": {}}]
    # Stream thought summaries: without them a long think sends nothing for minutes, the read times out and the
    # request is retried from the start (each attempt billed). The summaries are skipped when the answer is assembled.
    thinking = {"includeThoughts": True}
    if effort:
        thinking["thinkingLevel"] = {"xhigh": "high", "max": "high"}.get(effort, effort)
    body["generationConfig"]["thinkingConfig"] = thinking
    return body


STOP = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}


def assemble(lines, sink=None):
    """SSE stream of GenerateContentResponse chunks -> (text, usage, trace). Raises StreamCut if no finishReason."""
    text, trace, usage, finish = [], [], {}, None
    events, last_keys, feedback = 0, [], None
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:].strip())
        events += 1
        if sink:
            sink({"kind": "event", "data": ev})
        last_keys = sorted(ev)
        feedback = ev.get("promptFeedback") or feedback
        if "error" in ev:
            err = ev["error"]
            if err.get("code") in RETRY_CODES or err.get("status") in ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL"):
                raise api.StreamCut(f"stream error: {err}")
            raise api.APIError(f"stream error: {err}")
        for c in ev.get("candidates", [])[:1]:
            for p in (c.get("content") or {}).get("parts", []):
                if p.get("thought"):
                    continue
                if "text" in p:
                    text.append(p["text"])
                elif "executableCode" in p:
                    trace.append({"tool": "code_execution", "input": p["executableCode"].get("code", "")[:2000]})
            finish = c.get("finishReason") or finish
        if ev.get("usageMetadata"):
            usage = ev["usageMetadata"]
    if not finish and feedback and feedback.get("blockReason"):  # the prompt itself was refused: retrying cannot help
        raise api.APIError(f"prompt blocked: {feedback}")
    if not finish:
        # Vertex sometimes closes a 200 stream without a finishReason. The answer may be whole or cut, so the request
        # is retried; what arrived is kept on the error in case every retry fails the same way.
        last_code = (trace[-1]["input"][:160].replace("\n", " | ") if trace else "")
        cut = api.StreamCut(f"stream ended without finishReason ({events} events, {sum(map(len, text))} chars of "
                            f"answer, {len(trace)} code runs; last code: {last_code})")
        cut.partial = ("".join(text), usage, trace)
        raise cut
    cached = usage.get("cachedContentTokenCount", 0) or 0
    u = {"input_tokens": (usage.get("promptTokenCount", 0) or 0) - cached + (usage.get("toolUsePromptTokenCount", 0) or 0),
         "cache_read_input_tokens": cached,
         "output_tokens": (usage.get("candidatesTokenCount", 0) or 0) + (usage.get("thoughtsTokenCount", 0) or 0),
         "stop_reason": STOP.get(finish, finish.lower())}
    return "".join(text), u, trace


def run(model, content, system=None, code_execution=False, max_tokens=MAX_OUT, effort=None, tag=None):
    """One Gemini trial. Returns (text, usage in the harness's Claude-style keys, trace of code runs).
    With TRACE_DIR set and a tag, the request and every streamed event go to TRACE_DIR/<tag>.jsonl."""
    body = body_for(content, system, code_execution, max_tokens, effort)
    data = json.dumps(body).encode()
    log = _tracer(tag)
    if log:
        log({"kind": "request", "model": model, "body": _redact(body)})
    headers = {"x-goog-api-key": _key(), "content-type": "application/json"}
    cuts = 0  # timeouts and cut streams: each one may have been billed for a long think, so retry them less
    partial = None  # the longest answer that arrived without a finishReason
    stream = True  # after a cut stream, ask for the whole response in one piece instead
    for attempt in range(api.TRIES):
        req = urllib.request.Request(endpoint(model, stream), data=data, headers=headers, method="POST")
        if log:
            log({"kind": "attempt", "n": attempt + 1, "stream": stream})
        try:
            with urllib.request.urlopen(req, timeout=600 if stream else 1800) as r:
                if stream:
                    text, usage, trace = assemble(r, sink=log)
                else:
                    text, usage, trace = assemble([b"data: " + json.dumps(json.loads(r.read())).encode()], sink=log)
            if log:
                log({"kind": "done", "chars": len(text), "code_runs": len(trace), "usage": usage})
            api._charge(model, usage)
            return text, usage, trace
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if log:
                log({"kind": "error", "http": e.code, "body": raw[:2000]})
            if e.code in RETRY_CODES and attempt < api.TRIES - 1:
                _note(model, attempt, f"HTTP {e.code}")
                api._wait(attempt, e.headers)
                continue
            hint = (" (check the API key and that the Agent Platform API is enabled)"
                    if e.code in (401, 403) else " (check the model id in Model Garden, and set GOOGLE_CLOUD_PROJECT so the global endpoint is used)" if e.code == 404 else "")
            raise api.APIError(f"Gemini HTTP {e.code}: {raw[:400]}{hint}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError) as e:
            cuts += 1
            if log:
                log({"kind": "error", "type": type(e).__name__, "message": str(getattr(e, "reason", e))[:2000]})
            got = getattr(e, "partial", None)
            if got and (got[0].strip() or got[2]) and (not partial or (len(got[0]), len(got[2])) > (len(partial[0]), len(partial[2]))):
                partial = got
            if isinstance(e, api.StreamCut) and stream:
                stream = False
            # Vertex ends a request after about 23 code runs. A cut with that many runs and no answer is the model
            # looping on code, not the network: the same request ends the same way, so do not pay for it again.
            looped = bool(got) and not got[0].strip() and len(got[2]) >= LOOP_RUNS
            if attempt < api.TRIES - 1 and cuts <= CUT_RETRIES and not looped:
                _note(model, attempt, f"{type(e).__name__}: {str(getattr(e, 'reason', e))[:300]}"
                      + ("" if stream else "; next try without streaming"))
                api._wait(attempt)
                continue
            if partial:  # every try ended without a finishReason: keep the longest answer, marked for the report
                text, usage, trace = partial
                cached = usage.get("cachedContentTokenCount", 0) or 0
                u = {"input_tokens": (usage.get("promptTokenCount", 0) or 0) - cached
                     + (usage.get("toolUsePromptTokenCount", 0) or 0),
                     "cache_read_input_tokens": cached,
                     "output_tokens": (usage.get("candidatesTokenCount", 0) or 0) + (usage.get("thoughtsTokenCount", 0) or 0),
                     "stop_reason": "no_finish_reason" if text.strip() else "code_loop_cut"}
                _note(model, attempt, f"kept an answer of {len(text)} chars that arrived without a finishReason" if text.strip()
                      else f"every try ran code ({len(trace)} runs) and ended without a final answer")
                api._charge(model, u)
                return text, u, trace
            raise api.APIError(f"could not reach Vertex AI: {getattr(e, 'reason', e)}")
    raise api.APIError("gave up after repeated retries")


def _post(model, body, log=None):
    """One non-streaming generateContent call with the usual retries. Returns the parsed response."""
    data = json.dumps(body).encode()
    headers = {"x-goog-api-key": _key(), "content-type": "application/json"}
    cuts = 0
    for attempt in range(api.TRIES):
        req = urllib.request.Request(endpoint(model, stream=False), data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if log:
                log({"kind": "error", "http": e.code, "body": raw[:2000]})
            if e.code in RETRY_CODES and attempt < api.TRIES - 1:
                _note(model, attempt, f"HTTP {e.code}")
                api._wait(attempt, e.headers)
                continue
            raise api.APIError(f"Gemini HTTP {e.code}: {raw[:400]}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError) as e:
            cuts += 1
            if log:
                log({"kind": "error", "type": type(e).__name__, "message": str(getattr(e, "reason", e))[:2000]})
            if attempt < api.TRIES - 1 and cuts <= CUT_RETRIES:
                _note(model, attempt, f"{type(e).__name__}: {str(getattr(e, 'reason', e))[:200]}")
                api._wait(attempt)
                continue
            raise api.APIError(f"could not reach Vertex AI: {getattr(e, 'reason', e)}")
    raise api.APIError("gave up after repeated retries")


def run_tools(model, content, executor, system=None, max_tokens=MAX_OUT, effort=None, max_turns=25, tag=None,
              extra_tools=()):
    """Gemini under test with the harness's own tool (the local sandbox's run_python), through function calling:
    the same tool, files and turn limit as Claude gets with --sandbox local. Returns (text, usage, trace).
    Each turn is one generateContent call; the model's content goes back unchanged (thought signatures included)."""
    from harness import sandbox
    contents = [{"role": "user", "parts": to_parts(content, code_execution=False)}]
    thinking = {"includeThoughts": True}
    if effort:
        thinking["thinkingLevel"] = {"xhigh": "high", "max": "high"}.get(effort, effort)
    body = {"generationConfig": {"maxOutputTokens": min(int(max_tokens), MAX_OUT), "thinkingConfig": thinking},
            "tools": [{"functionDeclarations": [sandbox.GEMINI_DECL] + [
                {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}
                if t["input_schema"].get("properties") else {"name": t["name"], "description": t["description"]}
                for t in extra_tools]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    log = _tracer(tag)
    if log:
        log({"kind": "request", "model": model, "body": _redact(dict(body, contents=contents))})
    total = {"input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 0}
    trace = []
    for turn in range(max_turns):
        if log:
            log({"kind": "attempt", "n": turn + 1, "stream": False, "turn": True})
        res = _post(model, dict(body, contents=contents), log)
        if log:
            log({"kind": "event", "data": res})
        meta = res.get("usageMetadata") or {}
        cached = meta.get("cachedContentTokenCount", 0) or 0
        u = {"input_tokens": (meta.get("promptTokenCount", 0) or 0) - cached
             + (meta.get("toolUsePromptTokenCount", 0) or 0),
             "cache_read_input_tokens": cached,
             "output_tokens": (meta.get("candidatesTokenCount", 0) or 0) + (meta.get("thoughtsTokenCount", 0) or 0)}
        api._charge(model, u)
        for k in total:
            total[k] += u[k]
        cands = res.get("candidates") or []
        if not cands:
            fb = res.get("promptFeedback")
            raise api.APIError(f"no candidates (promptFeedback {fb})" if fb else "no candidates in the response")
        cand = cands[0]
        msg = cand.get("content") or {"parts": []}
        msg.setdefault("role", "model")
        msg.setdefault("parts", [])
        contents.append(msg)
        calls = [p["functionCall"] for p in msg["parts"] if "functionCall" in p]
        if calls:
            replies = []
            for c in calls:
                args = c.get("args") or {}
                trace.append({"tool": c.get("name"), "input": str(args.get("code", args))[:2000]})
                out = executor(c.get("name"), args)
                fr = {"name": c.get("name"), "response": {"output": out if out is not None
                                                          else f"error: unknown tool {c.get('name')}"}}
                if c.get("id"):
                    fr["id"] = c["id"]
                replies.append({"functionResponse": fr})
            contents.append({"role": "user", "parts": replies})
            continue
        text = "".join(p.get("text", "") for p in msg["parts"] if "text" in p and not p.get("thought"))
        finish = cand.get("finishReason") or "NO_FINISH_REASON"
        total["stop_reason"] = STOP.get(finish, finish.lower())
        if log:
            log({"kind": "done", "chars": len(text), "code_runs": len(trace), "usage": total})
        return text, total, trace
    total["stop_reason"] = "max_turns"
    if log:
        log({"kind": "done", "chars": 0, "code_runs": len(trace), "usage": total})
    return "", total, trace + [{"tool": "harness", "input": f"stopped after {max_turns} turns"}]
