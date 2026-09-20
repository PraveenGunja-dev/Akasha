import re
import sys
import os
import pandas as pd
from datetime import timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
import models


def _parse_scod(scod_val, project_lta):
    """A row's SCOD cell is either a literal date, or an "LTA"/"LTA+ND"/"LTA-ND"
    formula relative to the PROJECT's final LTA (max ECOD across all its rows,
    not this row's own ECOD). Returns (date, is_lta) or (None, False).
    """
    if pd.isna(scod_val) or str(scod_val).strip() in ('', 'nan', '-'):
        return None, False
    try:
        return pd.to_datetime(scod_val), False
    except Exception:
        pass
    text = str(scod_val).upper().strip()
    if 'LTA' not in text or project_lta is None:
        return None, False
    m = re.search(r'LTA\s*([+-])\s*(\d+)', text)
    if m:
        sign = 1 if m.group(1) == '+' else -1
        return project_lta + timedelta(days=sign * int(m.group(2))), True
    return project_lta, True  # bare "LTA"


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

    p6_col = project_col = ecod_col = scod_col = None
    for col in df.columns:
        val = str(df.at[0, col]).strip()
        if val == 'P6 project Name':
            p6_col = col
        elif val == 'Project':
            project_col = col
        elif val == 'ECOD':
            ecod_col = col
        elif val == 'SCOD':
            scod_col = col

    if not ecod_col:
        print("Could not find ECOD column in row 0")
        return

    # The connectivity export carries one row per phase/financing tranche, so a
    # single project can appear several times with a different ECOD (and SCOD)
    # each — e.g. AGE26AL_A16_FT_333MW_PPA: ECOD 31-Mar-26, 31-Mar-26, 30-Apr-26.
    # Overwriting mapping.lta_date/manual_scod row-by-row made the result
    # whichever row happened to be LAST in the file, not the latest date —
    # wrong on 5 of 24 ECOD-affected projects, by more than a quarter on some.
    # Both LTA and SCOD are the project's LATEST commitment across its rows, so
    # each is the max of its candidates, computed before any write happens
    # (user decision 2026-09-20) — the same "latest phase governs" rule this
    # file already uses for Connectivity Phase and AOP.
    #
    # SCOD is taken ONLY from this sheet (a literal date, or "LTA+/-N Days") or
    # a direct manual entry — never a live trial-run finish or a TC network
    # edge date, which are different, unrelated commitments (user decision
    # 2026-09-20; enforced in routers/module_deliveries.py's SCOD cascade, not
    # here). An "LTA+/-N Days" cell means relative to the project's own final
    # LTA (the max ECOD just computed), not that individual row's own ECOD —
    # so this runs as two passes: first settle every project's max ECOD, then
    # resolve each row's SCOD candidate against that finalized value.
    groups: dict[str, dict] = {}
    for idx in range(1, len(df)):
        row = df.iloc[idx]
        p6_name = str(row.get(p6_col, '')).strip() if p6_col else ''
        project = str(row.get(project_col, '')).strip() if project_col else ''
        ecod_val = row.get(ecod_col)

        p6_name = p6_name if p6_name and p6_name != 'nan' else None
        project = project if project and project != 'nan' else None
        key = p6_name or project
        if not key:
            continue

        ecod_date = None
        if not (pd.isna(ecod_val) or str(ecod_val).strip() in ('', 'nan')):
            try:
                ecod_date = pd.to_datetime(ecod_val)
            except Exception:
                pass

        g = groups.setdefault(key, {"p6_name": None, "project": None, "ecod": None, "scod": None, "scod_is_lta": False})
        g["p6_name"] = g["p6_name"] or p6_name
        g["project"] = g["project"] or project
        if ecod_date is not None and (g["ecod"] is None or ecod_date > g["ecod"]):
            g["ecod"] = ecod_date

    # Pass 2: SCOD, now that every group's final LTA (max ECOD) is settled.
    for idx in range(1, len(df)):
        row = df.iloc[idx]
        p6_name = str(row.get(p6_col, '')).strip() if p6_col else ''
        project = str(row.get(project_col, '')).strip() if project_col else ''
        scod_val = row.get(scod_col) if scod_col else None

        p6_name = p6_name if p6_name and p6_name != 'nan' else None
        project = project if project and project != 'nan' else None
        key = p6_name or project
        if not key or key not in groups:
            continue

        g = groups[key]
        scod_date, scod_is_lta = _parse_scod(scod_val, g["ecod"])
        if scod_date is not None and (g["scod"] is None or scod_date > g["scod"]):
            g["scod"] = scod_date
            g["scod_is_lta"] = scod_is_lta

    updated_lta = updated_scod = 0
    skipped_ambiguous = []
    for g in groups.values():
        mapping = None
        if g["p6_name"]:
            # P6 appends "_Commissioned" to a project's own name once it's
            # live, but the connectivity export keeps the pre-commissioning
            # name — an exact match alone left every commissioned project's
            # LTA null (e.g. AGE26AL_A16_FT_333MW_PPA_Commissioned never
            # matched "AGE26AL_A16_FT_333MW_PPA").
            mapping = db.query(models.ProjectMapping).filter(
                (models.ProjectMapping.project_name_from_p6 == g["p6_name"]) |
                (models.ProjectMapping.project_name_from_p6 == g["p6_name"] + "_Commissioned")
            ).first()
        if not mapping and g["project"]:
            # "Project" is a shared portfolio label, not a per-plot identifier —
            # 5 different mapping rows share "MSEDCL PPA Ph-3", for instance.
            # A row whose p6 name is a typo/mismatch (e.g. "AGEL_S2B_112.5_MW_
            # HSAT", not the real "ARE55L_S02B_HSAT_12.5_MW_PPA") used to fall
            # back to `.first()` on that shared label and silently overwrite a
            # DIFFERENT, unrelated project's already-correct LTA. Only accept
            # the project-name fallback when it resolves to exactly one mapping.
            candidates = db.query(models.ProjectMapping).filter(models.ProjectMapping.project == g["project"]).all()
            if len(candidates) == 1:
                mapping = candidates[0]
            elif len(candidates) > 1:
                skipped_ambiguous.append((g["p6_name"], g["project"], len(candidates)))

        if not mapping:
            print(f"Could not find mapping for P6 project: {g['p6_name']} or Project: {g['project']}")
            continue

        if g["ecod"] is not None:
            mapping.lta_date = g["ecod"]
            updated_lta += 1
        if g["scod"] is not None:
            mapping.manual_scod = g["scod"]
            mapping.manual_scod_is_lta = g["scod_is_lta"]
            updated_scod += 1

    db.commit()
    print(f"Updated {updated_lta} records with LTA dates (max ECOD per project).")
    print(f"Updated {updated_scod} records with SCOD dates (max of literal/LTA-relative candidates per project).")
    if skipped_ambiguous:
        print(f"Skipped {len(skipped_ambiguous)} row(s) with an unresolvable p6 name and an ambiguous (shared) project label:")
        for p6, proj, n in skipped_ambiguous:
            print(f"  - p6='{p6}' project='{proj}' matches {n} mapping rows")


if __name__ == "__main__":
    main()
