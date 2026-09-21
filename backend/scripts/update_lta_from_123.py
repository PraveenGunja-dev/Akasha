"""Populate project_mapping.lta_date (LTA) and .manual_scod (SCOD) from the
connectivity export (Data/123_export.xlsx).

The export carries one row per phase/financing tranche, so a project appears
several times with a different ECOD (and sometimes SCOD) each. Both LTA and
SCOD are the project's LATEST commitment, so each is the MAX across every row
belonging to that project — the same "latest phase governs" rule already used
for Connectivity Phase and AOP (user decision 2026-09-20).

Rows are resolved to a mapping FIRST and only then aggregated, because the same
project is spelled several ways in the sheet ("ASEJ6PL_S07_FT_300MW_PPA" vs
"ASEJ6PL_S07_FT_300MW", and P6 adds "_Commissioned" once a project is live).
Grouping on the raw name string instead left those aliases as separate groups
that each wrote to the same mapping in turn, so the value that survived was the
one written last rather than the largest.

Matching runs in tiers, most specific first (user decision 2026-09-21: check
every project, mapped properly, rather than skipping whenever the P6 name
doesn't match verbatim):
  1. P6 name, normalised (case/whitespace/hyphen/underscore-insensitive, with
     or without "_Commissioned") — e.g. the sheet's "ACL_A01- E_FT_25MW_GROUP
     NEW" against the mapping's "ACL_A01_E_FT_25MW_GROUP_NEW".
  2. SPV + Block, normalised ("S02b" == "S2B"), which the sheet always carries
     even on rows with no P6 name at all — resolves e.g. every "MSEDCL PPA
     Ph-3" row to its correct one of 5 candidate projects.
  3. If SPV+Block still matches more than one mapping (a plot split into
     several differently-sized sub-projects), narrow by the sheet's own
     "Solar" capacity (MW) against capacity_mwac, nearest within 5 MW.
  4. The "Project" display label, only when it happens to be unique — it's a
     shared portfolio name on most rows, so this rarely fires and never
     guesses across a shared one.
Whatever doesn't resolve uniquely is skipped and reported, not guessed.
"""
import re
import sys
import os
from collections import defaultdict
from datetime import timedelta

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
import models


def _parse_date(val):
    if pd.isna(val) or str(val).strip() in ('', 'nan', '-'):
        return None
    try:
        return pd.to_datetime(val)
    except Exception:
        return None


def _norm_name(s):
    """Case/whitespace/hyphen/underscore-insensitive form of a P6 name, so
    'ACL_A01- E_FT_25MW_GROUP NEW' and 'ACL_A01_E_FT_25MW_GROUP_NEW' compare equal."""
    if not s:
        return ''
    return re.sub(r'[\s_\-]+', '', str(s).upper())


def _norm_plot(s):
    """'S02b'/'A01e'/'S2B' -> a canonical (letters, digits-no-leading-zero, trailing letters)
    form, so the sheet's "Block" and the mapping's "Plot" compare equal despite
    zero-padding differences."""
    if not s:
        return ''
    s = re.sub(r'[\s\-]+', '', str(s).upper())
    m = re.match(r'^([A-Z]+)0*(\d+)([A-Z]*)$', s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return s


def _parse_scod(scod_val, project_lta):
    """A SCOD cell is either a literal date, or an "LTA"/"LTA+ND"/"LTA-ND"
    formula relative to the PROJECT's final LTA (its max ECOD), not to the
    ECOD sitting on that particular row. Returns (date, is_lta).
    """
    if pd.isna(scod_val) or str(scod_val).strip() in ('', 'nan', '-'):
        return None, False
    literal = _parse_date(scod_val)
    if literal is not None:
        return literal, False
    text = str(scod_val).upper().strip()
    if 'LTA' not in text or project_lta is None:
        return None, False
    m = re.search(r'LTA\s*([+-])\s*(\d+)', text)
    if m:
        sign = 1 if m.group(1) == '+' else -1
        return project_lta + timedelta(days=sign * int(m.group(2))), True
    return project_lta, True  # bare "LTA" means the same date as LTA


def main():
    db = SessionLocal()
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "123_export.xlsx")

    print(f"Reading {file_path}")
    try:
        df = pd.read_excel(file_path, header=4)
    except Exception as e:
        print(f"Failed to read excel: {e}")
        return

    cols = {}
    for col in df.columns:
        val = str(df.at[0, col]).strip()
        cols[val] = col
    p6_col = cols.get('P6 project Name')
    project_col = cols.get('Project')
    spv_col = cols.get('SPV')
    block_col = cols.get('Block')
    solar_col = cols.get('Solar')
    ecod_col = cols.get('ECOD')
    scod_col = cols.get('SCOD')

    if not ecod_col:
        print("Could not find ECOD column in row 0")
        return

    all_mappings = db.query(models.ProjectMapping).all()
    by_p6_norm = defaultdict(list)
    by_project = defaultdict(list)
    by_spv_block = defaultdict(list)
    for m in all_mappings:
        if m.project_name_from_p6:
            by_p6_norm[_norm_name(m.project_name_from_p6)].append(m)
            stripped = m.project_name_from_p6.replace('_Commissioned', '')
            if stripped != m.project_name_from_p6:
                by_p6_norm[_norm_name(stripped)].append(m)
        if m.project:
            by_project[m.project].append(m)
        if m.spv_name and m.plot_no:
            by_spv_block[(_norm_name(m.spv_name), _norm_plot(m.plot_no))].append(m)

    unresolved = set()
    ambiguous = set()

    def resolve(p6_name, project, spv, block, solar_mw):
        """Every mapping a sheet row belongs to (possibly several duplicates)."""
        if p6_name:
            found = by_p6_norm.get(_norm_name(p6_name))
            if found:
                return found

        if spv and block:
            candidates = by_spv_block.get((_norm_name(spv), _norm_plot(block)), [])
            if len(candidates) == 1:
                return candidates
            if len(candidates) > 1:
                if solar_mw is not None:
                    scored = sorted(candidates, key=lambda m: abs(float(m.capacity_mwac or 0) - solar_mw))
                    if abs(float(scored[0].capacity_mwac or 0) - solar_mw) <= 5:
                        return [scored[0]]
                ambiguous.add((p6_name, f"SPV={spv} Block={block}", len(candidates)))
                return []

        if project:
            candidates = by_project.get(project, [])
            if len(candidates) == 1:
                return candidates
            if len(candidates) > 1:
                ambiguous.add((p6_name, project, len(candidates)))
                return []

        unresolved.add((p6_name, project))
        return []

    def row_keys(idx):
        row = df.iloc[idx]
        get = lambda c: (str(row.get(c, '')).strip() if c else '')
        p6_name = get(p6_col) or None
        project = get(project_col) or None
        spv = get(spv_col) or None
        block = get(block_col) or None
        for bad in ('nan',):
            if p6_name == bad: p6_name = None
            if project == bad: project = None
            if spv == bad: spv = None
            if block == bad: block = None
        solar_val = row.get(solar_col) if solar_col else None
        try:
            solar_mw = float(solar_val) if solar_val is not None and not pd.isna(solar_val) else None
        except (ValueError, TypeError):
            solar_mw = None
        return row, p6_name, project, spv, block, solar_mw

    # Pass 1 — settle each project's LTA as the max ECOD over every row that
    # resolves to it, whichever alias or SPV+Block match that row was found by.
    agg: dict[int, dict] = {}
    for idx in range(1, len(df)):
        row, p6_name, project, spv, block, solar_mw = row_keys(idx)
        if not (p6_name or project or (spv and block)):
            continue
        ecod = _parse_date(row.get(ecod_col))
        for mapping in resolve(p6_name, project, spv, block, solar_mw):
            a = agg.setdefault(mapping.id, {"mapping": mapping, "ecod": None, "scod": None, "scod_is_lta": False})
            if ecod is not None and (a["ecod"] is None or ecod > a["ecod"]):
                a["ecod"] = ecod

    # Pass 2 — SCOD, now that every project's final LTA is known, since an
    # "LTA+N Days" cell is relative to that.
    for idx in range(1, len(df)):
        row, p6_name, project, spv, block, solar_mw = row_keys(idx)
        if (not (p6_name or project or (spv and block))) or not scod_col:
            continue
        for mapping in resolve(p6_name, project, spv, block, solar_mw):
            a = agg.get(mapping.id)
            if a is None:
                continue
            scod, is_lta = _parse_scod(row.get(scod_col), a["ecod"])
            if scod is not None and (a["scod"] is None or scod > a["scod"]):
                a["scod"] = scod
                a["scod_is_lta"] = is_lta

    updated_lta = updated_scod = 0
    for a in agg.values():
        mapping = a["mapping"]
        if a["ecod"] is not None:
            mapping.lta_date = a["ecod"]
            updated_lta += 1
        if a["scod"] is not None:
            mapping.manual_scod = a["scod"]
            mapping.manual_scod_is_lta = a["scod_is_lta"]
            updated_scod += 1

    db.commit()
    print(f"Updated {updated_lta} records with LTA dates (max ECOD per project).")
    print(f"Updated {updated_scod} records with SCOD dates (literal, or LTA-relative to that max).")
    if ambiguous:
        print(f"Skipped {len(ambiguous)} row group(s) — could not resolve to exactly one project:")
        for p6, key, n in sorted(ambiguous, key=lambda x: str(x[1])):
            print(f"  - p6={p6!r} {key} matches {n} mapping rows")
    if unresolved:
        print(f"Skipped {len(unresolved)} row group(s) with no matching mapping at all:")
        for p6, proj in sorted(unresolved, key=lambda x: str(x[1])):
            print(f"  - p6={p6!r} project={proj!r}")


if __name__ == "__main__":
    main()
