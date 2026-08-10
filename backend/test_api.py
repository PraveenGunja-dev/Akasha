from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

response = client.get("/api/project-360")
print("Status Code:", response.status_code)
if response.status_code != 200:
    print("Response Body:", response.text)
