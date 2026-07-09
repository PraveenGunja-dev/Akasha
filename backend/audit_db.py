"""Full database audit script for Akasha Platform."""
from database import SessionLocal
from sqlalchemy import inspect, text

db = SessionLocal()
inspector = inspect(db.bind)

tables = sorted(inspector.get_table_names())
for t in tables:
    if t == 'alembic_version':
        continue
    count = db.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
    cols = inspector.get_columns(t)
    fks = inspector.get_foreign_keys(t)
    indexes = inspector.get_indexes(t)
    
    print(f"\n{'='*60}")
    print(f"TABLE: {t}  |  ROWS: {count:,}")
    print(f"{'='*60}")
    print("COLUMNS:")
    for c in cols:
        nullable = "NULL" if c.get("nullable") else "NOT NULL"
        default_val = f" DEFAULT={c.get('default')}" if c.get("default") else ""
        print(f"  {c['name']:40s} {str(c['type']):20s} {nullable}{default_val}")
    if fks:
        print("FOREIGN KEYS:")
        for fk in fks:
            print(f"  {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
    if indexes:
        print("INDEXES:")
        for idx in indexes:
            unique = "UNIQUE " if idx.get("unique") else ""
            print(f"  {unique}{idx['name']}: {idx['column_names']}")

# Check for pgvector
print(f"\n{'='*60}")
print("EXTENSIONS CHECK")
print(f"{'='*60}")
try:
    exts = db.execute(text("SELECT extname, extversion FROM pg_extension")).fetchall()
    for e in exts:
        print(f"  {e[0]}: v{e[1]}")
except Exception as ex:
    print(f"  Error checking extensions: {ex}")

# Check for any embedding-like columns
print(f"\n{'='*60}")
print("VECTOR/EMBEDDING COLUMNS CHECK")
print(f"{'='*60}")
found = False
for t in tables:
    cols = inspector.get_columns(t)
    for c in cols:
        col_type = str(c['type']).lower()
        if 'vector' in col_type or 'embed' in c['name'].lower() or 'array' in col_type:
            print(f"  {t}.{c['name']}: {c['type']}")
            found = True
if not found:
    print("  No vector/embedding columns found.")

# Check for views
print(f"\n{'='*60}")
print("VIEWS")
print(f"{'='*60}")
try:
    views = inspector.get_view_names()
    if views:
        for v in views:
            print(f"  {v}")
    else:
        print("  No views.")
except:
    print("  Could not check views.")

# Check DB engine type
print(f"\n{'='*60}")
print("DATABASE INFO")
print(f"{'='*60}")
print(f"  Dialect: {db.bind.dialect.name}")
print(f"  URL: {str(db.bind.url)}")

db.close()
