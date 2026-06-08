from database import engine, Base
import models

def init_db():
    print("Initializing the database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully!")
    except Exception as e:
        print(f"Error connecting to database: {e}")

if __name__ == "__main__":
    init_db()
