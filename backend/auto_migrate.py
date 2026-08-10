import logging
from sqlalchemy import inspect, text
from database import engine
import models

logger = logging.getLogger(__name__)

def auto_upgrade_schema():
    """
    Automatically compares SQLAlchemy models against the database schema
    and injects missing columns via ALTER TABLE.
    """
    logger.info("🔍 Checking for missing database columns...")
    
    LEGACY_SAP_TABLES = ["mt_intransit", "mt_underconstruction"]

    # Ensure tables are created first
    models.Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        for table_name in LEGACY_SAP_TABLES:
            try:
                result = conn.execute(text(f"SELECT 1 FROM information_schema.tables WHERE table_name = '{table_name}'"))
                if result.fetchone():
                    logger.info(f"🧹 Dropping legacy SAP table '{table_name}' from the database...")
                    conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            except Exception as e:
                logger.warning(f"⚠️ Could not drop legacy SAP table '{table_name}': {e}")

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    added_columns_count = 0

    with engine.begin() as conn:
        for table_name, table in models.Base.metadata.tables.items():
            if table_name in existing_tables:
                existing_columns = {c['name'].lower() for c in inspector.get_columns(table_name)}
                
                for column in table.columns:
                    if column.name.lower() not in existing_columns:
                        col_type = str(column.type.compile(engine.dialect))
                        
                        try:
                            logger.info(f"➕ Adding missing column '{column.name}' ({col_type}) to table '{table_name}'...")
                            sql = text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}")
                            conn.execute(sql)
                            added_columns_count += 1
                        except Exception as e:
                            logger.error(f"❌ Failed to add column {column.name} to {table_name}: {e}")
                            
    if added_columns_count > 0:
        logger.info(f"✅ Successfully added {added_columns_count} missing columns.")
    else:
        logger.info("✅ Database schema is up to date. No missing columns found.")

if __name__ == "__main__":
    auto_upgrade_schema()
