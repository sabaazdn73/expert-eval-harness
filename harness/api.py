"""Minimal Claude Messages API client (standard library only), plus a mock model for offline tests."""
import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class APIError(RuntimeError):
    pass


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


def _stream(req):
    """Read a streamed Messages response (SSE). Returns (text, usage with stop_reason)."""
    text, usage, stop = [], {}, None
    with urllib.request.urlopen(req, timeout=600) as r:  # timeout applies between chunks, not to the whole answer
        for raw in r:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:].strip())
            t = ev.get("type")
            if t == "message_start":
                usage.update(ev["message"].get("usage", {}))
            elif t == "content_block_delta" and ev["delta"].get("type") == "text_delta":
                text.append(ev["delta"]["text"])
            elif t == "message_delta":
                stop = ev.get("delta", {}).get("stop_reason") or stop
                usage.update({k: v for k, v in ev.get("usage", {}).items() if v is not None})
            elif t == "error":
                raise APIError(f"stream error: {ev.get('error')}")
    return "".join(text), dict(usage, stop_reason=stop)


def call(model, content, system=None, max_tokens=4000, temperature=None, effort=None):
    """One streamed Messages API call. Returns (text, usage dict).

    Thinking tokens count toward max_tokens on current models, so give a large max_tokens for hard tasks.
    temperature is sent only when given; newer models reject it, so it is dropped and retried.
    effort sets output_config.effort (low, medium, high, xhigh, max); None keeps the model's default."""
    if model.startswith("mock"):
        return mock_call(model, content)
    body = {"model": model, "max_tokens": max_tokens, "stream": True,
            "messages": [{"role": "user", "content": content}]}
    if temperature is not None:
        body["temperature"] = temperature
    if effort:
        body["output_config"] = {"effort": effort}
    if system:
        body["system"] = system
    headers = {"x-api-key": _key(), "anthropic-version": API_VERSION, "content-type": "application/json"}
    for attempt in range(5):
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            return _stream(req)
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code == 400 and "temperature" in raw and "temperature" in body:
                body.pop("temperature")
                continue
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                time.sleep(int(e.headers.get("retry-after") or 2 ** (attempt + 2)))
                continue
            raise APIError(f"HTTP {e.code}: {raw[:400]}")
        except urllib.error.URLError as e:
            raise APIError(f"could not reach the API: {e.reason}")
    raise APIError("gave up after repeated retries")


def upload_file(path):
    """Upload a file with the Files API and return its file_id (used for container_upload blocks)."""
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


def create(body):
    """One non-streamed Messages API request with a raw body (used for tool loops). Returns the response dict."""
    headers = {"x-api-key": _key(), "anthropic-version": API_VERSION, "content-type": "application/json"}
    body = dict(body)
    for attempt in range(5):
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=1800) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                time.sleep(int(e.headers.get("retry-after") or 2 ** (attempt + 2)))
                continue
            raise APIError(f"HTTP {e.code}: {raw[:400]}")
        except urllib.error.URLError as e:
            raise APIError(f"could not reach the API: {e.reason}")
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
