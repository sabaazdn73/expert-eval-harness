"""Optional link to a local code-ref library (the private code-ref MCP's index).

The library itself never lives in this repository: point the harness at it with --ref-lib or the
CODE_REF_DIR environment variable. Only short excerpts with standard, edition and page are used.
"""
import json
import os
import re
import sqlite3

SNIPPET = 420


class RefLibrary:
    def __init__(self, directory):
        directory = os.path.expanduser(directory)
        db = os.path.join(directory, "refs.sqlite")
        if not os.path.exists(db):
            raise FileNotFoundError(f"{db} not found: build it with build_index.py in the code-ref folder")
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        self.reg = {s["id"]: s for s in json.load(open(os.path.join(directory, "sources.json")))["sources"]}

    @staticmethod
    def _fts(q):
        if q.count('"') >= 2:
            return q
        words = re.findall(r"[A-Za-z0-9.\-]+", q)
        return " ".join(f'"{w}"' for w in words) if words else '""'

    def search(self, query, family=None, current_only=True, limit=3):
        ids = [sid for sid, s in self.reg.items()
               if (not family or family.lower() in s["family"].lower())
               and (not current_only or s["status"] == "current")]
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        sql = (f"SELECT source, page, snippet(pages, 2, '', '', ' … ', 40) FROM pages "
               f"WHERE pages MATCH ? AND source IN ({ph}) ORDER BY rank LIMIT ?")
        out = []
        for sid, page, snip in self.con.execute(sql, [self._fts(query)] + ids + [limit]):
            s = self.reg[sid]
            out.append({"source": sid, "standard": f"{s['family']} {s['edition']}", "status": s["status"],
                        "pdf_page": page, "excerpt": snip[:SNIPPET]})
        return out

    def editions(self):
        return [f"{s['family']} {s['edition']}: {s['status']}" + (f" (superseded by {self.reg[s['superseded_by']]['edition']})" if s.get("superseded_by") else "")
                for s in self.reg.values() if s.get("kind") in ("standard", "provisions")]

    def block_for(self, task):
        """Reference block for a task, from its ref_queries. Empty string when the task has none."""
        hits = []
        for q in task.get("ref_queries", []):
            hits += self.search(q["query"], q.get("family"), q.get("current_only", True), q.get("limit", 2))
        if not hits:
            return ""
        lines = ["Editions in the reference library:"] + [f"- {e}" for e in self.editions()]
        lines += ["", "Excerpts (short, for checking only):"]
        for h in hits:
            lines.append(f"- [{h['standard']}, {h['status']}, PDF p.{h['pdf_page']}] {h['excerpt']}")
        return "\n".join(lines)
