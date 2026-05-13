import json
import requests
import config

BASE_URL = "https://api.rd.services"

def get_access_token():
    response = requests.post(
        f"{BASE_URL}/auth/token",
        params={"token_by": "refresh_token"},
        json={
            "client_id": config.RD_CLIENT_ID,
            "client_secret": config.RD_CLIENT_SECRET,
            "refresh_token": config.RD_REFRESH_TOKEN,
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]

access_token = get_access_token()
headers = {"Authorization": f"Bearer {access_token}"}

# Pega a primeira pagina da segmentacao
seg_response = requests.get(f"{BASE_URL}/platform/segmentations", headers=headers)
segmentations = seg_response.json().get("segmentations", [])
seg_id = segmentations[0]["id"]

contacts_response = requests.get(
    f"{BASE_URL}/platform/segmentations/{seg_id}/contacts",
    headers=headers,
    params={"page": 1, "page_size": 3},
)
contacts = contacts_response.json().get("contacts", [])

# Pega detalhes do primeiro contato e mostra todos os campos
uuid = contacts[0]["uuid"]
detail_response = requests.get(f"{BASE_URL}/platform/contacts/{uuid}", headers=headers)
data = detail_response.json()
contact = data.get("contact", data)

print("=== TODOS OS CAMPOS DO CONTATO ===\n")
for key, value in contact.items():
    if value not in (None, "", [], {}):
        print(f"{key}: {value}")

print("\n=== CAMPOS cf_ (customizados) ===\n")
for key, value in contact.items():
    if key.startswith("cf_"):
        print(f"{key}: {value}")
