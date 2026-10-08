"""Tiny RAG engine for carrier plan documents (no external services, no heavy deps).

Pipeline:  load docs -> split into section-aware chunks -> BM25 index -> top-k retrieval.

Design choices (explained in the README):
  * CHUNK_TOKENS  = 250   small enough that 3 chunks stay well under 1.5k tokens,
                          big enough to keep a benefit rule and its exceptions together.
  * OVERLAP_TOKENS = 40   so a sentence cut at a boundary still appears whole in one chunk.
  * Chunks never cross a "## Section" heading and each chunk is prefixed with its heading,
    so the model always knows which section a snippet came from.
"""
import math
import re
from collections import Counter
from pathlib import Path

from tokens import count_tokens

DOCS_DIR = Path(__file__).parent / "docs"
CHUNK_TOKENS = 250
OVERLAP_TOKENS = 40
DEFAULT_TOP_K = 3

_STOP = set("a an and are as at be by for from has have how i in is it my of on or that the this to was what when which with do does can me you your".split())
# Words that appear in nearly every insurance paragraph carry no ranking signal.
_STOP |= set("covered cover covers coverage plan plans".split())


def _terms(text: str):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP]


def _split_sections(text: str):
    """Yield (heading, body) pairs split on '## ' headings."""
    heading, buf = "Introduction", []
    for line in text.splitlines():
        if line.startswith("## "):
            if any(l.strip() for l in buf):
                yield heading, "\n".join(buf)
            heading, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if any(l.strip() for l in buf):
        yield heading, "\n".join(buf)


def _chunk_section(body: str):
    """Pack whole lines into ~CHUNK_TOKENS chunks, carrying OVERLAP_TOKENS of context forward."""
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    chunks, cur, cur_tok = [], [], 0
    for line in lines:
        t = count_tokens(line)
        if cur and cur_tok + t > CHUNK_TOKENS:
            chunks.append("\n".join(cur))
            # carry the tail of the previous chunk as overlap
            tail, tail_tok = [], 0
            for prev in reversed(cur):
                pt = count_tokens(prev)
                if tail_tok + pt > OVERLAP_TOKENS:
                    break
                tail.insert(0, prev)
                tail_tok += pt
            cur, cur_tok = tail, tail_tok
        cur.append(line)
        cur_tok += t
    if cur:
        chunks.append("\n".join(cur))
    return chunks


class PlanDocIndex:
    def __init__(self, docs_dir: Path = DOCS_DIR):
        self.chunks = []   # dicts: plan_id, section, text, terms
        self.doc_tokens = {}
        for path in sorted(docs_dir.glob("*.md")):
            text = path.read_text()
            plan_id = path.stem
            self.doc_tokens[plan_id] = count_tokens(text)
            for heading, body in _split_sections(text):
                for piece in _chunk_section(body):
                    full = f"[{plan_id} | {heading}]\n{piece}"
                    self.chunks.append({"plan_id": plan_id, "section": heading, "text": full,
                                        "terms": _terms(heading + " " + piece)})
        self._build_bm25()

    def _build_bm25(self):
        n = len(self.chunks)
        self.avgdl = (sum(len(c["terms"]) for c in self.chunks) / n) if n else 0
        df = Counter()
        for c in self.chunks:
            df.update(set(c["terms"]))
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        for c in self.chunks:
            c["tf"] = Counter(c["terms"])

    def available_plans(self):
        return sorted(self.doc_tokens)

    def search(self, query: str, top_k: int = DEFAULT_TOP_K, plan_id: str | None = None):
        q = _terms(query)
        k1, b = 1.5, 0.75
        scored = []
        for c in self.chunks:
            if plan_id and c["plan_id"] != plan_id:
                continue
            dl = len(c["terms"]) or 1
            score = 0.0
            for t in q:
                f = c["tf"].get(t, 0)
                if f:
                    score += self.idf.get(t, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avgdl))
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"plan_id": c["plan_id"], "section": c["section"], "score": round(s, 2), "text": c["text"]}
                for s, c in scored[:top_k]]


_index = None


def get_index() -> PlanDocIndex:
    global _index
    if _index is None:
        _index = PlanDocIndex()
    return _index
