"""Watt-peak per solar module, read from the SAP material text.

ZSPS007 carries no wattage column. The only place a module's rating exists is
the material short text, so `mt_poamount.mw_multiplication_factor` is derived
from that string at ingest and `po_quantities_mw` is quantity x factor. A line
whose factor is null is dropped from every MWp figure on the Ordering Schedule
page, so a text this module cannot read is capacity that silently disappears.

The original rule was a single `(\\d{3,4})\\s*W` search. It reads the vendors who
state the wattage outright (Longi "MODULE,615W,LR8-66HGD-615M") but not the ones
who only encode it in the part number, which cost 216 PO lines / 3.5M panels /
about 2,062 MWp -- most of the unexplained Balance Ordering on the commissioned
Khavda projects (checked 2026-09-23).

Every pattern below is taken from a material text actually present in
mt_poamount, not from a vendor datasheet; `PATTERN_EXAMPLES` is the evidence and
`selftest()` re-checks it. A text that states no rating anywhere -- "SOLAR PV
MODULE AS PER SPECIFICATIONS", "ROBOTIC UNITS FOR MODULE CLEANING", the MMS
erection service lines -- returns None, because guessing a wattage would invent
capacity. That is the one thing this module must never do.
"""
from __future__ import annotations

import re
from typing import Optional

# A crystalline silicon module sold to this portfolio is 250-800 Wp. The bound
# is a sanity guard, not a filter: it stops a stray "1500W" or a four-digit part
# number being read as a per-panel rating and inflating MWp by a factor of three.
MIN_WATTS = 250
MAX_WATTS = 800

# Ordered: the wattage stated outright wins over any part-number inference.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    # "630W" / "630 W" / "585WP" / "575 Wp" -- stated, with or without a space.
    ("stated", re.compile(r"(?<![\d.])(\d{3,4})\s*W[Pp]?(?![A-Za-z0-9])")),
    # Jinko       MODULE,SOLAR,MM:JKM590N-72HL4-BDV,JINKO
    ("jinko", re.compile(r"JKM(\d{3,4})[A-Z]?(?![\d])", re.I)),
    # Goldi       MODULE,PN:GS10-T144-GF-585,GOLDI
    ("goldi", re.compile(r"\bGF-(\d{3,4})(?![\d])", re.I)),
    # Redren      SOLAR PANEL,MM:RS-M10TC-144-585,REDREN
    ("redren", re.compile(r"RS-M10TC-\d+-(\d{3,4})(?![\d])", re.I)),
    # MSPVL       MODULE,SOLAR,AB-G12R-132-620,MSPVL
    ("mspvl", re.compile(r"AB-G\d+R-\d+-(\d{3,4})(?![\d])", re.I)),
    # GREW        MODULE,SOLAR,580WP,MM:GTG72HM10580,GREW  (caught by "stated",
    #             kept so a GREW line without the leading "580WP" still reads)
    ("grew", re.compile(r"GTG\d{2}HM\d{2}(\d{3})(?![\d])", re.I)),
    # Longi       MODULE,615W,LR8-66HGD-615M,LONGI         (ditto)
    ("longi", re.compile(r"HGD-(\d{3,4})[A-Z]?(?![\d])", re.I)),
    # Saatvik     MODULE,580W,SGE580-144TGG,SAATVIK        (ditto)
    ("saatvik", re.compile(r"\bSGE(\d{3,4})-", re.I)),
]

# One real material text per rule, as it appears in mt_poamount, with the
# wattage it must yield. selftest() asserts these; the ingest calls it on import
# so a broken pattern fails loudly at load rather than quietly zeroing capacity.
PATTERN_EXAMPLES: list[tuple[str, Optional[int]]] = [
    ("MODULE,SOLAR,N,1500V,630W,2382X1134X30MM", 630),
    ("MODULE,615W,LR8-66HGD-615M,LONGI", 615),
    ("MODULE,SOLAR,66HL4M-BDV-620W,JINKO", 620),
    ("MODULE,SOLAR,MM:GCL-NT10/72GDF-590W,GCL", 590),
    ("MODULE,575WP,MM:ASB-M10-144-AAA,MSEL", 575),
    ("MODULE,SOLAR,580WP,MM:GTG72HM10580,GREW", 580),
    ("MODULE,585W,HYPERSOLVSMDH.72.585.05", 585),
    ("MODULE,580W,SGE580-144TGG,SAATVIK", 580),
    ("MODULE,550W,ASB-M10-144-550,MSPVL", 550),
    # No "W" anywhere -- the rating lives in the part number only.
    ("MODULE,SOLAR,MM:JKM590N-72HL4-BDV,JINKO", 590),
    ("MODULE,SOLAR,MM:JKM585N-72HL4-BDV,JINKO", 585),
    ("MODULE,PN:GS10-T144-GF-585,GOLDI", 585),
    ("MODULE,PN:GS10-T144-GF-580,GOLDI", 580),
    ("SOLAR PANEL,MM:RS-M10TC-144-585,REDREN", 585),
    ("SOLAR PANEL,RS-M10TC-144-590,REDREN", 590),
    ("MODULE,SOLAR,AB-G12R-132-620,MSPVL", 620),
    # Stated with a space, and lower case.
    ("MODULE,SOLAR,620 W,BIFACIAL", 620),
    ("MODULE,SOLAR,615 Wp,MONO", 615),
    # Must stay unreadable: no rating is present, so none may be invented.
    ("SOLAR PV MODULE AS PER SPECIFICATIONS", None),
    ("ROBOTIC UNITS FOR MODULE CLEANING", None),
    ("Erection and installation of PV Module", None),
    ("MMS (module mounting structure) installation", None),
    ("MODULE,DUAL RELAY CONN,PN:88167", None),
    ("MODULE,230V,MM:JAV016,JVS", None),
    ("COLUMN,C-LIP,170X80X20X2X2345MM", None),
    # Out of range: a 1500 V system voltage is not a panel rating.
    ("MODULE,SOLAR,N,1500W,2382X1134X30MM", None),
]


def module_watts(text: Optional[str]) -> Optional[int]:
    """Watt-peak of one module, or None when the text states no usable rating.

    None means "not known", never "zero" -- the caller must leave the factor
    null so the line is excluded rather than counted as no capacity.
    """
    if not text:
        return None
    s = str(text)
    for _name, pat in _RULES:
        for m in pat.finditer(s):
            w = int(m.group(1))
            if MIN_WATTS <= w <= MAX_WATTS:
                return w
    return None


def module_watts_with_rule(text: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """As module_watts, plus which rule read it — for audit output."""
    if not text:
        return None, None
    s = str(text)
    for name, pat in _RULES:
        for m in pat.finditer(s):
            w = int(m.group(1))
            if MIN_WATTS <= w <= MAX_WATTS:
                return w, name
    return None, None


def mw_factor(text: Optional[str]) -> Optional[float]:
    """MW per module — the value stored in mt_poamount.mw_multiplication_factor.

    Replaces the older local `_extract_wattage_from_text` helpers; same contract
    (MW per unit, or None), wider reading.
    """
    w = module_watts(text)
    return None if w is None else w / 1_000_000


def selftest() -> None:
    """Assert every documented example still reads as recorded."""
    bad = []
    for txt, expected in PATTERN_EXAMPLES:
        got = module_watts(txt)
        if got != expected:
            bad.append(f"  {txt!r}\n     expected {expected}, got {got}")
    if bad:
        raise AssertionError("module_wattage patterns regressed:\n" + "\n".join(bad))


selftest()
