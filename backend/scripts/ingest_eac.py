"""
Load the BESS EAC's SAP extracts from Data/EAC_BEES:

    CJI3*.xlsx            -> Incurred  (Val/COArea Crcy, Value Type 11 excluded)
    S_alr_87013558*.xlsx  -> Committed (Val/COArea Crcy, POrd and PReq)

The newest file of each is used. Approved Capex comes from
"EAC Format_AND_WBS Structure.xlsx" in the same folder and is read when the
EAC is opened, so it needs no load step. See services/bess_eac.py.

    cd backend && python scripts/ingest_eac.py

Afterwards it prints each BESS project's totals, so a wrong or partial file
shows up here rather than on screen.
"""
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")


def main() -> None:
    from auto_migrate import auto_upgrade_schema
    auto_upgrade_schema()                      # creates the EAC tables on a fresh checkout

    from database import SessionLocal
    from services import bess_eac

    db = SessionLocal()
    try:
        loaded = bess_eac.ingest_eac_sap(db)
        print(f"Incurred : {loaded['incurred_file']} - {loaded['incurred_lines']} lines "
              f"(stock-side Value Type 11 excluded: {loaded['incurred_excluded_stock_lines']}; "
              f"postings {loaded['incurred_posting_from']} to {loaded['incurred_posting_to']})")
        print(f"Committed: {loaded['committed_file']} - {loaded['committed_lines']} lines "
              f"(POrd {loaded['committed_porder_lines']}, PReq {loaded['committed_preq_lines']}; "
              f"which count is set per project in the EAC view)")
        print()
        print(f"{'Project':<22} {'Approved':>11} {'Incurred':>10} {'Committed':>11} {'EAC':>11} {'Variance':>11}")
        f = lambda v: "-" if v is None else f"{v:,.2f}"
        for pid in bess_eac.ROOTS:
            total = next(r for r in bess_eac.build(db, pid)["rows"] if r["key"] == "L63")
            print(f"{pid:<22} {f(total['approved']):>11} {f(total['incurred']):>10} "
                  f"{f(total['committed']):>11} {f(total['eac']):>11} {f(total['variance']):>11}")
        print("\nINR Cr. EAC = Incurred + Committed + Balance to Completion.")
    except FileNotFoundError as e:
        print(f"FAILED: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
