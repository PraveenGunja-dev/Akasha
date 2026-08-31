"""
Link Pulse projects to the project mapping.

Pulse and P6 name the same substation completely differently:

    Pulse                     mapping
    BESS PSS-12 Project   ->  AGE27CL_PSS12   (project_id AGE27CL_PSS12_FINAL)
    BESS PSS-08B Project  ->  AGE35L_PSS8B
    PSS-18 Project        ->  AGE25CL PSS-18 (49 Loc.) - Phase-4

So a name match finds almost nothing — which is why 433 of 576
non-conformances belonged to no project. The substation number is the piece
both systems agree on, so that is what is matched on.

Safety rules, because a wrong link moves one site's non-conformances onto
another project:

  * BESS ONLY. A substation number is not an identity — several projects sit
    at the same substation. "PSS-18 Project" matched the solar project
    "AGE25CL PSS-18 (49 Loc.) - Phase-4" on number alone, which is wrong: they
    share a location, not a scope. Only Pulse projects that name themselves
    BESS are matched this way.
  * A mapping is only a candidate if it references exactly ONE substation.
    Several wind and solar mappings span two ("PSS-12 (27 Loc.) & PSS-14"),
    and a BESS non-conformance must not land on those.
  * A Pulse project is linked only when exactly ONE such candidate matches.
    Anything ambiguous is left alone and reported.
  * Existing pulse_project_uuid values are never overwritten.

Everything else — merchant, hybrid and named solar/wind projects — has no
shared key at all and must be mapped by hand in Admin.

    venv/Scripts/python.exe scripts/link_pulse_projects.py          # preview
    venv/Scripts/python.exe scripts/link_pulse_projects.py --apply  # write
"""

import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models  # noqa: E402
from database import SessionLocal  # noqa: E402

# PSS-08B / PSS_8B / PSS 09 all collapse to one token. The trailing letter must
# be adjacent: with \s* in front of it, " Project" contributes a stray "P" and
# PSS-09 becomes PSS9P, matching nothing.
SUBSTATION = re.compile(r"PSS[\s_-]*0*(\d+)([A-Za-z])?(?![A-Za-z])", re.I)


def tokens(text) -> set:
    return {
        "PSS%s%s" % (m.group(1), (m.group(2) or "").upper())
        for m in SUBSTATION.finditer(str(text or ""))
    }


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        mappings = [m for m in db.query(models.ProjectMapping).all() if m.project_id]

        # Pulse project name -> its UUID, plus how many NCs hang off it.
        pulse: dict[str, str] = {}
        for name, uuid in db.query(models.PulseNC.project_name, models.PulseNC.project_id).distinct():
            if name and uuid:
                pulse.setdefault(str(name).strip(), uuid)

        counts: dict[str, int] = {}
        for (name,) in db.query(models.PulseNC.project_name):
            if name:
                key = str(name).strip()
                counts[key] = counts.get(key, 0) + 1

        already = {
            m.pulse_project_uuid for m in mappings if getattr(m, "pulse_project_uuid", None)
        }

        linked, ambiguous, unmatched = [], [], []

        for name, uuid in sorted(pulse.items(), key=lambda kv: -counts.get(kv[0], 0)):
            if uuid in already:
                continue
            # BESS only: substation number alone is not an identity.
            if "bess" not in name.lower():
                unmatched.append((name, counts.get(name, 0), "not a BESS project - map by hand"))
                continue

            wanted = tokens(name)
            if not wanted:
                unmatched.append((name, counts.get(name, 0), "no substation in name"))
                continue

            candidates = []
            for m in mappings:
                blob = " ".join(str(x or "") for x in (m.project_name_from_p6, m.project, m.project_id))
                found = tokens(blob)
                if wanted & found:
                    candidates.append((m, found))

            # Only mappings that reference a single substation may be claimed.
            precise = [m for m, found in candidates if len(found) == 1]

            if len(precise) == 1:
                linked.append((name, uuid, precise[0], counts.get(name, 0)))
            elif candidates:
                ambiguous.append((name, counts.get(name, 0),
                                  ", ".join(m.project_id for m, _ in candidates)))
            else:
                unmatched.append((name, counts.get(name, 0), "no mapping for that substation"))

        print("%-26s %-30s %6s" % ("PULSE PROJECT", "LINKED TO", "NCS"))
        for name, _uuid, mapping, n in linked:
            print("%-26s %-30s %6d" % (name[:25], mapping.project_id[:29], n))

        if ambiguous:
            print("\nAmbiguous — left unlinked, needs a decision:")
            for name, n, who in ambiguous:
                print("  %-26s %4d NCs  candidates: %s" % (name[:25], n, who))

        if unmatched:
            print("\nNo match — needs mapping by hand in Admin:")
            for name, n, why in unmatched:
                print("  %-40s %4d NCs  (%s)" % (name[:39], n, why))

        covered = sum(n for *_, n in linked)
        print("\nwould link %d Pulse projects covering %d NCs" % (len(linked), covered))

        if not apply:
            print("preview only — re-run with --apply to write")
            return

        for _name, uuid, mapping, _n in linked:
            mapping.pulse_project_uuid = uuid
        db.commit()
        print("committed %d links" % len(linked))
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
