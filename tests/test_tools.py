"""Direct unit tests of the tool functions (no MCP transport). Run: python -m pytest -q  (or python tests/test_tools.py)"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as e:
        return str(e)
    raise AssertionError("expected ValueError")


def test_allowance():
    r = server.get_employee_allowance("emp_001")
    assert r["monthly_allowance"] == 450 and r["zip_code"] == "94107"
    assert "emp_001" in raises(server.get_employee_allowance, "nope")


def test_list_plans():
    r = server.list_plans("94107", 34, 1, 450)
    assert len(r["plans"]) == 7
    assert [p["monthly_premium"] for p in r["plans"]] == sorted(p["monthly_premium"] for p in r["plans"])
    assert all("employee_pays_per_month_after_allowance" in p for p in r["plans"])
    assert "Supported zip codes" in raises(server.list_plans, "00000", 30)


def test_search():
    r = server.search_plan_documents("is metformin covered", "anthem_hmo_silver")
    assert r["passages"] and "metformin" in r["passages"][0]["text"]
    assert r["tokens_returned"] < r["tokens_in_full_document"]
    assert "Plans with documents" in raises(server.search_plan_documents, "x", "kaiser_hmo_bronze")


def test_estimate_orders_sensibly():
    low = server.estimate_yearly_cost("emp_001", "anthem_hmo_silver", "low")
    high = server.estimate_yearly_cost("emp_001", "anthem_hmo_silver", "high")
    assert high["expected_out_of_pocket_care"] > low["expected_out_of_pocket_care"]
    assert high["expected_out_of_pocket_care"] <= 8000                       # capped at OOP max
    assert high["worst_case_total_yearly_cost"] >= high["expected_total_yearly_cost"]
    assert "not sold in the employee's zip" in raises(server.estimate_yearly_cost, "emp_001", "oscar_epo_gold_tx")


def test_flag(tmp_path=None):
    flags = server.DATA / "advisor_flags.json"
    before = json.loads(flags.read_text()) if flags.exists() else []
    r = server.flag_for_advisor("emp_002", "Wants to confirm his cardiologist is in network.", "normal")
    after = json.loads(flags.read_text())
    assert len(after) == len(before) + 1 and r["ticket_id"].startswith("TKT-")
    flags.write_text(json.dumps(before, indent=2)) if before else flags.unlink()   # keep repo clean
    assert "specific reason" in raises(server.flag_for_advisor, "emp_002", "help")


def test_resources_and_prompts():
    assert "ICHRA" in server.glossary()
    assert json.loads(server.company_policy("brightpt"))["name"] == "Bright Physical Therapy"
    assert "emp_004" in server.pick_my_plan("emp_004")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
