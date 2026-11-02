"""Gemini models under test, through Vertex AI (Google Cloud's Agent Platform), standard library only.

The grader stays Claude, so every model's answer is scored the same way. Gemini gets the same prompt, files and
system prompt as Claude; tasks with code_execution get Gemini's own Python sandbox (it runs server side, inside one
request), and data files are attached so code can load them.

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


def is_gemini(model):
    return model.startswith("gemini")


def _key():
    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise api.APIError("GOOGLE_API_KEY is not set. Create an API key in Google Cloud (Agent Platform > Authenticate) "
                           "and export it in your own shell; never commit it.")
    return key


def endpoint(model):
    """With GOOGLE_CLOUD_PROJECT set: the project's endpoint in GOOGLE_CLOUD_LOCATION (default global), which newer
    models such as gemini-4-argon need (without a project, API-key requests resolve to us-central1).
    Without it: the publisher URL Google documents for express-mode API keys."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    loc = os.environ.get("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
    host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
    path = (f"projects/{project}/locations/{loc}/publishers/google/models/{model}" if project
            else f"publishers/google/models/{model}")
    return f"https://{host}/v1/{path}:streamGenerateContent?alt=sse"


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
                text = f"(File {name} is attached for code execution; also shown below.)"
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
    if effort:
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": {"xhigh": "high", "max": "high"}.get(effort, effort)}
    return body


STOP = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens"}


def assemble(lines):
    """SSE stream of GenerateContentResponse chunks -> (text, usage, trace). Raises StreamCut if no finishReason."""
    text, trace, usage, finish = [], [], {}, None
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:].strip())
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
    if not finish:
        raise api.StreamCut("stream ended without finishReason")
    cached = usage.get("cachedContentTokenCount", 0) or 0
    u = {"input_tokens": (usage.get("promptTokenCount", 0) or 0) - cached + (usage.get("toolUsePromptTokenCount", 0) or 0),
         "cache_read_input_tokens": cached,
         "output_tokens": (usage.get("candidatesTokenCount", 0) or 0) + (usage.get("thoughtsTokenCount", 0) or 0),
         "stop_reason": STOP.get(finish, finish.lower())}
    return "".join(text), u, trace


def run(model, content, system=None, code_execution=False, max_tokens=MAX_OUT, effort=None):
    """One Gemini trial. Returns (text, usage in the harness's Claude-style keys, trace of code runs)."""
    data = json.dumps(body_for(content, system, code_execution, max_tokens, effort)).encode()
    headers = {"x-goog-api-key": _key(), "content-type": "application/json"}
    for attempt in range(api.TRIES):
        req = urllib.request.Request(endpoint(model), data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                text, usage, trace = assemble(r)
            api._charge(model, usage)
            return text, usage, trace
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code in RETRY_CODES and attempt < api.TRIES - 1:
                api._wait(attempt, e.headers)
                continue
            hint = (" (check the API key and that the Agent Platform API is enabled)"
                    if e.code in (401, 403) else " (check the model id in Model Garden, and set GOOGLE_CLOUD_PROJECT so the global endpoint is used)" if e.code == 404 else "")
            raise api.APIError(f"Gemini HTTP {e.code}: {raw[:400]}{hint}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError) as e:
            if attempt < api.TRIES - 1:
                api._wait(attempt)
                continue
            raise api.APIError(f"could not reach Vertex AI: {getattr(e, 'reason', e)}")
    raise api.APIError("gave up after repeated retries")
