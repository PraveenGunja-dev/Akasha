"""Full database audit script - writes to file to avoid truncation."""
from database import SessionLocal
from sqlalchemy import inspect, text

db = SessionLocal()
inspector = inspect(db.bind)

output = []
tables = sorted(inspector.get_table_names())
for t in tables:
    if t == 'alembic_version':
        continue
    count = db.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
    cols = inspector.get_columns(t)
    fks = inspector.get_foreign_keys(t)
    indexes = inspector.get_indexes(t)
    
    output.append(f"\n{'='*60}")
    output.append(f"TABLE: {t}  |  ROWS: {count:,}")
    output.append(f"{'='*60}")
    output.append("COLUMNS:")
    for c in cols:
        nullable = "NULL" if c.get("nullable") else "NOT NULL"
        default_val = f" DEFAULT={c.get('default')}" if c.get("default") else ""
        output.append(f"  {c['name']:40s} {str(c['type']):20s} {nullable}{default_val}")
    if fks:
        output.append("FOREIGN KEYS:")
        for fk in fks:
            output.append(f"  {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
    if indexes:
        output.append("INDEXES:")
        for idx in indexes:
            unique = "UNIQUE " if idx.get("unique") else ""
            output.append(f"  {unique}{idx['name']}: {idx['column_names']}")

db.close()

with open("audit_results.txt", "w") as f:
    f.write("\n".join(output))
print("Written to audit_results.txt")
