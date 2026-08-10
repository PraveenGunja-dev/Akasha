"""
Business rules for SLR (ZPSPS007) line items.

Two rules decide whether an SLR row counts as a purchase order.

1. Document type must be POrd or PReq. Rows with a blank type are cost and
   budget lines, not procurement — Land Cost, Modules Supply (FOB), Piling,
   Financing Costs, site setup. Only 21 of the 100 blank-type rows carry a PO
   document at all, and several hold large negative actuals (Land Cost at
   -Rs 2,989 Cr, Modules Supply (FOB) at -Rs 3,525 Cr) that would otherwise
   net against genuine spend.

2. Description must not be an overhead or consolidated service line — SPGS
   supply/services, PMC charges and margin, ISA charges. These are few but very
   large: 60 of 4,119 rows carry 63.6% of gross actual spend (Rs 10,816 Cr of
   Rs 17,009 Cr), so leaving them in lets a handful of contract lines dominate
   every procurement figure.

Descriptions are matched as a case-insensitive prefix rather than a substring,
so a material description that merely contains one of these letter runs (for
example "visa" or "misaligned" containing "isa") is not caught by accident.
"""
from sqlalchemy import and_, or_, not_

import models

PO_DOCUMENT_TYPES = ("POrd", "PReq")

EXCLUDED_DESCRIPTION_PREFIXES = ("SPGS", "PMC", "ISA")


def exclude_overhead_lines():
    """Criterion dropping overhead/service lines by description.

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


def only_po_document_types():
    """Criterion keeping only rows SAP typed as a purchase order or requisition."""
    return models.MTSLRData.type.in_(PO_DOCUMENT_TYPES)


def po_lines_only():
    """Both rules together — the filter every PO-derived metric should use."""
    return and_(only_po_document_types(), exclude_overhead_lines())
