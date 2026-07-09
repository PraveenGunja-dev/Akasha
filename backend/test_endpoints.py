import requests

portfolio = "Solar Khavda"

def check_endpoint(url):
    try:
        resp = requests.get(url)
        data = resp.json()
        if isinstance(data, list):
            print(f"{url}: {len(data)} items")
        elif isinstance(data, dict):
            if "summary" in data:
                print(f"{url}: {data['summary'].get('total_projects', 'N/A')} total_projects")
            elif "projects" in data:
                print(f"{url}: {len(data['projects'])} projects")
            else:
                print(f"{url}: (dict keys: {list(data.keys())})")
    except Exception as e:
        print(f"{url}: Error {e}")

urls = [
    f"http://localhost:8000/api/dashboard/summary?portfolio={portfolio}",
    f"http://localhost:8000/api/summary?portfolio={portfolio}",
    f"http://localhost:8000/api/financials?portfolio={portfolio}",
    f"http://localhost:8000/api/logistics?portfolio={portfolio}",
    f"http://localhost:8000/api/pmag/dashboard?portfolio={portfolio}"
]

for url in urls:
    check_endpoint(url)
