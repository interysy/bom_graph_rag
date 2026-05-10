import os
import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

ENV_VARIABLE_FUSEKI_HOST = "FUSEKI_HOST"
ENV_VARIABLE_FUSEKI_PORT = "FUSEKI_PORT"


def create_dataset():
    host = os.getenv(ENV_VARIABLE_FUSEKI_HOST)
    port = os.getenv(ENV_VARIABLE_FUSEKI_PORT)

    if not host or not port:
        logger.error(
            f"❌ Error: {ENV_VARIABLE_FUSEKI_HOST} or {ENV_VARIABLE_FUSEKI_PORT} missing."
        )
        exit(1)
    
    endpoint = f"http://{host}:{port}/$/datasets"
    
    auth = ("admin", "admin")
    data = {
        "dbName": "apex-bom",
        "dbType": "tdb2"
    }

    logger.info(f"Checking/Creating dataset 'apex-bom' at {endpoint}...")

    try:
        response = requests.post(
            endpoint,
            auth=auth,
            data=data
        )

        if response.status_code == 200:
            logger.success("✅ Dataset created successfully (or already exists).")
        elif response.status_code == 409:
            logger.info("ℹ️ Dataset 'apex-bom' already exists.")
        else:
            logger.error(f"❌ Failed to setup dataset. Status: {response.status_code}")
            logger.error(f"Response: {response.text}")
            exit(1)

    except requests.exceptions.ConnectionError:
        logger.error(f"❌ Connection Error: Could not reach Fuseki at {host}:{port}")
        logger.error("If running locally, set FUSEKI_HOST=localhost. If in Docker, use FUSEKI_HOST=fuseki.")
        exit(1)

if __name__ == "__main__":
    create_dataset()