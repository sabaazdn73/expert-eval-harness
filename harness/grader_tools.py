"""Equipped grader: the judge checks a response with tools instead of reading it only.

- code_execution (server tool, Anthropic sandbox): re-run the response's arithmetic.
- code_ref_search / code_ref_page (client tools, run locally): read the standards in the local code-ref
  library, so the library never leaves this machine except as the short excerpts the grader asks for.
- The task's input files are attached, so the grader can check figures against the source documents.

The grader also reports possible problems in the key itself (flags for human review).
"""
import json
import os
import re

from harness import api

CODE_EXEC = {"type": "code_execution_20250825", "name": "code_execution"}
CLIENT_TOOLS = [
    {"name": "code_ref_search",
     "description": "Full-text search of the local library of building codes and standards (ACI 318, ASCE 7, IBC and others). "
                    "Returns short excerpts with standard, edition, status and PDF page. Use it to confirm a clause the response cites, "
                    "or the edition that governs.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "words or a clause number, e.g. '18.14.5.1 vuv' or 'Type 1a torsional irregularity'"},
         "family": {"type": "string", "description": "optional: limit to a standard family, e.g. 'ACI 318' or 'ASCE 7'"},
         "include_superseded": {"type": "boolean", "description": "also search superseded editions (default false)"}},
         "required": ["query"]}},
    {"name": "code_ref_page",
     "description": "Read the text of one PDF page of a source in the local code library (source id and pdf_page from code_ref_search).",
     "input_schema": {"type": "object", "properties": {"source": {"type": "string"}, "pdf_page": {"type": "integer"}},
                      "required": ["source", "pdf_page"]}},
]

GUIDE = (
    "You have tools. Use them to verify, not to re-solve the task from scratch:\n"
    "- code_execution: recompute every number an item depends on (ratios, limits, drifts, forces) from the response's own inputs "
    "and from the source documents, and compare with the key's tolerances.\n"
    "- code_ref_search / code_ref_page: check clause numbers, wording and editions the response relies on.\n"
    "- The task's input files are attached: check the figures the response takes from them.\n"
    "Score from the key. If you find that the key itself looks wrong, ambiguous, or misses a valid alternative reading the response uses, "
    "still score by the key, and report it in key_flags for a human to review.\n"
)


def _client_tool(name, args, lib):
    if lib is None:
        return "No local code library is configured for this run."
    if name == "code_ref_search":
        hits = lib.search(args.get("query", ""), args.get("family"), not args.get("include_superseded"), limit=5)
        return json.dumps(hits) if hits else "no matches"
    if name == "code_ref_page":
        row = lib.con.execute("SELECT text FROM pages WHERE source = ? AND page = ?",
                              (args.get("source"), int(args.get("pdf_page", 0)))).fetchone()
        return (row[0][:6000] if row else "page not found")
    return f"unknown tool {name}"


def run_equipped(model, content, lib, max_tokens=64000, max_turns=40):
    """Run a grading conversation with tools until the model ends its turn. Returns (final_text, usage, trace)."""
    tools = [CODE_EXEC] + CLIENT_TOOLS
    messages = [{"role": "user", "content": content}]
    usage = {"input_tokens": 0, "output_tokens": 0}
    trace, container = [], None
    for _ in range(max_turns):
        body = {"model": model, "max_tokens": max_tokens, "tools": tools, "messages": messages}
        if container:
            body["container"] = container
        res = api.create(body)
        for k in usage:
            usage[k] += res.get("usage", {}).get(k, 0)
        container = (res.get("container") or {}).get("id") or container
        blocks = res.get("content", [])
        messages.append({"role": "assistant", "content": blocks})
        stop = res.get("stop_reason")
        for b in blocks:
            if b.get("type") in ("server_tool_use", "tool_use"):
                trace.append({"tool": b.get("name"), "input": b.get("input")})
        if stop == "tool_use":
            results = []
            for b in blocks:
                if b.get("type") == "tool_use":
                    out = _client_tool(b["name"], b.get("input", {}), lib)
                    results.append({"type": "tool_result", "tool_use_id": b["id"], "content": out})
            messages.append({"role": "user", "content": results})
            continue
        if stop == "pause_turn":
            continue
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return text, usage, trace
    return "", usage, trace + [{"tool": "harness", "input": "stopped after max_turns"}]
