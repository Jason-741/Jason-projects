import hashlib
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Document, DocumentSegment
from ..research import credibility, transcripts
from ..research.llm import LLMClient
from ..research.search import bm25
from ..security.auth import current_user
from ..services.market_data import find_security

router = APIRouter(prefix="/api/research", tags=["research"], dependencies=[Depends(current_user)])


def _extract_text(name: str, raw: bytes) -> str:
    if name.lower().endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader
        except ImportError:
            raise HTTPException(422, "PDF support requires pypdf (pip install pypdf)")
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(f"[[page {i + 1}]]\n" + (p.extract_text() or "") for i, p in enumerate(reader.pages))
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "text documents must be UTF-8")


def _segments_for(doc_type: str, text: str):
    if doc_type == "transcript":
        return [s.as_dict() for s in transcripts.segment_transcript(text)]
    # Generic documents: segment by page marker (PDF) or paragraph blocks, keeping location.
    out, seq = [], 0
    page = None
    for block in text.split("\n\n"):
        b = block.strip()
        if not b:
            continue
        if b.startswith("[[page "):
            page = b.split("]]")[0].replace("[[page ", "")
            b = b.split("]]", 1)[1].strip()
            if not b:
                continue
        seq += 1
        out.append({"seq": seq, "section": None, "speaker": None, "role": None, "text": b[:8000],
                    "location": f"page {page}, block {seq}" if page else f"block {seq}"})
    return out


@router.post("/documents")
async def upload(file: UploadFile = File(...), doc_type: str = Form(...), symbol: str | None = Form(None),
                 title: str | None = Form(None), source: str = Form("user_upload"), url: str | None = Form(None),
                 published_at: date | None = Form(None), db: Session = Depends(get_db)):
    raw = await file.read()
    if len(raw) > 25_000_000:
        raise HTTPException(413, "file too large")
    text = _extract_text(file.filename or "", raw)
    sec = find_security(db, symbol) if symbol else None
    doc = Document(security_id=sec.id if sec else None, doc_type=doc_type, title=title or file.filename, source=source,
                   url=url, published_at=published_at, sha256=hashlib.sha256(raw).hexdigest(), content_text=text)
    db.add(doc)
    db.flush()
    segs = _segments_for(doc_type, text)
    for s in segs:
        db.add(DocumentSegment(document_id=doc.id, **{k: s[k] for k in ("seq", "section", "speaker", "role", "text", "location")}))
    db.commit()
    return {"id": doc.id, "title": doc.title, "segments": len(segs), "sha256": doc.sha256,
            "note": "document content is stored as untrusted data"}


@router.get("/documents")
def list_docs(symbol: str | None = None, db: Session = Depends(get_db)):
    q = select(Document)
    if symbol:
        sec = find_security(db, symbol)
        q = q.where(Document.security_id == (sec.id if sec else -1))
    return [{"id": d.id, "title": d.title, "doc_type": d.doc_type, "source": d.source, "url": d.url,
             "published_at": str(d.published_at) if d.published_at else None, "retrieved_at": d.retrieved_at.isoformat()}
            for d in db.scalars(q.order_by(Document.id.desc()))]


def _segs(db, doc_id):
    return list(db.scalars(select(DocumentSegment).where(DocumentSegment.document_id == doc_id).order_by(DocumentSegment.seq)))


def _as_seg(s: DocumentSegment):
    return transcripts.Segment(s.seq, s.section or "", s.speaker or "", s.role or "unknown", s.text, s.location or "")


@router.get("/documents/{doc_id}/analysis")
def analysis(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    segs = [_as_seg(s) for s in _segs(db, doc_id)]
    by_role = {}
    for s in segs:
        by_role.setdefault(s.role, 0)
        by_role[s.role] += 1
    return {"document": {"id": doc.id, "title": doc.title, "source": doc.source, "url": doc.url},
            "segments_by_role": by_role, "segments": [s.as_dict() for s in segs],
            "guidance_candidates": transcripts.candidate_guidance(segs), "tone": transcripts.tone(segs),
            "notes": ["guidance items are CANDIDATES extracted by pattern matching — confirm against the source",
                      "tone scores are supporting indicators, never standalone signals"]}


@router.get("/compare")
def compare(prev_id: int, cur_id: int, db: Session = Depends(get_db)):
    return transcripts.compare_calls([_as_seg(s) for s in _segs(db, prev_id)], [_as_seg(s) for s in _segs(db, cur_id)])


class AskIn(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    document_ids: list[int] = Field(min_length=1, max_length=20)
    top_k: int = Field(12, ge=1, le=40)


@router.post("/ask")
def ask(b: AskIn, db: Session = Depends(get_db)):
    pool = []
    for did in b.document_ids:
        doc = db.get(Document, did)
        if not doc:
            raise HTTPException(404, f"document {did} not found")
        for s in _segs(db, did):
            pool.append({"id": s.id, "doc_title": doc.title, "location": s.location, "speaker": s.speaker, "text": s.text})
    scores = bm25(b.question, [p["text"] for p in pool])
    ranked = [p for sc, p in sorted(zip(scores, pool), key=lambda x: -x[0]) if sc > 0][: b.top_k]
    res = LLMClient().answer(b.question, ranked)
    res["retrieved"] = [{"id": f"S{p['id']}", "doc": p["doc_title"], "location": p["location"], "speaker": p["speaker"],
                         "excerpt": p["text"][:400]} for p in ranked]
    return res


class CredIn(BaseModel):
    records: list[dict]


@router.post("/credibility")
def cred(b: CredIn):
    return credibility.score_guidance(b.records)
