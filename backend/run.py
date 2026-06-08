import os
import uvicorn
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def prepare_database():
    load_dotenv(override=True)
    db_url = os.getenv("DATABASE_URL")
    if not db_url or not db_url.startswith("postgres"):
        return
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    # Split the URL to get the base URL and the target DB name
    try:
        base_url, db_name = db_url.rsplit("/", 1)
        query = ""
        if "?" in db_name:
            db_name, query = db_name.split("?", 1)
            query = "?" + query
            
        # Connect to default 'postgres' database to issue CREATE DATABASE
        postgres_url = f"{base_url}/postgres{query}"
        
        # We need isolation_level="AUTOCOMMIT" to run CREATE DATABASE
        engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            # Check if database exists
            res = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{db_name}'"))
            if not res.fetchone():
                print(f"Database '{db_name}' not found. Creating it now...")
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"Database '{db_name}' created successfully!")
            else:
                print(f"Database '{db_name}' already exists.")
    except Exception as e:
        print(f"Could not automatically ensure database exists: {e}")

    # Run Alembic migrations automatically
    try:
        import alembic.config
        print("Applying database migrations...")
        alembic.config.main(argv=['--raiseerr', 'upgrade', 'head'])
        print("Migrations complete!")
    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    load_dotenv(override=True)
    
    if os.getenv("AUTO_SETUP_DB", "False").lower() == "true":
        print("Preparing Database Infrastructure...")
        prepare_database()
    else:
        print("AUTO_SETUP_DB is False. Skipping automatic database creation and migration.")
    
    print("Starting Akasha Platform Backend on Port 3510...")
    # Run the FastAPI application on host 0.0.0.0 and port 3510
    uvicorn.run("main:app", host="0.0.0.0", port=3510, reload=False)
