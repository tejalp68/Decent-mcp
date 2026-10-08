"""ICHRA Employee Assistant - an MCP server for Decent's small-business clients.

Context: with an ICHRA (Individual Coverage HRA) a company gives each employee a monthly
allowance and the employee shops for their own individual health plan. That shopping step is
confusing. This server lets an AI assistant (Claude, Cursor, a local model...) help an employee
compare plans against their real allowance - and hand off to a human Decent advisor when needed.

All data is MOCK data (see data/ and docs/). IMPORTANT for stdio transport: never print() to
stdout in this file - stdout carries the MCP protocol. Log to stderr only.

Run:
    python server.py                      # stdio  (Claude Desktop, Cursor, VS Code)
    python server.py --transport http     # streamable HTTP on http://127.0.0.1:8000/mcp
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from rag import DEFAULT_TOP_K, get_index
from tokens import count_tokens, token_method

DATA = Path(__file__).parent / "data"

mcp = FastMCP(
    "decent-ichra-assistant",
    instructions=(
        "You help employees at Decent client companies choose a health plan using their employer's "
        "ICHRA monthly allowance. Always look up the employee's real allowance first with "
        "get_employee_allowance. Use only data returned by the tools. You are NOT a doctor or a "
        "licensed insurance advisor: for medical, legal, tax or unclear situations, call "
        "flag_for_advisor so a human Decent advisor can follow up."
    ),
)


# ----------------------------------------------------------------------------- data helpers
def _load(name: str):
    return json.loads((DATA / name).read_text())


def _employee(employee_id: str) -> dict:
    for e in _load("employees.json"):
        if e["id"] == employee_id.strip().lower():
            return e
    raise ValueError(
        f"No employee found with id '{employee_id}'. Employee ids look like 'emp_001'. "
        "Ask the user for their employee id."
    )


def _plan(plan_id: str) -> dict:
    for p in _load("plans.json"):
        if p["plan_id"] == plan_id.strip().lower():
            return p
    raise ValueError(
        f"No plan found with id '{plan_id}'. Plan ids look like 'anthem_hmo_silver'. "
        "Call list_plans first to get valid plan ids."
    )


def _monthly_premium(plan: dict, age: int, dependents: int) -> float:
    """MOCK pricing: premium rises with age (3:1 cap, like the ACA) and each dependent adds 60% of the base rate."""
    age_factor = min(3.0, 1.0 + max(0, age - 21) * 0.0465)
    base = plan["base_premium_21"]
    return round(base * age_factor + dependents * 0.6 * base, 2)


# ----------------------------------------------------------------------------- TOOLS
@mcp.tool()
def get_employee_allowance(employee_id: str) -> dict:
    """Look up one employee's ICHRA details: monthly allowance, age, zip code, dependents,
    employee class and enrollment deadline.

    Use this FIRST, before listing or comparing plans, because every other step needs these numbers.
    Input: employee_id such as 'emp_001'. Do not guess the id; ask the user if you do not know it.
    """
    e = _employee(employee_id)
    return {
        "employee_id": e["id"],
        "name": e["name"],
        "company_id": e["company_id"],
        "monthly_allowance": e["monthly_allowance"],
        "age": e["age"],
        "zip_code": e["zip"],
        "dependents": e["dependents"],
        "employee_class": e["employee_class"],
        "enrollment_deadline": e["enrollment_deadline"],
    }


@mcp.tool()
def list_plans(zip_code: str, age: int, dependents: int = 0, monthly_allowance: float = 0) -> dict:
    """List the individual health plans sold in a zip code, with the monthly premium for this person.

    Use this after get_employee_allowance to see which plans exist. Pass the employee's zip_code, age
    and dependents. If you also pass monthly_allowance, each plan shows how much the employee would
    pay out of their own pocket each month after the employer allowance.
    Returns plan ids, carrier, plan type (HMO/PPO/EPO/HDHP), metal tier, deductible, out-of-pocket max.
    Plans with has_document=true can be searched with search_plan_documents.
    """
    zip_code = zip_code.strip()
    plans = [p for p in _load("plans.json") if zip_code in p["zips"]]
    if not plans:
        supported = sorted({z for p in _load("plans.json") for z in p["zips"]})
        raise ValueError(f"No plans are sold in zip code {zip_code}. Supported zip codes: {', '.join(supported)}.")
    if age < 18 or age > 90:
        raise ValueError("age must be between 18 and 90.")
    documented = set(get_index().available_plans())
    rows = []
    for p in plans:
        prem = _monthly_premium(p, age, dependents)
        row = {
            "plan_id": p["plan_id"],
            "name": p["name"],
            "carrier": p["carrier"],
            "plan_type": p["plan_type"],
            "metal_tier": p["metal_tier"],
            "monthly_premium": prem,
            "deductible": p["deductible"],
            "out_of_pocket_max": p["oop_max"],
            "hsa_eligible": p["hsa_eligible"],
            "has_document": p["plan_id"] in documented,
        }
        if monthly_allowance > 0:
            row["employee_pays_per_month_after_allowance"] = round(max(0.0, prem - monthly_allowance), 2)
        rows.append(row)
    rows.sort(key=lambda r: r["monthly_premium"])
    return {"zip_code": zip_code, "age": age, "dependents": dependents, "plans": rows,
            "note": "Premiums are MOCK estimates for a student project."}


@mcp.tool()
def search_plan_documents(query: str, plan_id: str = "", top_k: int = DEFAULT_TOP_K) -> dict:
    """Search the carrier's plan documents (benefits, drug formulary, referrals, prior authorization,
    emergency care, claims, ICHRA reimbursement) and return ONLY the few most relevant passages.

    Use this for specific questions such as 'is metformin covered', 'do I need a referral',
    'what needs prior authorization'. ALWAYS pass plan_id when you know it (e.g. 'anthem_hmo_silver'),
    otherwise passages from different plans get mixed. Only plans with has_document=true in list_plans
    have documents. Quote or paraphrase the returned passages; if nothing relevant is returned, say you
    could not find it and offer flag_for_advisor.
    """
    index = get_index()
    plan_id = plan_id.strip().lower()
    if plan_id and plan_id not in index.available_plans():
        raise ValueError(
            f"No document for plan '{plan_id}'. Plans with documents: {', '.join(index.available_plans())}."
        )
    top_k = max(1, min(int(top_k), 5))
    hits = index.search(query, top_k=top_k, plan_id=plan_id or None)
    returned = sum(count_tokens(h["text"]) for h in hits)
    out = {
        "query": query,
        "plan_id": plan_id or "all documented plans",
        "passages": [{"plan_id": h["plan_id"], "section": h["section"], "relevance": h["score"], "text": h["text"]}
                     for h in hits],
        "tokens_returned": returned,
        "token_count_method": token_method(),
    }
    if plan_id:
        out["tokens_in_full_document"] = index.doc_tokens[plan_id]
    if not hits:
        out["note"] = "No relevant passages found. Do not guess; tell the user and offer flag_for_advisor."
    return out


USAGE_PROFILES = {
    "low":    {"pcp_visits": 1, "specialist_visits": 0, "generic_fills": 0,  "major_event_bill": 0},
    "medium": {"pcp_visits": 4, "specialist_visits": 3, "generic_fills": 12, "major_event_bill": 3000},
    "high":   {"pcp_visits": 8, "specialist_visits": 8, "generic_fills": 24, "major_event_bill": 30000},
}
# What the provider bills (before insurance) per service - used only for deductible-based plans.
BILLED = {"pcp": 150, "specialist": 250, "fill": 30}


@mcp.tool()
def estimate_yearly_cost(employee_id: str, plan_id: str, usage_level: str = "medium") -> dict:
    """Estimate one employee's total yearly cost on one plan, after their employer ICHRA allowance.

    Use this to compare plans for a specific person once you have plan ids from list_plans.
    usage_level is 'low' (healthy, 1 checkup), 'medium' (a few visits, regular generic medication, one
    small procedure) or 'high' (frequent care and a hospital stay). Returns the yearly premium the
    employee pays after the allowance, expected out-of-pocket care costs, expected total, and the
    worst-case total. This is a rough estimate, not a quote.
    """
    usage_level = usage_level.strip().lower()
    if usage_level not in USAGE_PROFILES:
        raise ValueError("usage_level must be one of: low, medium, high.")
    e = _employee(employee_id)
    p = _plan(plan_id)
    if e["zip"] not in p["zips"]:
        raise ValueError(f"Plan '{p['plan_id']}' is not sold in the employee's zip code {e['zip']}. "
                         "Call list_plans with the employee's zip code to see valid plans.")
    u = USAGE_PROFILES[usage_level]

    monthly = _monthly_premium(p, e["age"], e["dependents"])
    annual_premium = round(monthly * 12, 2)
    annual_allowance = e["monthly_allowance"] * 12
    employee_premium = round(max(0.0, annual_premium - annual_allowance), 2)
    unused_allowance = round(max(0.0, annual_allowance - annual_premium), 2)

    coins = p["coinsurance_pct"] / 100
    ded = p["deductible"]
    if p["pcp_copay"] is not None:      # plans with flat copays for routine care
        copays = (u["pcp_visits"] * p["pcp_copay"] + u["specialist_visits"] * p["specialist_copay"]
                  + u["generic_fills"] * p["rx_generic_copay"])
        big = u["major_event_bill"]
        big_cost = min(big, ded) + coins * max(0, big - ded)
        oop = min(p["oop_max"], copays + big_cost)
    else:                                # HDHP: everything counts toward the deductible
        billed = (u["pcp_visits"] * BILLED["pcp"] + u["specialist_visits"] * BILLED["specialist"]
                  + u["generic_fills"] * BILLED["fill"] + u["major_event_bill"])
        oop = min(p["oop_max"], min(billed, ded) + coins * max(0, billed - ded))
    oop = round(oop, 2)

    return {
        "employee_id": e["id"], "plan_id": p["plan_id"], "plan_name": p["name"], "usage_level": usage_level,
        "monthly_premium": monthly,
        "yearly_premium_after_allowance": employee_premium,
        "unused_allowance_lost": unused_allowance,
        "expected_out_of_pocket_care": oop,
        "expected_total_yearly_cost": round(employee_premium + oop, 2),
        "worst_case_total_yearly_cost": round(employee_premium + p["oop_max"], 2),
        "assumptions": [
            "Mock pricing and a simplified cost model; not a real quote.",
            "Care usage is modelled for the employee only; dependents add to the premium but their care is not modelled.",
            "Unused allowance is not paid out as cash (per company policy).",
        ],
    }


@mcp.tool()
def flag_for_advisor(employee_id: str, reason: str, urgency: str = "normal") -> dict:
    """Ask a human Decent advisor to follow up with this employee. This writes a ticket.

    Use this when the question needs a person: medical or legal advice, tax questions, a doctor or
    drug that cannot be confirmed, a life event (new baby, marriage, moving), or when the documents
    do not answer the question. Give a short, specific reason. urgency is 'normal' or 'urgent'
    (urgent only if an enrollment deadline is within a few days).
    """
    urgency = urgency.strip().lower()
    if urgency not in ("normal", "urgent"):
        raise ValueError("urgency must be 'normal' or 'urgent'.")
    if len(reason.strip()) < 10:
        raise ValueError("Please give a specific reason (at least a short sentence) so the advisor knows what to do.")
    e = _employee(employee_id)
    path = DATA / "advisor_flags.json"
    flags = json.loads(path.read_text()) if path.exists() else []
    ticket = {
        "ticket_id": f"TKT-{uuid.uuid4().hex[:6].upper()}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "employee_id": e["id"], "employee_name": e["name"], "company_id": e["company_id"],
        "enrollment_deadline": e["enrollment_deadline"], "urgency": urgency, "reason": reason.strip(),
        "status": "open",
    }
    flags.append(ticket)
    path.write_text(json.dumps(flags, indent=2))
    return {"ticket_id": ticket["ticket_id"], "status": "open",
            "message": f"A Decent advisor will follow up with {e['name']} before the enrollment deadline ({e['enrollment_deadline']})."}


# ----------------------------------------------------------------------------- RESOURCES
@mcp.resource("decent://glossary")
def glossary() -> str:
    """Plain-language definitions of health insurance terms (deductible, ICHRA, HMO, ...)."""
    return (DATA / "glossary.md").read_text()


@mcp.resource("decent://carriers")
def carriers() -> str:
    """Insurance carriers available through Decent, with plan types and states."""
    return json.dumps(_load("carriers.json"), indent=2)


@mcp.resource("decent://company/{company_id}/ichra-policy")
def company_policy(company_id: str) -> str:
    """An employer's ICHRA rules: allowance by employee class, enrollment window and notes."""
    companies = _load("companies.json")
    if company_id not in companies:
        raise ValueError(f"Unknown company '{company_id}'. Known: {', '.join(companies)}")
    return json.dumps(companies[company_id], indent=2)


# ----------------------------------------------------------------------------- PROMPTS
@mcp.prompt()
def pick_my_plan(employee_id: str) -> str:
    """Guided flow: help an employee pick a plan using their real ICHRA allowance."""
    return (
        f"Help employee {employee_id} choose a health plan. Follow these steps in order:\n"
        "1. Call get_employee_allowance to get their allowance, zip code, age and dependents.\n"
        "2. Ask ONE question: how much medical care do they expect this year (low, medium or high), "
        "and do they take regular medication?\n"
        "3. Call list_plans with their zip code, age, dependents and allowance.\n"
        "4. Call estimate_yearly_cost for the 3 most promising plans using their usage level.\n"
        "5. If they take a specific drug or ask about doctors, referrals or approvals, call "
        "search_plan_documents with the plan_id.\n"
        "6. Recommend one plan in plain language, showing expected AND worst-case yearly cost, and "
        "mention the enrollment deadline.\n"
        "If anything is unclear, or the question is medical/legal/tax, call flag_for_advisor instead of guessing."
    )


@mcp.prompt()
def explain_this_plan(plan_id: str) -> str:
    """Explain one plan in simple language with no jargon."""
    return (
        f"Explain plan '{plan_id}' to someone who has never bought health insurance. Use list_plans data "
        "and search_plan_documents (with plan_id) for referrals and prescriptions. In under 150 words, cover: "
        "what the monthly premium and deductible mean, who it suits, and one thing to watch out for. "
        "Define any jargon you use (the decent://glossary resource has definitions)."
    )


@mcp.prompt()
def compare_two_plans(plan_a: str, plan_b: str, employee_id: str) -> str:
    """Compare two plans side by side for a specific employee."""
    return (
        f"Compare plans '{plan_a}' and '{plan_b}' for employee {employee_id}. Call get_employee_allowance, then "
        "estimate_yearly_cost for both plans at low, medium and high usage. Present a small table (expected "
        "and worst-case yearly cost per usage level), then say in two sentences which plan fits which kind of "
        "year. Do not make a medical judgment; offer flag_for_advisor if they want a person to review it."
    )


# ----------------------------------------------------------------------------- entrypoint
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ICHRA Employee Assistant MCP server (mock data)")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"[ichra-mcp] starting ({args.transport})", file=sys.stderr)
    if args.transport == "http":
        mcp.settings.host, mcp.settings.port = args.host, args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
