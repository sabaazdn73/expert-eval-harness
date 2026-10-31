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


def call(model, content, system=None, max_tokens=4000, temperature=1.0):
    """One Messages API call. Returns (text, usage dict)."""
    if model.startswith("mock"):
        return mock_call(model, content)
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
            "messages": [{"role": "user", "content": content}]}
    if system:
        body["system"] = system
    headers = {"x-api-key": _key(), "anthropic-version": API_VERSION, "content-type": "application/json"}
    for attempt in range(5):
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                res = json.loads(r.read())
            text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
            return text, res.get("usage", {})
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
