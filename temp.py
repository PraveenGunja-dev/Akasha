import psycopg2, json
conn = psycopg2.connect('postgresql://postgres:Postgres%40123@localhost:3315/aksha_db')
cur = conn.cursor()
cur.execute("SELECT projects FROM tc_network_edge WHERE region = 'Rajasthan' AND projects IS NOT NULL LIMIT 5")
for r in cur.fetchall():
    print(r[0])
