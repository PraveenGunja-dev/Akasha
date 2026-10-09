import pandas as pd
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from models import AribaInboundDelivery

logger = logging.getLogger(__name__)

def parse_date(date_val):
    if pd.isna(date_val):
        return None
    if isinstance(date_val, datetime):
        return date_val
    try:
        return pd.to_datetime(date_val).to_pydatetime()
    except Exception:
        return None

def sync_ariba_inbound_deliveries(db: Session, excel_path: str):
    """
    Reads the ZIBDSESREP.xlsx file and synchronizes Ariba Inbound Deliveries to the database.
    This provides visibility into material transit state (Dispatched vs Received) and 
    finance handover (Checklist Status).
    """
    try:
<<<<<<< Updated upstream
        df = pd.read_excel(excel_path)
    except Exception as e:
        logger.error(f"Failed to read ARIBA Excel file {excel_path}: {e}")
        return False
        
    # Standardize columns to handle slight naming variations
    col_map = {
        'PO Number': 'po_number',
        'Item': 'item',
        'Material Number': 'material_number',
        'Material Description': 'material_description',
        'PO Quantity': 'po_quantity',
        'UoM': 'uom',
        'Company Code': 'company_code',
        'Vendor Code': 'vendor_code',
        'Vendor Name': 'vendor_name',
        'Inbound Delivery Quantity': 'inbound_delivery_quantity',
        'Rejected Quantity': 'rejected_quantity',
        'IBD Creation Date': 'ibd_creation_date',
        'Plant': 'plant',
        'GR posting date': 'gr_posting_date',
        'GRN Quantity': 'grn_quantity',
        'Currency': 'currency',
        'ARIBA Invoice date': 'ariba_invoice_date',
        'Checklist Number': 'checklist_number',
        'Checklist Status': 'checklist_status',
        'Checklist_Date': 'checklist_date'
    }
    
    # Rename columns that exist
    actual_cols = {}
    for c in df.columns:
        for k, v in col_map.items():
            if k.lower() in str(c).lower().strip():
                actual_cols[c] = v
                break
    
    df = df.rename(columns=actual_cols)
    
    records_added = 0
    
    # We clear the existing data or merge. Since this is an inbound delivery report, 
    # the best approach is usually to wipe and replace if the file contains the full snapshot.
    db.query(AribaInboundDelivery).delete()
    db.flush()
    
    for _, row in df.iterrows():
        po_num = str(row.get('po_number', '')).strip()
        if not po_num or po_num == 'nan':
            continue
            
        mat_desc = str(row.get('material_description', '')).strip()
        # Note: We explicitly do NOT filter out Solar Modules here. We want them tracked.
        
        def safe_float(val):
            try:
                return float(val) if pd.notna(val) else 0.0
            except Exception:
                return 0.0
=======
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def load_ariba_allocations(db: Session, po_numbers: Optional[set] = None) -> dict:
    """Every Ariba delivery row, with the WBS element(s) its PO line belongs to.

    Returns {"rows": [...], "unmapped_lines": n}. Each row carries
    `allocations`: [(wbs_element, share)], shares summing to 1. The WBS comes
    from the SAP CO lines of the same (PO, item); a line booked to several WBS
    is split by CO quantity. A line missing from CO falls back to the PO's WBS
    in mt_poamount only when the whole PO sits on ONE WBS - otherwise the row
    stays unmapped rather than being credited to a guessed project.

    `is_module` / `mw_per_unit` come from the CO material text (the same
    PANEL rule and wattage parser the PO tables use), so MWp is computed
    exactly as SAP's ordered MWp is."""
    from services.module_wattage import mw_factor

    params, where = {}, ""
    if po_numbers is not None:
        if not po_numbers:
            return {"rows": [], "unmapped_lines": 0}
        params["pos"] = list(po_numbers)
        where = "where po_number = any(:pos)"
    rows = [dict(r) for r in db.execute(text(f"""
        select po_number, item, material_number, material_description, uom, vendor_code, vendor_name,
               plant, inbound_delivery_quantity, rejected_quantity, grn_quantity,
               ibd_creation_date, gr_posting_date, checklist_number, checklist_status, checklist_date
        from ariba_inbound_delivery {where}"""), params).mappings()]
    if not rows:
        return {"rows": [], "unmapped_lines": 0}

    pos = list({r["po_number"] for r in rows})
    co = db.execute(text("""
        select po_document, po_item, wbs_element, sum(abs(coalesce(quantity, 0))),
               bool_or(is_module), max(material_description)
        from sap_co_line
        where po_document = any(:pos) and po_item is not null and wbs_element is not null
        group by 1, 2, 3"""), {"pos": pos}).fetchall()
    by_line: dict[tuple, list] = defaultdict(list)
    line_meta: dict[tuple, dict] = {}
    for po, item, wbs, qty, is_mod, mdesc in co:
        key = (str(po).strip(), str(item).strip().lstrip("0"))
        by_line[key].append((wbs, _f(qty)))
        meta = line_meta.setdefault(key, {"is_module": False, "mw": None})
        meta["is_module"] = meta["is_module"] or bool(is_mod)
        meta["mw"] = meta["mw"] or (mw_factor(mdesc or "") if is_mod else None)

    po_wbs: dict[str, set] = defaultdict(set)
    po_mw: dict[str, float] = {}
    for po, wbs, mw in db.execute(text("""
            select purchasing_document, wbs_element, max(mw_multiplication_factor)
            from mt_poamount where purchasing_document = any(:pos) and wbs_element is not null
            group by 1, 2"""), {"pos": pos}):
        po_wbs[str(po).strip()].add(wbs)
        if mw:
            po_mw[str(po).strip()] = float(mw)

    unmapped = set()
    for r in rows:
        key = (r["po_number"], str(r["item"] or "").lstrip("0"))
        lines = by_line.get(key)
        if lines:
            total = sum(q for _, q in lines)
            r["allocations"] = [(w, (q / total) if total > 0 else 1 / len(lines)) for w, q in lines]
            r["mapped_by"] = "po_item"
        elif len(po_wbs.get(r["po_number"], ())) == 1:
            r["allocations"] = [(next(iter(po_wbs[r["po_number"]])), 1.0)]
            r["mapped_by"] = "po"
        else:
            r["allocations"] = []
            r["mapped_by"] = None
            unmapped.add(key)
        meta = line_meta.get(key, {})
        r["is_module"] = bool(meta.get("is_module"))
        r["mw_per_unit"] = meta.get("mw") or mw_factor(r["material_description"] or "") or (
            po_mw.get(r["po_number"]) if r["is_module"] else None)
    return {"rows": rows, "unmapped_lines": len(unmapped)}


_PLANT_CODE = re.compile(r"^(?:H-|WIND_)?([0-9A-Z]{4})(?:-.*)?$")


def plant_codes(*cells: Optional[str]) -> set:
    """SAP plant codes named in project-master cells, as Ariba writes them.

    The sheet writes 'H-51Y9' (Ariba: '51Y9') and 'WIND_6733', puts several
    codes in one cell separated by spaces or line breaks ('H-603C\\nH-603I'),
    and sometimes a WBS ('H-51Y9-01-01', whose first part is the plant)."""
    out = set()
    for cell in cells:
        for part in re.split(r"[\s,;/]+", cell or ""):
            m = _PLANT_CODE.match(part.strip().upper())
            if m:
                out.add(m.group(1))
    return out


def assign_to_projects(rows: list, plant_owners: dict, wbs_owners, wbs_share) -> None:
    """Decide which project(s) each Ariba row belongs to (user rule 2026-10-09).

    1. Plant first: the row's plant is matched to the project master's plant
       codes (SPV plant, AGEL module plant, AGE6L). One project owns the plant
       and SAP books the PO line to that project (or to no project) -> the row
       is that project's.
    2. Plant shared -> the PO decides among the projects on that plant: the
       WBS SAP books the PO line to names which of them. A plant listed on one project but whose PO lines SAP books
       to others IS shared - the sheet records 51Y9 only on MLP T1 J&K while
       SAP books its lines to MLP T1 TR/CG/OR/TN - so it is decided the same
       way, never credited to the one project the sheet happens to name.
    3. A WBS several projects carry is split by capacity (wbs_share), as the
       SAP figures are.

    Sets r["assign"] = {mapping_id: share} and r["basis"] / r["match"], the
    rule that placed it, for the ledger and the export.

    plant_owners: plant -> [mapping ids]; wbs_owners(wbs) -> [mapping ids];
    wbs_share(mapping_id, wbs) -> that project's share of the WBS."""
    for r in rows:
        plant = (r.get("plant") or "").upper()
        owners = plant_owners.get(plant, [])
        wbs = sorted({w for w, _ in r["allocations"]})
        by_wbs = {mid for w in wbs for mid in wbs_owners(w)}
        if len(owners) == 1 and by_wbs <= {owners[0]}:
            r["assign"] = {owners[0]: 1.0}
            r["basis"] = "plant"
            r["match"] = f"Plant {plant}"
            continue
        # Several projects on the plant: the PO decides among THOSE projects
        # (user rule 2026-10-09). Only when the PO line's WBS names none of
        # them (or the plant names one project and SAP books the line to
        # others, as with 51Y9) does the WBS alone decide.
        pool = set(owners) if len(owners) > 1 and by_wbs & set(owners) else None
        assign: dict = {}
        for w, s in r["allocations"]:
            mids = [mid for mid in wbs_owners(w) if pool is None or mid in pool]
            if not mids:
                continue
            total = sum(wbs_share(mid, w) for mid in mids)
            for mid in mids:
                assign[mid] = assign.get(mid, 0.0) + s * (wbs_share(mid, w) / total if total > 0 else 1 / len(mids))
        if pool is not None:
            # Renormalise: lines booked outside the plant's projects are dropped from the pool split
            got = sum(assign.values())
            assign = {k: v / got for k, v in assign.items()} if got > 0 else {}
        r["assign"] = {k: v for k, v in assign.items() if v > 0}
        if not r["assign"]:
            r["basis"], r["match"] = None, f"Plant {plant or '?'}: no project"
            continue
        r["basis"] = "po"
        where = ", ".join(wbs)
        if owners:
            r["match"] = f"Plant {plant} shared - PO line WBS {where}"
        else:
            r["match"] = f"PO line WBS {where} (plant {plant or '?'} not in project master)"
        if any(v < 0.999 for v in r["assign"].values()):
            r["match"] += " - capacity share"


def delivery_events(rows: list, share_of) -> list:
    """Group allocated Ariba rows into delivery events for one project.

    One event per (PO, dispatch date, receipt date): rows on the same PO that
    left and landed on the same days are one consignment for planning; any
    difference in either date is a separate event, never merged.

    share_of(row) -> this project's share of the row (0 when it is not the
    project's). Quantities are the received GRN for received rows and the
    dispatched IBD quantity for rows awaiting GRN."""
    today = datetime.utcnow().date()
    events: dict[tuple, dict] = {}
    for r in rows:
        share = share_of(r)
        if share <= 0:
            continue
        ibd_dt, gr_dt = r["ibd_creation_date"], r["gr_posting_date"]
        received = gr_dt is not None
        qty = (_f(r["grn_quantity"]) if received else _f(r["inbound_delivery_quantity"])) * share
        key = (r["po_number"], ibd_dt.date() if ibd_dt else None, gr_dt.date() if gr_dt else None)
        e = events.get(key)
        if e is None:
            e = events[key] = {
                "po": r["po_number"], "vendor": r["vendor_name"] or "",
                "dispatch_date": key[1].isoformat() if key[1] else None,
                "receipt_date": key[2].isoformat() if key[2] else None,
                "transit_days": (key[2] - key[1]).days if key[1] and key[2] else None,
                "age_days": (today - key[1]).days if key[1] and not received else None,
                "status": "received" if received else "awaiting_grn",
                "qty": 0.0, "mwp": 0.0, "mwp_known": True, "rejected_qty": 0.0,
                "uom": r["uom"] or "", "rows": 0, "checklist_created": 0,
                "checklist_numbers": [], "checklist_date": None, "share": share,
                "lines": set(), "plants": set(), "matches": set(), "basis": set(),
            }
        e["plants"].add((r.get("plant") or "").upper())
        if r.get("match"):
            e["matches"].add(r["match"])
        if r.get("basis"):
            e["basis"].add(r["basis"])
        e["qty"] += qty
        if r["mw_per_unit"]:
            e["mwp"] += qty * r["mw_per_unit"]
        else:
            e["mwp_known"] = False
        e["rejected_qty"] += _f(r["rejected_quantity"]) * share
        e["rows"] += 1
        e["lines"].add(str(r["item"] or ""))
        e["share"] = min(e["share"], share)
        if r["checklist_number"]:
            e["checklist_created"] += 1
            if r["checklist_number"] not in e["checklist_numbers"]:
                e["checklist_numbers"].append(r["checklist_number"])
            cd = r["checklist_date"].date().isoformat() if r["checklist_date"] else None
            if cd and (e["checklist_date"] is None or cd > e["checklist_date"]):
                e["checklist_date"] = cd
    out = []
    for e in events.values():
        e["qty"] = round(e["qty"], 2)
        e["mwp"] = round(e["mwp"], 3)
        e["rejected_qty"] = round(e["rejected_qty"], 2)
        e["lines"] = sorted(e["lines"], key=lambda s: (len(s), s))
        e["share"] = round(e["share"], 4)
        e["plant"] = ", ".join(sorted(p for p in e.pop("plants") if p))
        # How this lot was placed on the project: "plant" or "po" (plant
        # shared, PO line WBS decided); "match" spells it out.
        basis = e.pop("basis")
        e["basis"] = "plant" if basis == {"plant"} else "po" if basis else None
        e["match"] = " | ".join(sorted(e.pop("matches")))
        out.append(e)
    out.sort(key=lambda e: (e["dispatch_date"] or "", e["receipt_date"] or "9999", e["po"]))
    return out
>>>>>>> Stashed changes

        delivery = AribaInboundDelivery(
            po_number=po_num,
            item=str(row.get('item', '')).strip(),
            material_number=str(row.get('material_number', '')).strip(),
            material_description=mat_desc,
            po_quantity=safe_float(row.get('po_quantity')),
            uom=str(row.get('uom', '')).strip(),
            company_code=str(row.get('company_code', '')).strip(),
            vendor_code=str(row.get('vendor_code', '')).strip(),
            vendor_name=str(row.get('vendor_name', '')).strip(),
            inbound_delivery_quantity=safe_float(row.get('inbound_delivery_quantity')),
            rejected_quantity=safe_float(row.get('rejected_quantity')),
            ibd_creation_date=parse_date(row.get('ibd_creation_date')),
            plant=str(row.get('plant', '')).strip(),
            gr_posting_date=parse_date(row.get('gr_posting_date')),
            grn_quantity=safe_float(row.get('grn_quantity')),
            currency=str(row.get('currency', '')).strip(),
            ariba_invoice_date=parse_date(row.get('ariba_invoice_date')),
            checklist_number=str(row.get('checklist_number', '')).strip(),
            checklist_status=str(row.get('checklist_status', '')).strip(),
            checklist_date=parse_date(row.get('checklist_date'))
        )
        db.add(delivery)
        records_added += 1
        
    try:
        db.commit()
        logger.info(f"Successfully synced ARIBA Inbound Deliveries. Total records: {records_added}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Error committing ARIBA data: {e}")
        return False
