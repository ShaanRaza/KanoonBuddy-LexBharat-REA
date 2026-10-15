"""Editor documents: each user's own saved drafts (the "Editor" screen).

The editor keeps a ProseMirror document as a JSON string. We store it as is, per user, and derive the
title from the first line of text. Nothing here calls a model.
"""
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("EDITOR_DB", ROOT / "data" / "editor.sqlite"))
MAX_DOC_BYTES = 800_000       # stays under the 1 MB request cap
MAX_DOCS_PER_USER = 200
_lock = threading.Lock()


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(
        """CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT,
               content TEXT NOT NULL, saved_at TEXT NOT NULL);
           CREATE INDEX IF NOT EXISTS d_user ON docs(user_id, saved_at);"""
    )
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass
    return c


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def _first_text(node) -> str:
    """First non-empty run of text in a ProseMirror node tree."""
    if isinstance(node, dict):
        if isinstance(node.get("text"), str) and node["text"].strip():
            return node["text"].strip()
        kids = node.get("content") or []
        if isinstance(kids, dict):      # the saved file wraps the document: {"content": {"type": "doc", ...}}
            kids = [kids]
        for child in kids:
            t = _first_text(child)
            if t:
                return t
    return ""


def derive_title(content: str) -> str:
    try:
        t = _first_text(json.loads(content))
    except Exception:
        t = ""
    return (t[:80] or "Untitled document")


def register(app):
    @app.get("/api/editor/documents")
    def list_docs(request: Request):
        c = _conn()
        try:
            uid = request.state.user["id"]
            for r in c.execute("SELECT id,content FROM docs WHERE user_id=? AND title='Untitled document'", (uid,)).fetchall():
                t = derive_title(r["content"])           # repair titles saved before the title finder handled wrapped documents
                if t != "Untitled document":
                    c.execute("UPDATE docs SET title=? WHERE id=? AND user_id=?", (t, r["id"], uid))
            c.commit()
            rows = c.execute("SELECT id,title,saved_at FROM docs WHERE user_id=? ORDER BY saved_at DESC LIMIT 500", (uid,)).fetchall()
        finally:
            c.close()
        return {"documents": [{"id": r["id"], "title": r["title"], "savedAt": r["saved_at"]} for r in rows]}

    @app.get("/api/editor/documents/{doc_id}")
    def get_doc(doc_id: str, request: Request):
        c = _conn()
        try:
            r = c.execute("SELECT * FROM docs WHERE id=? AND user_id=?", (doc_id, request.state.user["id"])).fetchone()
        finally:
            c.close()
        if r is None:
            raise HTTPException(404, "Document not found")
        return {"id": r["id"], "title": r["title"], "content": r["content"], "savedAt": r["saved_at"]}

    @app.post("/api/editor/documents")
    async def save_doc(request: Request):
        uid = request.state.user["id"]
        try:
            body = await request.json()
            content = body.get("content")
            if not isinstance(body, dict) or not isinstance(content, str):
                raise ValueError
            json.loads(content)  # must be valid editor JSON
        except Exception:
            return JSONResponse({"error": "Invalid document"}, status_code=400)
        if len(content.encode()) > MAX_DOC_BYTES:
            return JSONResponse({"error": "That document is too large to save."}, status_code=413)
        doc_id = str(body.get("id") or "")[:64]
        title, now = derive_title(content), _now()
        with _lock:
            c = _conn()
            try:
                owned = c.execute("SELECT 1 FROM docs WHERE id=? AND user_id=?", (doc_id, uid)).fetchone() if doc_id else None
                if doc_id and not owned and c.execute("SELECT 1 FROM docs WHERE id=?", (doc_id,)).fetchone():
                    return JSONResponse({"error": "Document not found"}, status_code=404)  # someone else's id
                if owned:
                    c.execute("UPDATE docs SET title=?, content=?, saved_at=? WHERE id=?", (title, content, now, doc_id))
                else:
                    if c.execute("SELECT count(*) FROM docs WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_DOCS_PER_USER:
                        return JSONResponse({"error": f"You can keep up to {MAX_DOCS_PER_USER} documents. Delete some to save more."}, status_code=409)
                    doc_id = doc_id or str(uuid.uuid4())
                    c.execute("INSERT INTO docs VALUES (?,?,?,?,?)", (doc_id, uid, title, content, now))
                c.commit()
            finally:
                c.close()
        return {"id": doc_id, "title": title, "savedAt": now}

    @app.delete("/api/editor/documents/{doc_id}")
    def delete_doc(doc_id: str, request: Request):
        c = _conn()
        try:
            c.execute("DELETE FROM docs WHERE id=? AND user_id=?", (doc_id, request.state.user["id"]))
            c.commit()
        finally:
            c.close()
        return {"success": True}

    @app.get("/api/editor/documents/{doc_id}/download")
    def download_unavailable(doc_id: str):
        return JSONResponse({"error": "Downloading documents isn't available yet."}, status_code=501)


def export_user(user_id: str) -> list:
    c = _conn()
    try:
        return [dict(r) for r in c.execute("SELECT id,title,content,saved_at FROM docs WHERE user_id=?", (user_id,))]
    finally:
        c.close()


def delete_user(user_id: str) -> None:
    c = _conn()
    try:
        c.execute("DELETE FROM docs WHERE user_id=?", (user_id,))
        c.commit()
    finally:
        c.close()
