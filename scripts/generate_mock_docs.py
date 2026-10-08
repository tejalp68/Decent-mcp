"""Generate realistic-looking MOCK carrier plan documents for the RAG tool.

All content is fictional. Numbers come from data/plans.json so the documents
agree with the structured plan data. Formulary tiers differ per plan (seeded)
so searches like "is insulin covered" give different answers per plan.

Run:  python scripts/generate_mock_docs.py
"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS = {p["plan_id"]: p for p in json.loads((ROOT / "data" / "plans.json").read_text())}
DOC_PLANS = ["anthem_hmo_silver", "kaiser_hmo_silver", "uhc_hdhp_bronze_ca", "oscar_epo_gold_tx"]

DRUGS = [
    ("metformin", "generic"), ("lisinopril", "generic"), ("atorvastatin", "generic"),
    ("levothyroxine", "generic"), ("amlodipine", "generic"), ("omeprazole", "generic"),
    ("sertraline", "generic"), ("escitalopram", "generic"), ("losartan", "generic"),
    ("albuterol inhaler", "generic"), ("amoxicillin", "generic"), ("azithromycin", "generic"),
    ("gabapentin", "generic"), ("hydrochlorothiazide", "generic"), ("montelukast", "generic"),
    ("prednisone", "generic"), ("sumatriptan", "generic"), ("cetirizine", "generic"),
    ("insulin glargine", "brand"), ("insulin lispro", "brand"), ("semaglutide", "specialty"),
    ("adalimumab", "specialty"), ("etanercept", "specialty"), ("apixaban", "brand"),
    ("empagliflozin", "brand"), ("sitagliptin", "brand"), ("budesonide-formoterol inhaler", "brand"),
    ("rosuvastatin", "generic"), ("duloxetine", "generic"), ("bupropion", "generic"),
]


def formulary_section(plan, rng):
    lines = ["## Section 3. Prescription Drug Formulary", "",
             f"The {plan['name']} formulary groups drugs into four cost tiers. Tier 1 is the lowest cost. "
             "Drugs marked PA need prior authorization before the plan will pay. "
             "Drugs marked ST require you to try a lower-cost drug first (step therapy). "
             "The list below is reviewed every quarter and may change.", ""]
    for drug, kind in DRUGS:
        if kind == "generic":
            tier, notes = 1, ""
        elif kind == "brand":
            tier = rng.choice([2, 3])
            notes = rng.choice(["", "", "PA", "ST"])
        else:
            tier = 4
            notes = rng.choice(["PA", "PA, ST", "PA"])
        covered = rng.random() > 0.06
        if not covered:
            lines.append(f"- {drug}: NOT COVERED on this formulary. Ask your doctor about alternatives.")
            continue
        if plan["rx_generic_copay"] is None:
            cost = "you pay the full discounted price until the deductible is met, then coinsurance"
        else:
            copay = {1: plan["rx_generic_copay"], 2: plan["rx_generic_copay"] * 3,
                     3: plan["rx_generic_copay"] * 6, 4: f"{plan['coinsurance_pct']}% coinsurance"}[tier]
            cost = f"${copay} per 30-day fill" if tier < 4 else str(copay)
        extra = f" Requirements: {notes}." if notes else ""
        lines.append(f"- {drug}: Tier {tier}, {cost}.{extra}")
    return "\n".join(lines)


def build(plan_id):
    p = PLANS[plan_id]
    rng = random.Random(plan_id)
    pcp = f"${p['pcp_copay']} copay" if p["pcp_copay"] is not None else "full cost until deductible is met"
    spec = f"${p['specialist_copay']} copay" if p["specialist_copay"] is not None else "full cost until deductible is met"
    hsa = ("This is an HSA-eligible high deductible health plan. You may open a Health Savings Account "
           "and contribute pre-tax dollars, up to the annual IRS limit.") if p["hsa_eligible"] else \
          "This plan is not paired with a Health Savings Account."
    referral = {"HMO": "You must choose a primary care provider (PCP). Specialist visits require a referral from your PCP, otherwise the plan will not pay.",
                "EPO": "You do not need a referral to see a specialist, but you must stay inside the network. Out-of-network care is covered only in an emergency.",
                "PPO": "You do not need referrals. You can see out-of-network providers, but you will pay a higher deductible and coinsurance.",
                "HDHP": "You do not need referrals, but you must use in-network providers to get negotiated prices."}[p["plan_type"]]

    parts = [f"# {p['name']} - Evidence of Coverage (MOCK DOCUMENT)",
             f"Carrier: {p['carrier']}   Plan ID: {plan_id}   Type: {p['plan_type']}   Metal tier: {p['metal_tier']}",
             "This document is fictional and was generated for a student project. It does not describe a real insurance product.", "",
             "## Section 1. Summary of Benefits", "",
             f"Annual deductible (individual): ${p['deductible']:,}. Out-of-pocket maximum (individual): ${p['oop_max']:,}. "
             f"Coinsurance after deductible: you pay {p['coinsurance_pct']}% of allowed charges. "
             f"Primary care visit: {pcp}. Specialist visit: {spec}. "
             f"Generic prescriptions: {'${}'.format(p['rx_generic_copay']) + ' copay' if p['rx_generic_copay'] is not None else 'full discounted price until deductible is met'}. "
             "Preventive care such as annual checkups, flu shots and recommended screenings is covered at no cost to you when you use an in-network provider.",
             "", hsa, "",
             "## Section 2. How Your Network Works", "", referral,
             " Always confirm that a doctor, clinic or hospital is in the network before scheduling non-emergency care. "
             "Network directories are updated monthly, but providers can leave the network between updates. "
             "If you were told a provider was in the network and that was incorrect, contact member services and keep a record of the date and the person you spoke with.",
             "", formulary_section(p, rng), "",
             "## Section 4. Prior Authorization", "",
             "Some services and drugs must be approved in advance. Your provider normally submits the request. Standard decisions are made within 15 days and urgent requests within 72 hours. "
             "If a request is denied you have the right to an appeal. Services that commonly need prior authorization include advanced imaging such as MRI and CT scans, non-emergency inpatient stays, "
             "planned surgeries, durable medical equipment over $500, genetic testing and specialty drugs.",
             "", "## Section 5. Emergency and Urgent Care", "",
             f"Emergency room visits are covered at any hospital in the world if you reasonably believed your health was in serious danger. After you meet your deductible you pay {p['coinsurance_pct']}% coinsurance. "
             "If you are admitted to the hospital from the emergency room, call the plan within 48 hours. Urgent care centers are for illnesses that need quick attention but are not life-threatening, such as sprains, "
             "ear infections or minor cuts. Urgent care usually costs much less than the emergency room.",
             "", "## Section 6. Mental Health and Substance Use Care", "",
             "Therapy, psychiatry and substance use treatment are covered on the same terms as other medical care, as required by federal parity law. Telehealth therapy visits are covered when the provider is in the network. "
             "Inpatient mental health stays require prior authorization except in an emergency.",
             "", "## Section 7. Maternity and Newborn Care", "",
             "Prenatal visits, delivery and postpartum care are covered. A newborn is covered from birth for the first 30 days. You must add the baby to your plan within those 30 days to keep coverage going. "
             "Contact your employer's ICHRA administrator, because adding a dependent can change which plans are available and how your allowance applies.",
             "", "## Section 8. What Is Not Covered", "",
             "Cosmetic surgery, weight loss surgery unless medically necessary and pre-approved, long-term custodial care, experimental treatments, hearing aids for adults, routine dental and routine vision care for adults, "
             "and acupuncture are not covered. Services received outside the network on a plan that does not cover out-of-network care are not covered except in an emergency.",
             "", "## Section 9. Claims and Appeals", "",
             "In-network providers send claims to the plan directly. If you pay for care yourself, send the itemized bill and proof of payment within 12 months of the date of service. "
             "The plan will send an Explanation of Benefits showing what was billed, what the plan paid and what you owe. If you disagree with a decision, you can file an appeal within 180 days. "
             "After the internal appeal, you may request an independent external review.",
             "", "## Section 10. Premium Payments and ICHRA Reimbursement", "",
             "If your employer offers an Individual Coverage HRA, you pay the plan's monthly premium and your employer reimburses you up to your monthly allowance. "
             "Keep your premium receipts. Any part of the premium above your allowance is your responsibility. If your allowance is larger than the premium, the unused amount is not paid to you as cash. "
             "Premiums reimbursed through an ICHRA are not taxed as income as long as you are enrolled in individual market coverage. You must tell your employer if you become eligible for Medicare or other employer coverage.",
             ]
    # Pad with a repeated-but-varied administrative appendix so documents look like real, long packets
    for i in range(1, 9):
        parts += ["", f"## Appendix {i}. Member Rights and Administrative Notes (Part {i})", "",
                  f"Members of the {p['name']} have the right to receive information about the plan, its providers and its policies in clear language. Members can ask for a printed copy of any "
                  "document at no cost. Interpreter services are available in more than 150 languages. The plan does not discriminate on the basis of race, color, national origin, disability, age, sex, "
                  "gender identity or sexual orientation. Members can file a complaint (grievance) by phone or in writing, and the plan must acknowledge it within 5 business days. "
                  "Coordination of benefits rules apply when you have more than one health plan: the plan that is primary pays first and the secondary plan may pay part of what is left. "
                  "Subrogation rules allow the plan to recover payments if you receive money from another party for an injury. Fraud, such as lending your member card, can lead to loss of coverage. "
                  "Privacy notices explain how your health information is used, and you may ask for an accounting of disclosures. Plan documents can change. Material changes are communicated at least 60 days before they take effect."]
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    for pid in DOC_PLANS:
        path = out / f"{pid}.md"
        path.write_text(build(pid))
        print(f"wrote {path.relative_to(ROOT)} ({len(path.read_text().split())} words)")
