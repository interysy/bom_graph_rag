#!/bin/bash
set -e

echo "Waiting for Fuseki to initialize..."
sleep 5 

echo "Running data seeding scripts..."
python3 generate_bom.py
python3 load_ttl.py

echo "Seeding complete. Starting Agent..."
python3 -u agent.py