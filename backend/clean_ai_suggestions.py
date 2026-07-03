from database import SessionLocal
import models

def fix_ai_suggestions():
    db = SessionLocal()
    try:
        # Find all notifications that have the hardcoded fallback
        fallback_text = "Fast-track parallel works or assign an extra crew to recover the delay."
        notifs = db.query(models.Notification).filter(models.Notification.ai_suggestion == fallback_text).all()
        
        print(f"Found {len(notifs)} polluted AI suggestions. Resetting to NULL...")
        for n in notifs:
            n.ai_suggestion = None
            
        db.commit()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fix_ai_suggestions()
