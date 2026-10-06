import psycopg2
try:
    conn = psycopg2.connect(dbname='Akasha', user='postgres', password='Nikitha', host='127.0.0.1', port='5432')
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = [t[0] for t in cur.fetchall()]
    print("Tables:", tables)
except Exception as e:
    print(e)
