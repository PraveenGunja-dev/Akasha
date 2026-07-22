import sys
import os
import json

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import P6Project, ProjectMapping

def test_progress():
    db = SessionLocal()
    try:
        # We query the mappings and their associated P6 projects just like the dashboard
        mappings = db.query(ProjectMapping).all()
        p6_projects = db.query(P6Project).all()
        
        print("\n" + "="*80)
        print(f"{'Project ID':<15} | {'Actual Units':<15} | {'Budget Units':<15} | {'Duration %':<12} | {'Progress %'}")
        print("="*80)
        
        for m in mappings:
            # Find the corresponding P6 data
            p6_proj = next((p for p in p6_projects if p.project_id == m.project_id), None)
            
            if not p6_proj:
                continue
                
            actual_non_labor = getattr(p6_proj, 'actual_non_labor_units', 0) or 0.0
            budget_labor = getattr(p6_proj, 'at_completion_non_labor_units', 0) or 0.0
            dur_pct = getattr(p6_proj, 'duration_percent_complete', 0) or 0.0
            
            # The exact logic from our service
            if budget_labor > 0:
                progress = (actual_non_labor / budget_labor) * 100.0
                calc_method = "(Units)"
            else:
                progress = (dur_pct * 100.0) if dur_pct <= 1.0 else dur_pct
                calc_method = "(Duration Fallback)"
                
            print(f"{p6_proj.project_id:<15} | {actual_non_labor:<15} | {budget_labor:<15} | {dur_pct:<12.4f} | {progress:.2f}% {calc_method}")
            
    finally:
        db.close()

if __name__ == "__main__":
    test_progress()
