from database import SessionLocal
from routers.dashboard import get_capacity_overview

db = SessionLocal()
try:
    data = get_capacity_overview(portfolio="All Portfolios", db=db)
    print("SOLAR TOTALS:")
    print(f"COD Done (Solar): {data['totals']['solar_cod']:.1f} MW")
    print(f"Trial Run Only (Solar): {data['totals']['solar_tr']:.1f} MW")
    print(f"Total Solar (COD + TR): {(data['totals']['solar_cod'] + data['totals']['solar_tr']):.1f} MW")
except Exception as e:
    print("Error:", e)
finally:
    db.close()
