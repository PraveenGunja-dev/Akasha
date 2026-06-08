import requests
import json
import os

AUTH_URL = "https://powerback-api.unada.in/api/v1/user/login"
BASE_URL = "https://transmission-api-v3.unada.in"
CREDENTIALS = {
    "email": "zaid@unada.io",
    "password": "Demo@123"
}

def get_token():
    try:
        res = requests.post(AUTH_URL, json=CREDENTIALS)
        data = res.json()
        if "token" in data:
            return data["token"]
        elif "data" in data and "token" in data["data"]:
            return data["data"]["token"]
        elif "access_token" in data:
            return data["access_token"]
    except Exception as e:
        print("Auth Error:", e)
    return None

def fetch_and_save(endpoint, filename, token):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}{endpoint}"
    print(f"Fetching {url}...")
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        data = res.json()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved {filename}")
    except Exception as e:
        print(f"Error fetching {endpoint}:", e)

if __name__ == "__main__":
    token = get_token()
    if not token:
        print("Failed to get token")
    else:
        print("Token retrieved successfully")
        
        # Fetch key endpoints
        endpoints = [
            ("/api/rajasthan/projects", "samples/rajasthan_projects.json"),
            ("/api/rajasthan/default-data", "samples/rajasthan_default_data.json"),
            ("/api/khavda/projects", "samples/khavda_projects.json"),
            ("/api/khavda/default-data", "samples/khavda_default_data.json"),
            ("/api/khavda/hierarchy/stats", "samples/khavda_hierarchy_stats.json"),
        ]
        
        for ep, file in endpoints:
            fetch_and_save(ep, file, token)
