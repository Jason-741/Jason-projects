"""Deterministic earnings-call transcript segmentation (no LLM required).

Input: a transcript the USER supplies (pasted text or file) — the platform does not fabricate or
scrape transcripts. Expected layout (common in public transcripts):

    Participants / Corporate Participants
      Jane Doe - Chief Executive Officer
      John Roe - Chief Financial Officer
    ...
    Jane Doe: (text)            or       Jane Doe -- CEO
                                         (text)
    Operator: ...
    Question-and-Answer Session

Output: located segments (speaker, role, section, turn number) so later analysis can cite them.
Guidance extraction here is a keyword/regex pass that surfaces CANDIDATE forward-looking
sentences with their location — a human (or an LLM step with citations) must confirm them.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

ROLE_PATTERNS = [
    ("ceo", re.compile(r"\b(chief executive|ceo|president and ceo)\b", re.I)),
    ("cfo", re.compile(r"\b(chief financial|cfo|finance director)\b", re.I)),
    ("executive", re.compile(r"\b(chief|coo|cto|vice president|vp|svp|evp|head of|director|investor relations|treasurer)\b", re.I)),
    ("analyst", re.compile(r"\b(analyst|research|securities|capital markets|bank|partners|llc|& co)\b", re.I)),
]
QA_MARKERS = re.compile(r"^\s*(question[- ]and[- ]answer|q\s*&\s*a|questions and answers)\b", re.I)
SPEAKER_LINE = re.compile(r"^\s*(?P<name>[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})\s*(?:--|—|-|,)?\s*(?P<title>[^:]{0,80})?:\s*(?P<text>.*)$")
PARTICIPANT_LINE = re.compile(r"^\s*(?P<name>[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3})\s*(?:--|—|-|,)\s*(?P<title>.+)$")

GUIDANCE_TERMS = re.compile(
    r"\b(guidance|outlook|expect(?:s|ed|ing)?|anticipate[sd]?|forecast|target(?:ing)?|we (?:plan|intend) to|"
    r"full[- ]year|fiscal (?:20\d\d|year)|next (?:quarter|year)|capex|capital expenditure|production of|"
    r"aisc|all-in sustaining|range of)\b", re.I)
METRIC_TERMS = {
    "revenue": re.compile(r"\b(revenue|sales)\b", re.I),
    "ebitda": re.compile(r"\bebitda\b", re.I),
    "eps": re.compile(r"\b(eps|earnings per share)\b", re.I),
    "production": re.compile(r"\b(production|ounces|oz|pounds|lbs|tonnes|boe|barrels)\b", re.I),
    "capex": re.compile(r"\b(capex|capital expenditure|capital spending)\b", re.I),
    "costs": re.compile(r"\b(aisc|all-in sustaining|cash cost|unit cost)\b", re.I),
    "margin": re.compile(r"\bmargin", re.I),
    "cash_flow": re.compile(r"\b(free cash flow|cash flow)\b", re.I),
    "debt_liquidity": re.compile(r"\b(debt|liquidity|leverage|credit facility|refinanc)\w*", re.I),
}
UNCERTAINTY = re.compile(r"\b(uncertain|uncertainty|challenging|headwind|difficult|volatile|cautious|delay(?:ed|s)?|"
                         r"risk|pressure|softness|weak(?:er|ness)?|lower than expected)\b", re.I)
CONFIDENCE = re.compile(r"\b(confident|strong|record|robust|ahead of|exceed(?:ed|ing)?|momentum|tailwind|on track|"
                        r"accelerat\w+|outperform\w*)\b", re.I)
NUMBER = re.compile(r"(\$?\d[\d,]*(?:\.\d+)?\s*(?:%|percent|million|billion|thousand|[mbk]\b|oz|ounces|lbs|pounds|tonnes)?)", re.I)


@dataclass
class Segment:
    seq: int
    section: str
    speaker: str
    role: str
    text: str
    location: str

    def as_dict(self):
        return asdict(self)


def classify_role(name: str, title: str | None) -> str:
    if name.lower() == "operator":
        return "operator"
    t = title or ""
    for role, pat in ROLE_PATTERNS:
        if pat.search(t):
            return role
    return "unknown"


def parse_participants(text: str) -> dict[str, str]:
    roles = {}
    for line in text.splitlines()[:200]:
        m = PARTICIPANT_LINE.match(line)
        if m and ":" not in line:
            roles[m.group("name").strip()] = classify_role(m.group("name"), m.group("title"))
    return roles


def segment_transcript(text: str) -> list[Segment]:
    roles = parse_participants(text)
    section = "prepared_remarks"
    segs: list[Segment] = []
    cur_name, cur_role, buf, start_line = None, None, [], 0

    def flush(end_line):
        nonlocal buf
        body = " ".join(x.strip() for x in buf if x.strip())
        if cur_name and body:
            segs.append(Segment(len(segs) + 1, section, cur_name, cur_role or "unknown", body,
                                f"turn {len(segs) + 1}, lines {start_line}-{end_line}"))
        buf = []

    for i, line in enumerate(text.splitlines(), start=1):
        if QA_MARKERS.match(line):
            flush(i - 1)
            section = "qa"
            cur_name = None
            continue
        m = SPEAKER_LINE.match(line)
        if m:
            name = m.group("name").strip()
            known = name in roles or name.lower() == "operator"
            if known or (m.group("title") and classify_role(name, m.group("title")) != "unknown"):
                flush(i - 1)
                cur_name = name
                cur_role = roles.get(name) or classify_role(name, m.group("title"))
                start_line = i
                buf = [m.group("text")]
                continue
        if cur_name:
            buf.append(line)
    flush(len(text.splitlines()))
    return segs


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9$])")


def candidate_guidance(segments: list[Segment]) -> list[dict]:
    """Forward-looking sentences from management (not analysts/operator) containing numbers."""
    out = []
    for s in segments:
        if s.role not in ("ceo", "cfo", "executive", "unknown"):
            continue
        for j, sent in enumerate(_SENT.split(s.text)):
            if GUIDANCE_TERMS.search(sent) and NUMBER.search(sent):
                metrics = [k for k, p in METRIC_TERMS.items() if p.search(sent)]
                out.append({"speaker": s.speaker, "role": s.role, "section": s.section, "location": f"{s.location}, sentence {j + 1}",
                            "metrics": metrics, "numbers": [n.strip() for n in NUMBER.findall(sent)][:6], "text": sent.strip(),
                            "status": "candidate — verify against source"})
    return out


def tone(segments: list[Segment]) -> dict:
    """Counts of confidence vs uncertainty words per 1,000 words by role group. A SUPPORTING
    indicator only: word counts are crude, context-blind and easy to game."""
    groups: dict[str, dict] = {}
    for s in segments:
        g = "management" if s.role in ("ceo", "cfo", "executive") else s.role
        d = groups.setdefault(g, {"words": 0, "uncertainty": 0, "confidence": 0})
        d["words"] += len(s.text.split())
        d["uncertainty"] += len(UNCERTAINTY.findall(s.text))
        d["confidence"] += len(CONFIDENCE.findall(s.text))
    for d in groups.values():
        w = max(d["words"], 1)
        d["uncertainty_per_1k"] = 1000 * d["uncertainty"] / w
        d["confidence_per_1k"] = 1000 * d["confidence"] / w
        d["net_tone_per_1k"] = d["confidence_per_1k"] - d["uncertainty_per_1k"]
    return groups


def compare_calls(prev: list[Segment], cur: list[Segment]) -> dict:
    tp, tc = tone(prev), tone(cur)
    m_prev, m_cur = tp.get("management", {}), tc.get("management", {})
    return {"previous": tp, "current": tc,
            "management_net_tone_change_per_1k": (m_cur.get("net_tone_per_1k", 0) - m_prev.get("net_tone_per_1k", 0))
            if m_prev and m_cur else None,
            "note": "lexicon tone is a supporting indicator, never a standalone signal"}
