FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py skills.py generate_bom.py docker-entrypoint.sh .
COPY fuseki-utilities ./fuseki-utilities

RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
