import requests
import urllib3
import json
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

AUTH_URL = 'https://powerback-api.unada.in/api/v1/user/login'
CREDENTIALS = {'email': 'zaid@unada.io', 'password': 'Demo@123'}

res = requests.post(AUTH_URL, json=CREDENTIALS, verify=False)
token = res.json().get('data', {}).get('token')
headers = {'Authorization': f'Bearer {token}'}

def get_api_lines(region):
    proj_res = requests.get(f'https://transmission-api-v3.unada.in/api/{region}/projects', headers=headers, verify=False)
    current_proj = next((p for p in proj_res.json().get('projects', []) if p.get('is_current')), None)
    if not current_proj: return None
    pid = current_proj['id']
    details_res = requests.get(f'https://transmission-api-v3.unada.in/api/{region}/projects/{pid}', headers=headers, verify=False)
    network = details_res.json().get('data', {}).get('network', {})
    return network.get('edges', [])

raj_edges = get_api_lines('rajasthan')
khavda_edges = get_api_lines('khavda')

def print_unique_projects(edges, region_name):
    unique_projects = set()
    for e in edges:
        for p in e.get('project', []):
            unique_projects.add(p)
    print(f'--- {region_name} API PROJECT ALIASES ---')
    for p in sorted(unique_projects):
        print(f" - '{p}'")
    print()

print_unique_projects(raj_edges, 'RAJASTHAN')
print_unique_projects(khavda_edges, 'KHAVDA')
