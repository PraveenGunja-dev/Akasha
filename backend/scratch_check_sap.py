import database, pandas as pd
from sqlalchemy import text
with database.engine.connect() as conn:
    df = pd.read_sql(text("""
        SELECT SUM(po_quantities_mw) AS ordered_mw,
               SUM(delivered_qty * mw_multiplication_factor) AS delivered_mw,
               SUM(still_to_deliver_qty * mw_multiplication_factor) AS in_transit_mw
        FROM mt_poamount 
        WHERE (material_name ILIKE '%module%' OR short_text ILIKE '%module%')
          AND mw_multiplication_factor IS NOT NULL
          AND mw_multiplication_factor > 0
    """), conn)
print(df)
