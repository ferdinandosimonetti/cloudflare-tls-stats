import requests
import argparse
import os

parser = argparse.ArgumentParser(description="Query Cloudflare TLS cyphers for all zones")
parser.add_argument("--api-token", required=True, help="Cloudflare API token")
args = parser.parse_args()
API_TOKEN = args.api_token
#API_TOKEN = os.environ.get("CF_API_TOKEN")  # Zone:Read, Zone Settings:Read
BASE_URL = "https://api.cloudflare.com/client/v4"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}

# Default cipher lists per Cloudflare docs
TLS_CIPHERS = {
    "1.0": [
        "ECDHE-RSA-AES128-SHA",
        "AES128-SHA",
        "AES256-SHA",
    ],
    "1.1": [
        "ECDHE-RSA-AES128-SHA",
        "AES128-SHA",
        "AES256-SHA",
    ],
    "1.2": [
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-CHACHA20-POLY1305",
        "ECDHE-RSA-CHACHA20-POLY1305",
        "AES128-GCM-SHA256",
        "AES256-GCM-SHA384",
        "AES128-SHA256",
        "AES256-SHA256",
    ],
    "1.3": [
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "TLS_AES_128_CCM_SHA256",
        "TLS_AES_128_CCM_8_SHA256",
    ],
}

def list_zones():
    url = f"{BASE_URL}/zones"
    zones, page = [], 1
    while True:
        r = requests.get(url, headers=HEADERS, params={"page": page, "per_page": 50})
        r.raise_for_status()
        data = r.json()
        zones.extend(data["result"])
        if page >= data["result_info"]["total_pages"]:
            break
        page += 1
    return zones

def get_tls_settings(zone_id):
    r = requests.get(f"{BASE_URL}/zones/{zone_id}/settings/min_tls_version", headers=HEADERS)
    r.raise_for_status()
    min_tls = r.json()["result"]["value"]

    r = requests.get(f"{BASE_URL}/zones/{zone_id}/settings/ciphers", headers=HEADERS)
    r.raise_for_status()
    tls12_ciphers = r.json()["result"]["value"]

    # If empty, use default TLS 1.2 ciphers
    if not tls12_ciphers:
        tls12_ciphers = TLS_CIPHERS["1.2"]

    return min_tls, tls12_ciphers

def print_cipher_matrix():
    zones = list_zones()
    for z in zones:
        zone_id, zone_name = z["id"], z["name"]
        min_tls, tls12_ciphers = get_tls_settings(zone_id)

        print(f"\nZone: {zone_name}")
        print(f"  Minimum TLS: {min_tls}")

        # TLS 1.0 / 1.1
        if min_tls <= "1.0":
            print("  TLS 1.0 ciphers:")
            for c in TLS_CIPHERS["1.0"]:
                print(f"    - {c}")
        if min_tls <= "1.1":
            print("  TLS 1.1 ciphers:")
            for c in TLS_CIPHERS["1.1"]:
                print(f"    - {c}")

        # TLS 1.2
        if min_tls <= "1.2":
            print("  TLS 1.2 ciphers:")
            for c in tls12_ciphers:
                print(f"    - {c}")

        # TLS 1.3
        if min_tls <= "1.3":
            print("  TLS 1.3 ciphers:")
            for c in TLS_CIPHERS["1.3"]:
                print(f"    - {c}")

if __name__ == "__main__":
    print_cipher_matrix()