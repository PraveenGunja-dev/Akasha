"""
Business rules for SLR (ZPSPS007) line items.

Some SLR descriptions are overhead and consolidated service lines rather than
material purchase orders — SPGS supply/services, PMC charges and margin, and
ISA charges. They are excluded from PO-derived metrics.

The exclusion matters: 60 of 4,119 rows carry 63.6% of gross actual spend
(Rs 10,816 Cr of Rs 17,009 Cr), so leaving them in lets a handful of
consolidated contract lines dominate every procurement figure.

Matched as a case-insensitive prefix rather than a substring, so a material
description that merely contains one of these letter runs (for example "visa"
or "misaligned" containing "isa") is not caught by accident.
"""
from sqlalchemy import or_, not_

import models

EXCLUDED_DESCRIPTION_PREFIXES = ("SPGS", "PMC", "ISA")


def exclude_overhead_lines():
    """SQLAlchemy criterion dropping overhead/service lines from PO metrics.

    NULL-safe: a row with no description is kept rather than silently dropped,
    which is what a bare NOT (description ILIKE ...) would do in SQL.
    """
    return or_(
        models.MTSLRData.description.is_(None),
        not_(or_(*[
            models.MTSLRData.description.ilike(f"{prefix}%")
            for prefix in EXCLUDED_DESCRIPTION_PREFIXES
        ])),
    )
