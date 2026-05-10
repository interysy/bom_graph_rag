#!/bin/bash
set -e

echo "Waiting for Fuseki to initialize..."
sleep 5

echo "Create dataset"
python3 fuseki-utilities/setup_fuseki.py

echo "Cleaning DB"
python3 fuseki-utilities/clear_fuseki.py

echo "Running data seeding scripts..."
python3 generate_bom.py
python3 fuseki-utilities/load_ttl.py

echo "Seeding complete. Starting Agent..."
python3 -u agent.py
