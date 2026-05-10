import requests
from pathlib import Path
from dotenv import load_dotenv
import os
from loguru import logger

load_dotenv()

FILENAME = "apex_bom.ttl"
AUTH_HEADER = ("admin", "admin")
HEADERS = {"Content-Type": "text/turtle"}
SUCCESS_STATUS_CODES = [200, 201, 204]

ENV_VARIABLE_FUSEKI_HOST = "FUSEKI_HOST"
ENV_VARIABLE_FUSEKI_PORT = "FUSEKI_PORT"

def load_ttl():
    host = os.getenv(ENV_VARIABLE_FUSEKI_HOST)
    port = os.getenv(ENV_VARIABLE_FUSEKI_PORT)

    if not host or not port:
        logger.error(f"❌ Error: {ENV_VARIABLE_FUSEKI_HOST} or {ENV_VARIABLE_FUSEKI_PORT} missing.")
        exit(1)

    endpoint = f"http://{host}:{port}/apex-bom/data" 
    path = Path(FILENAME)
    
    if not path.exists():
        logger.error(f"❌ Error: {FILENAME} not found. Check your current directory.")
        exit(1)

    logger.info(f"Attempting to load {FILENAME} to {endpoint}...")

    with open(path, "rb") as file:
        try:
            response = requests.post(
                endpoint,
                data=file,
                headers=HEADERS,
                auth=AUTH_HEADER
            )

            if response.status_code in SUCCESS_STATUS_CODES:
                logger.success("✅ BOM loaded successfully!")
            else:
                logger.error(f"❌ Failed to load. Status Code: {response.status_code}")
                logger.error(f"Response Body: {response.text}")
                exit(1)

        except requests.exceptions.ConnectionError:
            logger.error("❌ Connection Error: Could not reach Fuseki.")
            logger.error("Ensure Fuseki is running and 'host.docker.internal' is accessible.")
            exit(1)

if __name__ == "__main__":
    load_ttl()
