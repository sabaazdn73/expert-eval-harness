"""Minimal Claude Messages API client (standard library only), plus a mock model for offline tests."""
import base64
import json
import mimetypes
import os
import random
import socket
import ssl
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class APIError(RuntimeError):
    pass


RETRY_CODES = (429, 500, 502, 503, 504, 529)
TRIES = 8


def _wait(attempt, headers=None):
    ra = headers.get("retry-after") if headers else None
    try:
        delay = float(ra) if ra else 0
    except ValueError:
        delay = 0
    time.sleep(max(delay, min(120, 5 * 2 ** attempt)) + random.uniform(0, 3))


def _key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise APIError("ANTHROPIC_API_KEY is not set. Export it in your own shell; never commit it.")
    return key


def file_block(path):
    """Turn a task file into a content block: text inline, PDFs as documents, images as images."""
    mime = mimetypes.guess_type(path)[0] or "text/plain"
    name = os.path.basename(path)
    if mime == "application/pdf":
        data = base64.b64encode(open(path, "rb").read()).decode()
        return {"type": "document", "source": {"type": "base64", "media_type": mime, "data": data}, "title": name}
    if mime in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        data = base64.b64encode(open(path, "rb").read()).decode()
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}}
    text = open(path, encoding="utf-8").read()
    return {"type": "text", "text": f'<file name="{name}">\n{text}\n</file>'}


CACHE_1H = {"type": "ephemeral", "ttl": "1h"}


def with_cache_point(content, ttl=CACHE_1H):
    """Copy of content with a cache point on its last cacheable block, so the identical prefix
    (task files and prompt) is billed once per hour per model and read from the cache after that."""
    content = [dict(b) for b in content]
    for b in reversed(content):
        if b.get("type") in ("text", "document", "image"):
            b["cache_control"] = dict(ttl)
            break
    return content


def call(model, content, system=None, max_tokens=4000, temperature=None, effort=None, cache=True):
    """One streamed Messages API call with a single user message. Returns (text, usage dict with stop_reason).

    Thinking tokens count toward max_tokens on current models, so give a large max_tokens for hard tasks.
    temperature is sent only when given; newer models reject it, so it is dropped and retried.
    effort sets output_config.effort (low, medium, high, xhigh, max); None keeps the model's default."""
    if model.startswith("mock"):
        return mock_call(model, content)
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": with_cache_point(content) if cache else content}]}
    if temperature is not None:
        body["temperature"] = temperature
    if effort:
        body["output_config"] = {"effort": effort}
    if system:
        body["system"] = system
    res = create(body)
    text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
    return text, dict(res.get("usage", {}), stop_reason=res.get("stop_reason"))


_UPLOADS = None


def upload_file(path):
    """file_id for a local file, uploading it once: ids are kept in runs/.uploads.json by content hash,
    so the same file is not uploaded again on every run."""
    import hashlib, threading
    global _UPLOADS
    store = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs", ".uploads.json")
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if _UPLOADS is None:
        try:
            _UPLOADS = json.load(open(store))
        except (OSError, ValueError):
            _UPLOADS = {}
    if digest in _UPLOADS:
        return _UPLOADS[digest]
    fid = _upload(path)
    _UPLOADS[digest] = fid
    os.makedirs(os.path.dirname(store), exist_ok=True)
    json.dump(_UPLOADS, open(store, "w"), indent=1)
    return fid


def _upload(path):
    import uuid
    boundary = uuid.uuid4().hex
    name = os.path.basename(path)
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    headers = {"x-api-key": _key(), "anthropic-version": API_VERSION,
               "content-type": f"multipart/form-data; boundary={boundary}"}
    req = urllib.request.Request(API_URL.replace("/messages", "/files"), data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["id"]
    except urllib.error.HTTPError as e:
        raise APIError(f"file upload failed, HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")


class StreamCut(ConnectionError):
    """The stream ended before message_stop, or the API sent an overloaded/api_error event: retry the request."""


class BudgetExceeded(APIError):
    pass


# ---- cost meter (estimates, USD per million tokens; see the pricing page for the current figures) ----
PRICES = {  # model prefix: (input, output, cache-read multiplier)
    "claude-haiku-5-5": (0.10, 0.50, 0.10),
    "claude-sonnet-5-5": (2.0, 10.0, 0.05),
    "claude-opus-5-5": (4.0, 20.0, 0.05),
    "claude-fable-5-1": (10.0, 50.0, 0.025),
}
import threading as _threading
_METER = {"usd": 0.0, "budget": None, "by_model": {}}
_METER_LOCK = _threading.Lock()


def cost_of(model, u):
    p = next((v for k, v in PRICES.items() if model.startswith(k)), None)
    if not p:
        return 0.0
    inp, out, rd = p
    cc = u.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens")
    w5m = cc.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:  # no breakdown: price every write at the 1-hour rate (the higher one)
        w1h, w5m = u.get("cache_creation_input_tokens", 0) or 0, 0
    tok = ((u.get("input_tokens", 0) or 0) * inp + (u.get("output_tokens", 0) or 0) * out
           + (u.get("cache_read_input_tokens", 0) or 0) * inp * rd + (w1h or 0) * inp * 2 + (w5m or 0) * inp * 1.25)
    return tok / 1e6


def set_budget(usd):
    _METER["budget"] = usd


def spent():
    return _METER["usd"], dict(_METER["by_model"])


def _charge(model, usage):
    c = cost_of(model, usage)
    with _METER_LOCK:
        _METER["usd"] += c
        _METER["by_model"][model] = _METER["by_model"].get(model, 0.0) + c


def check_budget():
    b = _METER["budget"]
    if b is not None and _METER["usd"] >= b:
        raise BudgetExceeded(f"budget of ${b:.2f} reached (estimated spend ${_METER['usd']:.2f}); stopping new requests")


def _assemble(r):
    """Rebuild a full Messages response (content blocks, usage, stop reason, container) from an SSE stream.
    Raises StreamCut if the stream ends before message_stop or carries a retryable error event."""
    msg, blocks, partial, stopped = {}, {}, {}, False
    for raw in r:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        ev = json.loads(line[5:].strip())
        t = ev.get("type")
        if t == "message_start":
            msg = ev["message"]
        elif t == "content_block_start":
            blocks[ev["index"]] = dict(ev["content_block"])
        elif t == "content_block_delta":
            b, d = blocks[ev["index"]], ev["delta"]
            dt = d.get("type")
            if dt == "text_delta":
                b["text"] = b.get("text", "") + d["text"]
            elif dt == "thinking_delta":
                b["thinking"] = b.get("thinking", "") + d["thinking"]
            elif dt == "signature_delta":
                b["signature"] = d["signature"]
            elif dt == "input_json_delta":
                partial[ev["index"]] = partial.get(ev["index"], "") + d.get("partial_json", "")
            elif dt == "citations_delta":
                b.setdefault("citations", []).append(d.get("citation"))
        elif t == "content_block_stop":
            i = ev["index"]
            if i in partial:
                blocks[i]["input"] = json.loads(partial.pop(i) or "{}")
        elif t == "message_delta":
            d = ev.get("delta", {})
            if d.get("stop_reason"):
                msg["stop_reason"] = d["stop_reason"]
            if d.get("container"):
                msg["container"] = d["container"]
            u = msg.setdefault("usage", {})
            u.update({k: v for k, v in ev.get("usage", {}).items() if v is not None})
        elif t == "message_stop":
            stopped = True
        elif t == "error":
            err = ev.get("error") or {}
            if err.get("type") in ("overloaded_error", "api_error", "rate_limit_error"):
                raise StreamCut(f"stream error: {err}")
            raise APIError(f"stream error: {err}")
    if not stopped:
        raise StreamCut("stream ended before message_stop")
    msg["content"] = [blocks[i] for i in sorted(blocks)]
    return msg


def create(body):
    """One streamed Messages API request with a raw body. Returns the assembled response dict.

    Streamed so that long turns (thinking plus tool calls) do not hit HTTP read timeouts. Retries rate limits,
    overloads, dropped connections and cut streams. Every completed response is charged to the cost meter, and
    no new trial starts once the --budget is reached (checked by the runner, so a trial already under way finishes)."""
    headers = {"x-api-key": _key(), "anthropic-version": API_VERSION, "content-type": "application/json"}
    body = dict(body, stream=True)
    for attempt in range(TRIES):
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as r:  # timeout between chunks
                msg = _assemble(r)
            _charge(body["model"], msg.get("usage", {}))
            return msg
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code == 400 and "temperature" in raw and "temperature" in body:
                body.pop("temperature")
                continue
            if e.code in RETRY_CODES and attempt < TRIES - 1:
                _wait(attempt, e.headers)
                continue
            raise APIError(f"HTTP {e.code}: {raw[:400]}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError, OSError) as e:
            if attempt < TRIES - 1:
                _wait(attempt)
                continue
            raise APIError(f"could not reach the API: {getattr(e, 'reason', e)}")
    raise APIError("gave up after repeated retries")


def mock_call(model, content):
    """Offline stand-in. mock-good answers from the task's mock_answer, mock-bad returns nonsense."""
    prompt = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
    if "GRADER" in prompt:  # judge call
        verdict = "pass" if "MOCK_GOOD" in prompt else "fail"
        return json.dumps({"items": [{"id": "all", "verdict": verdict, "reason": "mock judge"}]}), {}
    marker = "<mock_answer>"
    if model == "mock-good" and marker in prompt:
        ans = prompt.split(marker, 1)[1].split("</mock_answer>", 1)[0]
        return "MOCK_GOOD reasoning.\n```json\n" + ans + "\n```", {"input_tokens": 0, "output_tokens": 0}
    return "MOCK_BAD.\n```json\n{}\n```", {"input_tokens": 0, "output_tokens": 0}
