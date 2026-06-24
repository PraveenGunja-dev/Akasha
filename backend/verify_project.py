import os
import sys
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)
import models
from database import SessionLocal

db = SessionLocal()

# Find a WBS that has data across PO, MB51, and MB52
wbs_target = "H-51GA-01-01"

print(f"=== MATERIAL EQUATION TRACE FOR WBS: {wbs_target} ===")

# 1. Total PO (ME2J)
po_totals = db.query(
    func.sum(models.MTPOAmount.order_quantity).label('qty'),
    func.sum(models.MTPOAmount.still_to_deliver_qty).label('pending_qty')
).filter(models.MTPOAmount.wbs_element == wbs_target).first()

po_qty = po_totals.qty or 0
pending_qty = po_totals.pending_qty or 0

print(f"1. Total Ordered (PO):             {po_qty:,.2f}")
print(f"   -> Still to be Delivered:       {pending_qty:,.2f}")

# 2. Total Consumed (MB51)
mb51_totals = db.query(
    func.sum(models.MTMaterialDocument.quantity).label('qty')
).filter(models.MTMaterialDocument.wbs_element == wbs_target).first()

# MB51 might be negative in SAP, so we take absolute value if it's negative
mb51_raw = mb51_totals.qty or 0
mb51_qty = abs(mb51_raw)

print(f"2. Total Consumed (MB51):          {mb51_qty:,.2f}  (Raw DB val: {mb51_raw:,.2f})")

# 3. Total Inventory (MB52)
mb52_totals = db.query(
    func.sum(models.MTInventory.unrestricted_qty).label('qty')
).filter(models.MTInventory.wbs_element == wbs_target).first()

mb52_qty = mb52_totals.qty or 0

print(f"3. Total in Inventory (MB52):      {mb52_qty:,.2f}")

# --- Comparisons ---
print("\n=== COMPARISONS ===")

# PO vs (Consumed + Inventory)
delivered_calc = mb51_qty + mb52_qty
diff_1 = po_qty - delivered_calc
print(f"A) PO vs (Consumed + Inventory)")
print(f"   PO: {po_qty:,.2f} | (MB51+MB52): {delivered_calc:,.2f}")
print(f"   Difference: {diff_1:,.2f}  (If positive, we are missing deliveries. If negative, we received more than ordered!)")

# PO vs (Consumed + Inventory + Still to Deliver)
total_accounted = mb51_qty + mb52_qty + pending_qty
diff_2 = po_qty - total_accounted
print(f"\nB) PO vs (Consumed + Inventory + Still to Deliver)")
print(f"   PO: {po_qty:,.2f} | Total Accounted: {total_accounted:,.2f}")
print(f"   Difference: {diff_2:,.2f} (This should ideally be exactly zero!)")

