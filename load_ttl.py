import requests
from pathlib import Path

# Configuration
FILENAME = "apex_bom.ttl"
# Using the GSP (Graph Store Protocol) endpoint
ENDPOINT = "http://host.docker.internal:3030/apex-bom/data" 
AUTH_HEADER = ("admin", "admin")
HEADERS = {"Content-Type": "text/turtle"}
SUCCESS_STATUS_CODES = [200, 201, 204]

def load_ttl():
    path = Path(FILENAME)
    
    if not path.exists():
        print(f"❌ Error: {FILENAME} not found. Check your current directory.")
        return

    print(f"Attempting to load {FILENAME} to {ENDPOINT}...")

    with open(path, "rb") as file:
        try:
            # Fuseki requires the 'default' parameter to target the default graph
            response = requests.post(
                ENDPOINT,
                params={"default": ""},
                data=file,
                headers=HEADERS,
                auth=AUTH_HEADER
            )

            # Check for success
            if response.status_code in [200, 201, 204]:
                print("✅ BOM loaded successfully!")
            else:
                print(f"❌ Failed to load. Status Code: {response.status_code}")
                print(f"Response Body: {response.text}")

        except requests.exceptions.ConnectionError:
            print("❌ Connection Error: Could not reach Fuseki.")
            print("Ensure Fuseki is running and 'host.docker.internal' is accessible.")

if __name__ == "__main__":
    load_ttl()
