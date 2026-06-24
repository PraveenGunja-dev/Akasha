import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
import requests

r = requests.get('http://localhost:3510/akasha/api/dashboard/knowledge-graph?nocache=true')
d = r.json()

with_tc = [n for n in d['nodes'] if n.get('tc') and n['tc'].get('total_lines', 0) > 0]
with_tc_subs = [n for n in d['nodes'] if n.get('tc') and n['tc'].get('total_substations', 0) > 0]
no_tc = [n for n in d['nodes'] if n.get('category', 0) in [2, 3] and (not n.get('tc') or n['tc'].get('total_lines', 0) == 0)]

print(f"Projects with TC lines: {len(with_tc)}")
print(f"Projects with TC substations: {len(with_tc_subs)}")
print(f"Projects without TC data: {len(no_tc)}")

print("\n=== Projects WITH TC lines ===")
for n in with_tc:
    tc = n['tc']
    print(f"  {n['name']}: {tc['total_lines']} lines, {tc['total_substations']} subs, region={tc.get('region')}")

print(f"\n=== Some projects WITHOUT TC ===")
for n in no_tc[:10]:
    tc = n.get('tc')
    if tc:
        print(f"  {n['name']}: lines={tc.get('total_lines', 0)}, subs={tc.get('total_substations', 0)}")
    else:
        print(f"  {n['name']}: tc=None")
