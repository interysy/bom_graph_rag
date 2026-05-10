import os

import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

AUTH_HEADER = ("admin", "admin")

ENV_VARIABLE_FUSEKI_HOST = "FUSEKI_HOST"
ENV_VARIABLE_FUSEKI_PORT = "FUSEKI_PORT"

SUCCESS_STATUS_CODES = {200, 201, 204}

CLEAR_COMMAND_PAYLOAD = {"update": "CLEAR ALL"}


def clear_dataset():
    host = os.getenv(ENV_VARIABLE_FUSEKI_HOST)
    port = os.getenv(ENV_VARIABLE_FUSEKI_PORT)

    if not host or not port:
        logger.error(
            f"❌ Error: {ENV_VARIABLE_FUSEKI_HOST} or {ENV_VARIABLE_FUSEKI_PORT} missing."
        )
        exit(1)

    base_url = f"http://{host}:{port}/apex-bom"
    update_endpoint = f"{base_url}/update"
    logger.info(f"Clearing dataset at {update_endpoint}...")

    try:
        response = requests.post(
            update_endpoint,
            data=CLEAR_COMMAND_PAYLOAD,
            auth=AUTH_HEADER,
        )
        if response.status_code in SUCCESS_STATUS_CODES:
            logger.success("✅ Dataset cleared.")
        else:
            logger.error(f"❌ Failed to clear. Status: {response.status_code}, {response.text}")
            exit(1)
    except requests.exceptions.RequestException as exception:
        logger.error(f"❌ Connection error during clear: {exception}")
        exit(1)


if __name__ == "__main__":
    clear_dataset()
