"""Recompute mt_poamount.mw_multiplication_factor from the material text.

Why this exists
---------------
The wattage rule used at ingest only read vendors who state the rating outright
("MODULE,615W,LR8-66HGD-615M,LONGI"). Jinko, Goldi, Redren and MSPVL encode it
in the part number instead ("MODULE,SOLAR,MM:JKM590N-72HL4-BDV,JINKO" is a
590 Wp panel), so those lines were stored with a null factor. Every MWp figure
on the Ordering Schedule requires `mw_multiplication_factor > 0`, so the panels
were invisible: about 2,244 MWp across 3.8M panels, which is most of the
unexplained Balance Ordering on the commissioned Khavda projects.

services/module_wattage.py now reads both forms. This script applies that rule
to rows already in the table, so the fix does not have to wait for a full SAP
re-ingest (which is a delete-and-replace of the whole PO table).

It is a straight recompute, not a guess: a row whose text states no rating keeps
a null factor and stays excluded.

Usage
-----
    python scripts/backfill_module_wattage.py              # dry run, prints the plan
    python scripts/backfill_module_wattage.py --apply      # writes
    python scripts/backfill_module_wattage.py --apply --all-materials

By default only rows whose text mentions a module/panel are touched. --all-materials
recomputes every row, which is what a future full ingest would do anyway.
"""
import argparse
import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from services.module_wattage import module_watts_with_rule, selftest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write the changes (default is a dry run)")
    ap.add_argument("--all-materials", action="store_true",
                    help="recompute every row, not only module/panel lines")
    args = ap.parse_args()

    selftest()          # fail loudly if the patterns have regressed
    db = SessionLocal()
    try:
        q = db.query(models.MTPOAmount)
        if not args.all_materials:
            like = models.MTPOAmount.short_text.ilike('%module%')
            q = q.filter(
                like
                | models.MTPOAmount.material_name.ilike('%module%')
                | models.MTPOAmount.short_text.ilike('%panel%')
                | models.MTPOAmount.material_name.ilike('%panel%'))
        rows = q.all()
        print(f"rows considered: {len(rows):,}")

        set_new, changed, cleared, untouched = [], [], [], 0
        by_rule: dict[str, int] = {}
        for r in rows:
            watts, rule = module_watts_with_rule(r.short_text or r.material_name)
            factor = None if watts is None else watts / 1_000_000
            old = r.mw_multiplication_factor

            if factor is None and old is None:
                untouched += 1
                continue
            if old is not None and factor is not None and abs(old - factor) < 1e-12:
                untouched += 1
                continue

            qty = float(r.po_quantities or 0.0)
            rec = (r, old, factor, qty, watts, rule)
            if old is None:
                set_new.append(rec)
                by_rule[rule or '?'] = by_rule.get(rule or '?', 0) + 1
            elif factor is None:
                cleared.append(rec)
            else:
                changed.append(rec)

        print(f"  already correct          : {untouched:,}")
        print(f"  factor NEWLY set         : {len(set_new):,}")
        print(f"  factor CHANGED           : {len(changed):,}")
        print(f"  factor CLEARED to null   : {len(cleared):,}")

        gained_mw = sum(q * w / 1e6 for _r, _o, _f, q, w, _n in set_new)
        print(f"\n  MWp made visible by the newly set rows: {gained_mw:,.1f}")
        if by_rule:
            print("  by rule: " + ", ".join(f"{k}={v}" for k, v in sorted(by_rule.items())))

        # A changed or cleared factor moves a number that was already on screen,
        # so both are printed in full rather than summarised.
        for label, group in (("CHANGED", changed), ("CLEARED", cleared)):
            if not group:
                continue
            print(f"\n  *** {label} ***")
            for r, old, factor, qty, watts, rule in group[:40]:
                o = f"{old * 1e6:.0f}W" if old else "null"
                n = f"{watts}W ({rule})" if watts else "null"
                print(f"    {o:>12} -> {n:<18} qty={qty:>10,.0f}  {str(r.short_text)[:52]}")
            if len(group) > 40:
                print(f"    ... and {len(group) - 40} more")

        if not args.apply:
            print("\nDRY RUN — nothing written. Re-run with --apply to commit.")
            return 0

        for r, _old, factor, qty, _w, _n in set_new + changed + cleared:
            r.mw_multiplication_factor = factor
            r.po_quantities_mw = (qty * factor) if factor is not None else None
        db.commit()
        print(f"\nCommitted {len(set_new) + len(changed) + len(cleared):,} rows.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
