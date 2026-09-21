"""One-time data fix for 6 projects whose OL (and, for some, Type/Category)
were blank in project_mapping, verified against the reference Khavda PDF
tracker (Data/Khavda FY 26-27 Solar Projects Module Deliveries_02-Sep-26.pdf)
during the 2026-09-20/21 module-deliveries audit.

This was originally applied as a one-off SQL UPDATE directly against the
local database and never captured as a script — so it never reached any
other environment. Running it there produced a genuine ~3,063 MWp gap in
Total Capacity against local (six projects' MWp effectively read as 0
without OL, since capacity_mwp = capacity_mwac * OL when capacity_mwdc is
blank), plus a missing DCR bucket in the Source Type breakdown (NHPC).

Matched by project_name_from_p6, NOT by numeric id — the id is a DB-assigned
sequence and is not guaranteed to be the same value across environments.
Idempotent and non-destructive: each field is only written if it is
currently blank/zero, so it never overwrites a legitimate value entered
since (e.g. a later, more specific mapping-sheet update).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
import models

# Verified against the PDF's own Capacity(MWac) x OL = Capacity(MWp) column
# for every row except LUDBAY, which the PDF does not cover at all.
FIXES = {
    "ACL_A01_HSAT_50MW_Group_NEW": {
        "ol": "1.35", "source_of_origin": "ALMM",
    },
    "AGE26BL_A03_HSAT_250MW_LTP_T4_AP_NEW": {
        "ol": "1.35", "category": "PPA", "source_of_origin": "China",
    },
    "ARE55L_A18_HSAT_600MW_PPA": {
        "ol": "1.35", "source_of_origin": "ALMM",
    },
    "ARE55L_S09_HSAT_400MW_PPA": {
        "ol": "1.35", "spv_name": "ARE55L", "source_of_origin": "ALMM",
    },
    "ASEJ6PL_S07_FT_300MW_PPA": {
        "ol": "1.36", "spv_name": "ASEJ6PL", "source_of_origin": "China",
    },
    "NHPC EPC 600 MW Khavda-I": {
        "ol": "1.50", "plot_no": "NHPC", "category": "NHPC",
        "mms_type": "HSAT", "source_of_origin": "DCR",
    },
    # Not in the Khavda PDF (a different site) — SPV only, derived from its
    # own P6 name, not a guess. OL/Type intentionally left blank; there is
    # no source for them.
    "ARE8L_LUDBAY_FT_150MW_PPA": {
        "spv_name": "ARE8L",
    },
}


def _blank(v):
    return v is None or str(v).strip().lower() in ("", "-", "na", "nan", "none", "0", "0.0")


def main():
    db = SessionLocal()
    updated = 0
    skipped = []
    missing = []
    for p6_name, fields in FIXES.items():
        mapping = db.query(models.ProjectMapping).filter(
            models.ProjectMapping.project_name_from_p6 == p6_name
        ).first()
        if not mapping:
            missing.append(p6_name)
            continue

        applied = {}
        for field, value in fields.items():
            if _blank(getattr(mapping, field, None)):
                setattr(mapping, field, value)
                applied[field] = value

        if applied:
            updated += 1
            print(f"  {p6_name}: {applied}")
        else:
            skipped.append(p6_name)

    db.commit()
    print(f"\nUpdated {updated} of {len(FIXES)} projects.")
    if skipped:
        print(f"Already populated, left as-is: {skipped}")
    if missing:
        print(f"Not found in this database (check project_name_from_p6 matches): {missing}")


if __name__ == "__main__":
    main()
