"""Team mode: a structural review done by a team of agents that talk in one shared channel.

    python3 -m harness.run run --team --models claude-sonnet-5-5 --k 1 --sandbox local --tasks "/path/to/tasks/*"

Instead of one model answering the task, the same model works as a team, the way a design office splits a review:

1. Code basis. One agent reads the package for what lies outside any single member: where the project is, which
   building code the jurisdiction has adopted and so which editions of ACI 318 and ASCE 7 govern, the state or city
   amendments, and the design criteria. It posts this to the channel first, so no member is checked against the
   wrong edition (the trap behind most failures in the hackathon tasks).
2. Plan. A lead splits the review into parts, one per structural member or connection, so that every member and
   every provision the request needs is covered once.
3. Members. Each member agent checks its own part, with numbers, in the sandbox, against the code basis in the
   channel. When a decision depends on another part (a force, a dimension, a joint they share) it asks that agent
   in the channel with a line "ASK @agent: ...".
4. Answers. Agents answer the questions addressed to them; an answer can correct an earlier finding.
5. Check. A checking engineer reads the whole channel, makes sure every part and every item is covered and that the
   parts agree with each other, recomputes what it doubts, and writes the team's answer in the task's format. That
   answer is graded exactly like a single model's answer, so a team run compares one to one with a solo run.

Every agent sees the same task files, so the files are written to the prompt cache once and read from it by every
later call. The whole conversation is saved as JSON and as a chat-style HTML page (see render_html).
"""
import html
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from harness import api

CODE_BASIS_ID = "code-basis"
LEAD_ID = "lead"
CHECKER_ID = "checker"

CODE_BASIS_ROLE = """You are the code-basis engineer on a structural review team. The team works in one shared channel.
Before anyone checks a member, establish from the documents what lies outside any single member:
- where the project is, and which building code and edition that jurisdiction has adopted;
- which editions of the referenced standards follow from it (ACI 318, ASCE 7, others the package uses), and whether any
  document in the package cites a different edition than the one that governs;
- the state or city amendments that change a provision the review depends on;
- the design criteria the members are checked against (risk category, seismic design category, materials, loads).
Give the document and page for every item. Say plainly what the documents leave open. Do not review the members.
Your reply is your post to the channel: a short list, under 400 words."""

LEAD_ROLE = """You lead a structural review team. The code basis is already posted in the channel below.
Split the review into at most {n} parts, one per structural member or connection (or per group of identical members),
so that every member and every provision the request needs is covered once and nothing is checked twice. Give each
part an agent id (lower case, letters, digits and hyphens, e.g. "wall-w1-w3" or "dowels") and a scope: what to check,
in which documents, against which clauses. List the questions that involve two parts, so the agents know whom to ask.
Reply only with a fenced ```json block:
{{"agents": [{{"id": "...", "member": "...", "scope": "..."}}], "cross_checks": ["..."]}}"""

MEMBER_ROLE = """You are the {id} agent on a structural review team. You own one part of the review: {member}.
Scope: {scope}
Read the channel first and use the code basis posted there. Check your part's design and detailing against the
governing code edition and the local amendments, with numbers, and do the arithmetic in code. Check both the document
under review and the draft review for your part: say where each is right and where it is wrong.
When a decision depends on another part (a force, a dimension, a joint you share), ask that agent with a line of the form
ASK @agent-id: your question
The agents in the channel are: {roster}.
Do not write the final review. Your reply is your post to the channel, under 600 words: FINDINGS (each with the clause,
the numbers and a verdict), then any ASK lines."""

ANSWER_ROLE = """You are the {id} agent on the same review team. These questions were addressed to you in the channel:
{questions}
Answer each one with numbers, in a short post. If a question shows that one of your earlier findings is wrong, correct
it and say so. You may ask a further question with an ASK @agent-id: line. Your reply is your post, under 400 words."""

CHECKER_ROLE = """You are the checking engineer on the review team, and you sign the team's answer.
Read the whole channel below. Make sure that:
- every member and every item the request needs is covered;
- the parts agree with each other (shared forces, joints, dimensions) and with the code basis;
- the code edition and the local amendments used are the ones that govern.
Recompute any number you doubt. Where agents disagree, decide and say why. Then write the team's final answer to the
original request, complete and in the format it asks for. Do not mention the team or the channel in that answer."""

ASK_RE = re.compile(r"^\s*\**ASK\**\s+@([A-Za-z0-9_\-]+)\s*:?\s*(.+)$", re.M)
MSG_CAP = 8000  # characters of one post shown to the other agents (the full post is saved)


def call_count(max_agents, rounds):
    """Model calls in one team trial at most: code basis, lead, the members, one answer round per member, checker."""
    return 3 + max_agents * (1 + rounds)


def _parse_plan(text, max_agents):
    m = re.findall(r"```json\s*(\{.*?\})\s*```", text or "", flags=re.S) or re.findall(r"(\{.*\})", text or "", flags=re.S)
    plan = None
    for raw in reversed(m):
        try:
            plan = json.loads(raw)
            break
        except ValueError:
            continue
    agents, seen = [], {CODE_BASIS_ID, LEAD_ID, CHECKER_ID}
    for a in (plan or {}).get("agents") or []:
        aid = re.sub(r"[^a-z0-9\-]+", "-", str(a.get("id", "")).lower()).strip("-")[:40] or f"part-{len(agents) + 1}"
        while aid in seen:
            aid += "-2"
        seen.add(aid)
        agents.append({"id": aid, "member": str(a.get("member") or aid), "scope": str(a.get("scope") or "")})
        if len(agents) >= max_agents:
            break
    if not agents:  # an unreadable plan must not end the trial: one agent then reviews the whole package
        agents = [{"id": "reviewer", "member": "the whole package",
                   "scope": "every member, connection and provision the request needs"}]
    return agents, [str(c) for c in (plan or {}).get("cross_checks") or []]


def _split(task, content):
    """(files before the request, the request block, blocks after it). The request block carries the answer format."""
    for i, b in enumerate(content):
        if b.get("type") == "text" and b.get("text", "").startswith(task["prompt_text"]):
            return content[:i], b, content[i + 1:]
    return content[:-1], content[-1], []


def render_channel(channel, cap=MSG_CAP):
    if not channel:
        return "<channel>\n(no posts yet)\n</channel>"
    out = []
    for m in channel:
        t = m["text"] if len(m["text"]) <= cap else m["text"][:cap] + f"\n[... {len(m['text']) - cap} characters cut]"
        out.append(f"--- post {m['n']} · round {m['round']} · from @{m['from']}"
                   + (f" to @{', @'.join(m['to'])}" if m.get("to") else "") + f" ---\n{t}")
    return "<channel>\n" + "\n\n".join(out) + "\n</channel>"


def run_team(task, content, solve, max_agents=4, rounds=1, parallel=4, on_event=None):
    """solve(content, tag_suffix) -> (text, usage, trace, note) runs one agent: the same model, tools and sandbox as a
    solo trial. Returns (final_text, usage, trace, note, channel, agents).

    on_event(dict), if given, is told what happens as it happens, for the live view (harness/live.py):
    {"type": "working", "agent", "kind"} when an agent starts, {"type": "idle", ...} when it is done,
    {"type": "plan", "agents"} once the review is split, and {"type": "post", "msg"} for every post."""
    files, request, post = _split(task, content)
    files = [dict(b) for b in files]
    for b in reversed(files):  # one cache point after the files: every agent reads them from the cache
        if b.get("type") in ("text", "document", "image"):
            b["cache_control"] = dict(api.CACHE_1H)
            break
    bare = {"type": "text", "text": "<request>\n" + task["prompt_text"] + "\n</request>"}
    channel, usage, trace, calls = [], {}, [], [0]
    ids = set()  # the agents a question can go to, known once the plan is in
    lock = threading.Lock()

    def emit(e):
        if on_event:
            try:
                on_event(e)
            except Exception:  # the live view must never stop a trial
                pass

    def add_usage(u):
        for k, v in (u or {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                usage[k] = usage.get(k, 0) + v
            elif k == "library_lookups" and v:
                usage.setdefault(k, []).extend(v)
        if u and u.get("stop_reason"):
            usage["stop_reason"] = u["stop_reason"]

    def ask(role_text, who, kind, final=False):
        req = request if final else bare
        with lock:
            seen = render_channel(channel)
        cx = files + [req, {"type": "text", "text": seen},
                      {"type": "text", "text": "<your_role>\n" + role_text + "\n</your_role>"}] + post
        emit({"type": "working", "agent": who, "kind": kind})
        try:
            text, u, tr, _ = solve(cx, f"team-{who}")
        finally:
            emit({"type": "idle", "agent": who, "kind": kind})
        with lock:
            calls[0] += 1
            add_usage(u)
            trace.extend(dict(t, agent=who) for t in (tr or []))
        return text or ""

    def say(rnd, who, text, kind, to=None):
        if to is None:  # a post is addressed to the agents its ASK lines name
            to = sorted({t.lower() for t, _ in ASK_RE.findall(text) if t.lower() in ids and t.lower() != who})
        with lock:
            msg = {"n": len(channel) + 1, "round": rnd, "from": who, "to": to, "kind": kind, "text": text.strip()}
            channel.append(msg)
        emit({"type": "post", "msg": dict(msg)})
        return msg

    # 1. code basis, 2. plan
    say(0, CODE_BASIS_ID, ask(CODE_BASIS_ROLE, CODE_BASIS_ID, "basis"), "basis")
    plan_text = ask(LEAD_ROLE.format(n=max_agents), LEAD_ID, "plan")
    agents, cross = _parse_plan(plan_text, max_agents)
    ids.update([a["id"] for a in agents] + [CODE_BASIS_ID])
    emit({"type": "plan", "agents": agents})
    roster = ", ".join(["@" + CODE_BASIS_ID] + ["@" + a["id"] for a in agents])
    say(0, LEAD_ID, "Plan:\n" + "\n".join(f"- @{a['id']}: {a['member']}. {a['scope']}" for a in agents)
        + ("\nCross-checks:\n" + "\n".join(f"- {c}" for c in cross) if cross else ""), "plan")

    def questions_in(msgs):
        qs = {}
        for m in msgs:
            for target, q in ASK_RE.findall(m["text"]):
                target = target.lower()
                if target in ids and target != m["from"]:
                    qs.setdefault(target, []).append((m["from"], q.strip()))
        return qs

    # 3. members, in parallel; each post goes up as soon as its agent is done
    def member(a):
        text = ask(MEMBER_ROLE.format(id=a["id"], member=a["member"], scope=a["scope"], roster=roster), a["id"], "findings")
        return say(1, a["id"], text, "findings")
    with ThreadPoolExecutor(max_workers=max(1, min(parallel, len(agents)))) as pool:
        new = list(pool.map(member, agents))

    # 4. answer rounds: questions go to the agent they name
    role_of = {a["id"]: a for a in agents}
    for r in range(rounds):
        qs = questions_in(new)
        if not qs:
            break

        def answer(t, r=r, qs=qs):
            qtext = "\n".join(f"- from @{frm}: {q}" for frm, q in qs[t])
            text = ask(ANSWER_ROLE.format(id=t, questions=qtext) + (
                "\nYou are the code-basis engineer: answer from the documents and the adopted code." if t == CODE_BASIS_ID
                else f"\nYour part: {role_of[t]['member']}."), t, "answer")
            return say(2 + r, t, text, "answer", to=sorted({frm for frm, _ in qs[t]}))
        targets = sorted(qs)
        with ThreadPoolExecutor(max_workers=max(1, min(parallel, len(targets)))) as pool:
            new = list(pool.map(answer, targets))

    # 5. the checker writes the answer that is graded
    final = ask(CHECKER_ROLE, CHECKER_ID, "final", final=True)
    say(max(m["round"] for m in channel) + 1, CHECKER_ID, final, "final")
    note = f"team of {len(agents)} agents + code basis + checker, {len(channel)} posts, {calls[0]} model calls"
    return final, usage, trace, note, channel, agents


# ---------------- the channel as a page ----------------

COLORS = ["#2f6f62", "#7a4fb0", "#b5562e", "#2f5d8a", "#8a6d1f", "#a03f6b", "#3f7f2f", "#5a5f6b"]


def _initials(who):
    parts = [p for p in re.split(r"[-_]", who) if p]
    return ("".join(p[0] for p in parts[:2]) or who[:2]).upper()


def _fmt(text):
    t = html.escape(text)
    t = re.sub(r"^(\s*\**ASK\**\s+@[A-Za-z0-9_\-]+.*)$", r'<span class="ask">\1</span>', t, flags=re.M)
    t = re.sub(r"(@[A-Za-z0-9_\-]+)", r'<span class="at">\1</span>', t)
    return t


def render_html(channel, title, subtitle=""):
    """A self-contained chat-style page of one team trial: who posted what, in order, with @mentions marked."""
    who = []
    for m in channel:
        if m["from"] not in who:
            who.append(m["from"])
    color = {w: COLORS[i % len(COLORS)] for i, w in enumerate(who)}
    kinds = {"basis": "code basis", "plan": "plan", "findings": "findings", "answer": "answer", "final": "final answer"}
    rows = []
    for m in channel:
        c = color[m["from"]]
        to = (" → " + ", ".join("@" + t for t in m["to"])) if m.get("to") else ""
        rows.append(
            f'<article class="msg{" final" if m["kind"] == "final" else ""}">'
            f'<div class="av" style="background:{c}">{_initials(m["from"])}</div>'
            f'<div class="body"><header><b>@{html.escape(m["from"])}</b>'
            f'<span class="meta">{kinds.get(m["kind"], m["kind"])} · round {m["round"]}{html.escape(to)}</span></header>'
            f'<pre>{_fmt(m["text"])}</pre></div></article>')
    members = "".join(f'<li><span class="dot" style="background:{color[w]}"></span>@{html.escape(w)}</li>' for w in who)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root {{ --bg:#f7f6f3; --panel:#ffffff; --ink:#1f2328; --muted:#5d6470; --line:#e2dfd8; --side:#22313f; --sideink:#e8edf2;
  --ask:#fff4d6; --askink:#6b4e00; --at:#1d5fa8; --final:#eef6f1; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15181c; --panel:#1d2126; --ink:#e6e8eb; --muted:#9aa3ad; --line:#2c3239;
  --side:#0f1418; --sideink:#cfd8e0; --ask:#3a3020; --askink:#f1d38a; --at:#7fb0ea; --final:#1d2a23; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 -apple-system, "Segoe UI", Inter, sans-serif; }}
.wrap {{ display:flex; min-height:100vh }}
aside {{ width:230px; flex:none; background:var(--side); color:var(--sideink); padding:20px 16px }}
aside h1 {{ font-size:15px; margin:0 0 4px }} aside p {{ margin:0 0 16px; opacity:.75; font-size:12px }}
aside ul {{ list-style:none; padding:0; margin:0 }} aside li {{ display:flex; gap:8px; align-items:center; padding:3px 0; font-size:13px }}
.dot {{ width:9px; height:9px; border-radius:50% }}
main {{ flex:1; min-width:0; padding:20px max(16px, 3vw) }}
main > h2 {{ margin:0 0 4px; font-size:18px }} main > p {{ margin:0 0 18px; color:var(--muted) }}
.msg {{ display:flex; gap:12px; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin-bottom:10px }}
.msg.final {{ background:var(--final) }}
.av {{ width:36px; height:36px; flex:none; border-radius:8px; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:12px }}
.body {{ min-width:0; flex:1 }} header {{ display:flex; flex-wrap:wrap; gap:8px; align-items:baseline }}
.meta {{ color:var(--muted); font-size:12px }}
pre {{ white-space:pre-wrap; word-wrap:break-word; margin:6px 0 0; font:13px/1.5 ui-monospace, Menlo, Consolas, monospace }}
.ask {{ background:var(--ask); color:var(--askink); border-radius:4px; padding:0 3px }} .at {{ color:var(--at); font-weight:600 }}
@media (max-width:700px) {{ .wrap {{ display:block }} aside {{ width:auto }} }}
</style></head><body><div class="wrap">
<aside><h1>#review</h1><p>{html.escape(title)}</p><ul>{members}</ul></aside>
<main><h2>{html.escape(title)}</h2><p>{html.escape(subtitle)}</p>{''.join(rows)}</main></div></body></html>"""
