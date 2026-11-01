"""Optional link to a local code-ref library (the private code-ref MCP's index).

The library itself never lives in this repository: point the harness at it with --ref-lib or the
CODE_REF_DIR environment variable. Only short excerpts with standard, edition and page are used.
"""
import json
import os
import re
import sqlite3
import threading

SNIPPET = 420


class RefLibrary:
    def __init__(self, directory):
        directory = os.path.expanduser(directory)
        db = os.path.join(directory, "refs.sqlite")
        if not os.path.exists(db):
            raise FileNotFoundError(f"{db} not found: build it with build_index.py in the code-ref folder")
        self.db = db
        self._local = threading.local()  # one read-only connection per worker thread
        meta = json.load(open(os.path.join(directory, "sources.json")))
        self.reg = {s["id"]: s for s in meta["sources"]}
        self.adoption = meta.get("ibc_adoption", {})
        self.local = meta.get("local_amendments", {})
        self.base = os.path.dirname(os.path.abspath(directory))  # source paths are relative to this folder

    @property
    def con(self):
        c = getattr(self._local, "con", None)
        if c is None:
            c = self._local.con = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        return c

    def adopted_by(self, sid):
        """IBC editions in the adoption table that reference this source's edition."""
        s = self.reg.get(sid, {})
        ed = s.get("edition", "").split()[0] if s.get("edition") else ""
        return [ibc for ibc, row in self.adoption.items() if not ibc.startswith("_")
                and row.get(s.get("family")) == ed]

    def page_text(self, source, page, limit=6000):
        if source not in self.reg:
            return f"error: unknown source {source!r}; use code_ref_search or code_ref_editions for valid ids"
        row = self.con.execute("SELECT body FROM pages WHERE source = ? AND page = ?", (source, int(page))).fetchone()
        if not row:
            return f"error: {source} has no text for PDF page {page} (out of range, blank or scanned); try code_ref_page_image"
        return row[0][:limit]

    def page_image(self, source, page, dpi=110):
        """PNG of one PDF page (base64), so equations and tables can be read as printed."""
        import base64
        s = self.reg.get(source)
        if not s:
            return None, f"unknown source {source}"
        path = os.path.join(self.base, s["path"])
        if not path.lower().endswith(".pdf") or not os.path.exists(path):
            return None, "no PDF for this source"
        try:
            import pymupdf
            doc = pymupdf.open(path)
            png = doc[int(page) - 1].get_pixmap(dpi=dpi).tobytes("png")
        except ImportError:
            import subprocess, tempfile
            with tempfile.TemporaryDirectory() as td:
                r = subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-png", "-singlefile",
                                    path, os.path.join(td, "p")], capture_output=True)
                if r.returncode != 0:
                    return None, "cannot render pages: pip install pymupdf (or install poppler)"
                png = open(os.path.join(td, "p.png"), "rb").read()
        except Exception as e:
            return None, f"cannot render page: {e}"
        return base64.b64encode(png).decode(), None

    @staticmethod
    def _fts(q):
        """Always quote each word, so user text can never be FTS5 syntax (no syntax errors from stray quotes)."""
        words = re.findall(r"[A-Za-z0-9.\-]+", q)
        return " ".join('"' + w.replace('"', '') + '"' for w in words) if words else '""'

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
            hit = {"source": sid, "standard": f"{s['family']} {s['edition']}", "status": s["status"],
                   "pdf_page": page, "excerpt": snip[:SNIPPET]}
            ad = self.adopted_by(sid)
            if ad:
                hit["adopted_by"] = ad
            out.append(hit)
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
