import requests

try:
    res = requests.get("http://localhost:3510/api/dashboard/api/projects/FY25-P06/slr?filter_code=ALL")
    print(res.status_code)
    print(res.json())
except Exception as e:
    print(e)
