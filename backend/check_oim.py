import requests

url = "https://tiles.openinframap.org/power/6/45/28.png"
response = requests.get(url)
print(f"URL 1 Status: {response.status_code}")

url2 = "https://tiles-eu.openinframap.org/power/6/45/28.png"
response2 = requests.get(url2)
print(f"URL 2 Status: {response2.status_code}")

url3 = "https://a.tiles.openinframap.org/power/{z}/{x}/{y}.png"

