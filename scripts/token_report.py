"""Rule 3 evidence: tokens if you paste the whole document vs. tokens the RAG tool returns.

Run:  python scripts/token_report.py          (prints a markdown table for the README)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rag import CHUNK_TOKENS, DEFAULT_TOP_K, OVERLAP_TOKENS, get_index  # noqa: E402
from tokens import count_tokens, token_method  # noqa: E402

QUERIES = [
    ("is metformin covered", "anthem_hmo_silver"),
    ("do I need a referral to see a specialist", "anthem_hmo_silver"),
    ("what needs prior authorization", "kaiser_hmo_silver"),
    ("what does insulin glargine cost per fill", "oscar_epo_gold_tx"),
    ("can I open an HSA with this plan", "uhc_hdhp_bronze_ca"),
    ("what happens if my allowance is bigger than the premium", "kaiser_hmo_silver"),
    ("how long do I have to add a newborn", "oscar_epo_gold_tx"),
    ("how do I appeal a denied claim", "uhc_hdhp_bronze_ca"),
]

idx = get_index()
sizes = [count_tokens(c["text"]) for c in idx.chunks]
print(f"Token counting method: **{token_method()}**  ")
print(f"Chunk target: {CHUNK_TOKENS} tokens, overlap {OVERLAP_TOKENS}, top_k {DEFAULT_TOP_K}. "
      f"Index: {len(idx.chunks)} chunks, avg {sum(sizes)//len(sizes)} tokens (max {max(sizes)}).\n")
print("| Question | Plan | Full document | RAG tool (top 3) | Saved |")
print("|---|---|---:|---:|---:|")
tot_full = tot_rag = 0
for q, pid in QUERIES:
    hits = idx.search(q, top_k=DEFAULT_TOP_K, plan_id=pid)
    rag = sum(count_tokens(h["text"]) for h in hits)
    full = idx.doc_tokens[pid]
    tot_full += full
    tot_rag += rag
    print(f"| {q} | {pid} | {full:,} | {rag:,} | {100 * (1 - rag / full):.0f}% |")
print(f"| **Average over {len(QUERIES)} questions** | | **{tot_full // len(QUERIES):,}** | **{tot_rag // len(QUERIES):,}** | **{100 * (1 - tot_rag / tot_full):.0f}%** |")
all_docs = sum(idx.doc_tokens.values())
print(f"\nComparing across all {len(idx.doc_tokens)} documented plans: pasting every document = {all_docs:,} tokens "
      f"vs. 4 calls to the RAG tool = roughly {4 * tot_rag // len(QUERIES):,} tokens.")
