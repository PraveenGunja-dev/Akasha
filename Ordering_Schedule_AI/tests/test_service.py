"""Service checks: train/serve parity, response contract, guardrail, errors.

    cd Ordering_Schedule_AI && AI_PROVIDER=none python -m pytest tests -q
"""
import os
import sys
from pathlib import Path

import pandas as pd
from datetime import date
import pytest

os.environ["AI_PROVIDER"] = "none"  # template explanations: deterministic, offline
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import parsers as P  # noqa: E402
from features import FEATURES, derive  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from service.app import ENGINE, app  # noqa: E402

client = TestClient(app)
UC1 = {"project_id": "ARE55L_S03", "project_name": "MSEDCL PPA Ph-3", "phase": "PH-1", "vendor_type": "ALMM",
       "priority": "STANDARD", "capacity_mwp": 203, "balance_ordering": 203, "inventory": 0, "receipt": 0,
       "under_transit": 0, "lta_date": "2026-10-08", "scod_date": "2026-10-08", "ftc_date": "2027-05-19"}
UC2 = {"project_id": "ARE55L_S03", "project_name": "string", "phase": "Ph-1", "category": "PPA",
       "capacity_mwp": 675, "balance_ordering": 675, "inventory": 0, "receipt": 0, "under_transit": 0,
       "lta_date": "2026-10-08", "scod_date": "2026-10-08", "ftc_date": "2026-10-08", "ftc_risk_flag": False,
       "current_priority": "STANDARD"}


def test_train_serve_parity():
    """The API's feature path reproduces the training features exactly."""
    as_of = P.read_as_of(ROOT / "data/raw")
    pf = pd.read_csv(ROOT / "data/interim/phase_frame.csv",
                     parse_dates=["ftc_date", "lta", "scod", "aop", "p6_data_date", "deadline_date"])
    pf["sap_mapped"] = pf["ol"].notna()
    tx = derive(pf, as_of)
    for i, p in pf[pf["ol"].notna()].iterrows():
        q = lambda c: float(p[c]) if p[c] == p[c] else 0.0  # noqa: E731
        req = {"project_id": p.p6_name, "project_name": p.project, "phase": p.phase, "vendor_type": p.vendor_type,
               "capacity_mwp": float(p.capacity_mwac * p.ol), "capacity_mwac": float(p.capacity_mwac),
               "ol": float(p.ol), "balance_ordering": q("balance_mwp"), "inventory": q("inventory_mwp"),
               "receipt": q("receipt_mwp"), "under_transit": q("transit_mwp"),
               "lta_date": p.lta.date().isoformat() if pd.notna(p.lta) else None,
               "scod_date": p.scod.date().isoformat() if pd.notna(p.scod) else None,
               "ftc_date": p.ftc_date.date().isoformat()}
        proj, prow = ENGINE.match(req["project_id"], req["project_name"], req["capacity_mwp"], req["phase"])
        assert proj is not None and proj["row_id"] == p.row_id
        xs = derive(ENGINE.base_row(req, proj, prow, None)[0], as_of).iloc[0]
        for f in FEATURES:
            a, b = xs[f], tx.loc[i, f]
            assert (pd.isna(a) and pd.isna(b)) or abs(a - b) < 1e-6, (p.project, p.phase, f, a, b)


def test_order_tc_contract():
    r = client.post("/api/ai/v1/order-tc-forecast?explain=true", json=UC1)
    assert r.status_code == 200
    d = r.json()
    for k in ("recommended_order_date", "predicted_tc_date", "confidence", "risk_level", "order_by_date",
              "order_now", "predicted_tc_date_p90", "projected_ftc_date", "deadline_breach_days", "rule_engine",
              "order_by_shift_vs_rule_days", "priority", "project", "explanation"):
        assert k in d
    assert d["rule_engine"] == {"order_by_date": "2026-12-27", "tc_date": "2027-04-04"}  # FTC-45, -98 (ALMM)
    assert d["project"]["p6_name"] == "ARE55L_S03_HSAT_500MW_MERCHANT"
    parts = [b["days"] for b in d["root_cause"]["breakdown"] if b["days"] is not None]
    assert sum(parts) == d["root_cause"]["predicted_ftc_shift_days"]  # segments partition the shift
    assert d["predicted_tc_date"] <= d["predicted_tc_date_p90"]
    assert d["explanation"]["mode"] == "template" and d["explanation"]["text"]
    assert d["explanation"]["consistency_flags"] == []


def test_priority_contract_and_guardrail():
    r = client.post("/api/ai/v1/priority-predict?explain=true", json=UC2)
    assert r.status_code == 200
    d = r.json()
    assert d["priority_class"] in ("P1", "P2", "STANDARD")
    assert abs(sum(d["class_probabilities"].values()) - 1) < 0.01
    assert 0 <= d["priority_score"] <= 100
    # PPA charging after SCOD with transmission ready is P1 by business rule.
    assert d["priority_class"] == "P1"
    assert d["guardrail"] is None or d["guardrail"]["applied"]


def test_group_is_lowest_priority():
    d = client.post("/api/ai/v1/priority-predict", json={**UC2, "category": "Group"}).json()
    assert d["priority_class"] == "STANDARD"


SECI = {"project_id": "ASEJ6PL_S07", "project_name": "SECI VIII PPA", "phase": "Ph-I", "vendor_type": "China",
        "priority": "STANDARD", "capacity_mwp": 408, "balance_ordering": 408, "inventory": 0, "receipt": 0,
        "under_transit": 0, "lta_date": "2027-01-31", "scod_date": "2027-03-02", "ftc_date": "2026-12-21"}


def test_monthly_requirement_phase_timed():
    d = client.post("/api/ai/v1/order-tc-forecast", json=SECI).json()
    mr = d["monthly_requirement"]
    # Both plans distribute exactly the balance, never more.
    assert mr["rule_engine"]["total_mwp"] == mr["ai"]["total_mwp"] == 408.0
    # Rule cells sit in the TC month (FTC - 45 d), as on the sheet: the requested Ph-I FTC 21-Dec-26 -> Nov-26.
    assert mr["rule_engine"]["months"][0]["month"] == "Nov-26"
    assert mr["ai"]["timed_by"] == "FTC date"
    first = mr["ai"]["months"][0]
    assert first["order_by_date"] == d["order_by_date"]          # monthly plan and headline agree
    assert d["lead_time"]["rule_engine_days"] == 136


def test_monthly_requirement_site_paced():
    """TPL-D: 30 MWp balance, 137 MWp in stock, structure pace from P6 -> needed as structures finish."""
    body = {"project_id": "ARE8L_A02", "project_name": "TPL-D PPA", "phase": "Single phase", "vendor_type": "ALMM",
            "capacity_mwp": 202.5, "capacity_mwac": 150, "ol": 1.35, "balance_ordering": 30, "inventory": 137,
            "ftc_date": "2026-11-07"}
    d = client.post("/api/ai/v1/order-tc-forecast", json=body).json()
    ai = d["monthly_requirement"]["ai"]
    assert ai["timed_by"] == "Site speed" and ai["total_mwp"] == 30.0
    assert ai["months"][0]["need_date"] > "2027-01-01"           # stock covers the next months first
    assert d["order_by_date"] == ai["months"][0]["order_by_date"]


def test_monthly_plan_by_contractor():
    d = client.get("/api/ai/v1/monthly-plan", params={"epc": "Amara Raja"}).json()
    g = d["groups"][0]
    assert g["capacity_mwp_total"] == 641.25                     # SUM of MWac x OL, not a split
    assert len(g["projects"]) == 4
    assert sum(m["required_at_site_mwp"] for m in g["monthly_total"]["ai"]) == pytest.approx(30.0, abs=0.2)
    assert client.get("/api/ai/v1/monthly-plan", params={"epc": "nobody"}).status_code == 404


def test_batch_csv_keeps_the_sheet_and_appends_ai_columns():
    import csv, io  # noqa: E401
    from service.batch import AI_COLUMNS
    raw = (ROOT / "data/raw/Module Deliveries.csv").read_bytes()
    r = client.post("/api/ai/v1/batch/module-deliveries/csv?explain=none",
                    files={"file": ("Module Deliveries.csv", raw, "text/csv")})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    src = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    out = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"), newline="")))
    assert len(out) == len(src)                                   # every row kept, in place
    h = P.header_index(out)
    assert out[h][-len(AI_COLUMNS):] == AI_COLUMNS
    tpl = next(x for x in out if len(x) > 2 and x[2] == "ARE8L_A02_HSAT_150MW_PPA_TPL")
    ai = dict(zip(AI_COLUMNS, tpl[-len(AI_COLUMNS):]))
    assert ai["AI Status"].startswith("Scored")
    # PPA past SCOD and past an LTA that came after SCOD: P1 by the penalty rule.
    assert ai["AI Priority"] == "P1" and ai["AI Priority Set By"].startswith("PPA penalty rule")
    # Site-paced from today: check the quantity and its link to the order date, not calendar dates.
    plan = ai["AI Month wise Module Requirement at Site (MWp / MWac)"]
    import re
    assert sum(float(x) for x in re.findall(r"\[ ([\d.]+) /", plan)) == pytest.approx(30.0, abs=0.2)
    assert plan.split("order by ")[1][:9] == ai["AI Module Order Date"]


def test_batch_json_matches_csv_and_rejects_bad_input():
    import json
    body = json.loads((ROOT / "samples/Module Deliveries.json").read_text(encoding="utf-8"))
    d = client.post("/api/ai/v1/batch/module-deliveries/json?explain=none", json=body).json()
    assert len(d["rows"]) == len(body["rows"]) == 49
    assert d["summary"]["scored"] == 32
    tpl = next(x for x in d["rows"] if x["P6 Name"] == "ARE8L_A02_HSAT_150MW_PPA_TPL")
    assert tpl["ai_detail"]["phases"][0]["uc1"]["order_by_date"]
    assert tpl["AI Module Order Date"] == date.fromisoformat(
        tpl["ai_detail"]["phases"][0]["uc1"]["order_by_date"]).strftime("%d-%b-%y")
    assert client.post("/api/ai/v1/batch/module-deliveries/json", json={"rows": [{"x": 1}]}).status_code == 422
    assert client.post("/api/ai/v1/batch/module-deliveries/csv",
                       files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}).status_code == 422


def test_akasha_dashboard_export():
    import json
    src = ROOT / "data/raw/akasha_ordering_schedule_full.json"
    raw = src.read_bytes()
    r = client.post("/api/ai/v1/batch/akasha-dashboard",
                    files={"file": (src.name, raw, "application/json")})
    assert r.status_code == 200
    out = ROOT / r.headers["x-output-path"]
    assert out.name == "AIAkashaOrderingSchedule_final.json" and out.exists()
    d, original = r.json(), json.loads(raw)
    assert d["block_plan"] == original["block_plan"]                  # the rest of the document is untouched
    projects = d["ordering_schedule"]["projects"]
    assert len(projects) == 49
    for p, src_p in zip(projects, original["ordering_schedule"]["projects"]):
        assert set(p) - set(src_p) == {"ai_priority", "ai_monthly_order_tc_forecast"}   # exactly two new fields
    seci = next(p for p in projects if p["project_name"] == "SECI VIII PPA")
    assert seci["ai_priority"]["priority_class"] == "P1" and seci["ai_priority"]["reasons"]
    assert seci["ai_priority"]["explanation"]["text"] and seci["ai_monthly_order_tc_forecast"]["explanation"]["text"]
    m = seci["ai_monthly_order_tc_forecast"]
    assert len(m["phases"]) == 6
    assert m["monthly_requirement"]["ai"]["months"][0]["order_by_date"] == m["order_by_date"]
    assert m["monthly_requirement"]["ai"]["total_mwp"] == 408.0
    # Both use cases read the same category: the priority inside UC1 matches ai_priority.
    for p in projects:
        if (p["ai_monthly_order_tc_forecast"]["status"] == "scored"
                and p["ai_monthly_order_tc_forecast"]["phase"] == p["ai_priority"]["phase"]):
            assert p["ai_monthly_order_tc_forecast"]["priority"]["ai"] == p["ai_priority"]["priority_class"], p["sr"]
    charged = [p for p in projects if p["ftc_all_charged"]]
    assert charged and all(p["ai_priority"]["status"] == "not_scored" for p in charged)
    assert client.post("/api/ai/v1/batch/akasha-dashboard/json", json={"x": 1}).status_code == 422


def _fake_reviewer(monkeypatch, reply: dict):
    """The governance LLM returns `reply`; the explanation LLM stays off (template)."""
    from service import explain, governance
    def fake(system, facts):
        if system.startswith("You are Akasha Intelligence AI Governance Layer"):
            assert "Module Deliveries data (planner sheet, as of 9 Oct 2026)" in facts
            return reply, "test"
        return None
    monkeypatch.setattr(explain, "_call_llm", fake)
    return governance


def test_v1_routes_keep_the_original_logic():
    for path, body in (("order-tc-forecast", UC1), ("priority-predict", UC2)):
        v1 = client.post(f"/api/ai/v1/{path}_v1", json=body).json()
        new = client.post(f"/api/ai/v1/{path}", json=body).json()
        assert "llm_review" not in v1["model"]
        assert new["model"].pop("llm_review")["status"] == "NOT_REVIEWED"     # no LLM in tests
        assert new == v1                                                       # same structure and values


def test_review_correction_flows_through_uc1(monkeypatch):
    base = client.post("/api/ai/v1/order-tc-forecast_v1", json=SECI).json()
    later = (pd.Timestamp(base["order_by_date"]) + pd.Timedelta(days=30)).date().isoformat()
    _fake_reviewer(monkeypatch, {"ai_priority": {}, "ai_monthly_order_tc_forecast": {
        "order_by_date": later, "predicted_tc_date": "2026-01-01"},     # TC before the order: must be rejected
        "ai_review_status": "CORRECTED", "ai_review_reason": "Quota full in the planned month."})
    d = client.post("/api/ai/v1/order-tc-forecast?explain=true", json=SECI).json()
    rv = d["model"]["llm_review"]
    assert rv["status"] == "CORRECTED" and rv["corrections"][0]["field"] == "order_by_date"
    assert any(r.startswith("predicted_tc_date") for r in rv["rejected"])
    assert d["order_by_date"] == later and d["recommended_order_date"] == later
    assert d["predicted_tc_date"] > base["predicted_tc_date"]                   # TC follows the later order
    parts = [b["days"] for b in d["root_cause"]["breakdown"] if b["days"] is not None]
    assert sum(parts) == d["root_cause"]["predicted_ftc_shift_days"] and min(parts) >= 0
    assert set(d) - {"explanation"} == set(base)                                # same response structure
    assert "governance review corrected order_by_date" in d["explanation"]["rule_vs_ai_assessment"]


def test_review_cannot_downgrade_ppa_penalty(monkeypatch):
    _fake_reviewer(monkeypatch, {"ai_priority": {"priority_class": "P2"}, "ai_monthly_order_tc_forecast": {},
                                 "ai_review_status": "CORRECTED", "ai_review_reason": "test"})
    d = client.post("/api/ai/v1/priority-predict", json=UC2).json()               # PPA past SCOD -> guardrail P1
    assert d["priority_class"] == "P1" and d["model"]["llm_review"]["status"] == "VALIDATED"
    assert d["model"]["llm_review"]["rejected"]
    g = client.post("/api/ai/v1/priority-predict?explain=true", json={**UC2, "category": "Group"}).json()
    assert g["priority_class"] == "P2" and g["model"]["llm_review"]["corrections"][0]["ml_value"] == "STANDARD"


@pytest.mark.parametrize("path,body,code", [
    ("order-tc-forecast", {**UC1, "vendor_type": "XYZ"}, 422),
    ("order-tc-forecast", {k: v for k, v in UC1.items() if k != "ftc_date"}, 422),
    ("priority-predict", {**UC2, "category": "Other"}, 422),
    ("order-tc-forecast", {**UC1, "project_id": "NOPE_X01", "project_name": ""}, 200),
])
def test_errors_and_unknown_projects(path, body, code):
    r = client.post(f"/api/ai/v1/{path}", json=body)
    assert r.status_code == code
    if code == 200:
        assert r.json()["project"] is None and r.json()["model"]["assumptions"]
