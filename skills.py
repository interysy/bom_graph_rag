from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests


BOM_PREFIX = "PREFIX bom: <http://ibom.ai/ontology/bom#>\n"
VALID_VARIANTS = {"SEDAN", "SUV", "COUPE", "HATCH", "ESTATE"}

FUSEKI_QUERY_ENDPOINT = "http://host.docker.internal:3030/apex-bom/sparql" 

FUSEKI_TIMEOUT_SECONDS = float(os.getenv("FUSEKI_TIMEOUT_SECONDS", "20"))


def _normalize_variant_code(variant_code: str) -> str:
    normalized = variant_code.strip().upper()
    if normalized not in VALID_VARIANTS:
        raise ValueError(
            f"Invalid variant_code '{variant_code}'. Must be one of {sorted(VALID_VARIANTS)}"
        )
    return normalized


def _build_system_filter(system_name: Optional[str], subject_var: str = "?system") -> str:
    if not system_name:
        return ""
    escaped = system_name.replace('"', '\\"')
    return f'  {subject_var} bom:systemName "{escaped}" .\n'


def _run_sparql(query: str) -> List[Dict[str, Any]]:
    response = requests.post(
        FUSEKI_QUERY_ENDPOINT,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=FUSEKI_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("results", {}).get("bindings", [])


def _binding_value(binding: Dict[str, Any], key: str, fallback: Any = None) -> Any:
    return binding.get(key, {}).get("value", fallback)


def count_parts(variant_code: str, system_name: Optional[str] = None) -> Dict[str, Any]:
    variant_code = _normalize_variant_code(variant_code)
    system_filter = _build_system_filter(system_name)

    query = f"""{BOM_PREFIX}
SELECT (COALESCE(SUM(?qty), 0) AS ?totalParts)
WHERE {{
  ?vehicle bom:variantCode "{variant_code}" ;
           bom:hasSystem ?system .
{system_filter}  ?system bom:hasAssembly ?assembly .
  ?assembly bom:hasPartLink ?partLink .
  ?partLink bom:quantity ?qty .
}}
"""
    rows = _run_sparql(query)
    total_parts = int(float(_binding_value(rows[0], "totalParts", 0))) if rows else 0
    return {
        "skill": "count_parts",
        "variant_code": variant_code,
        "system_name": system_name,
        "total_parts": total_parts,
    }


def count_unique_parts(variant_code: str, system_name: Optional[str] = None) -> Dict[str, Any]:
    variant_code = _normalize_variant_code(variant_code)
    system_filter = _build_system_filter(system_name)

    query = f"""{BOM_PREFIX}
SELECT (COUNT(DISTINCT ?part) AS ?uniqueParts)
WHERE {{
  ?vehicle bom:variantCode "{variant_code}" ;
           bom:hasSystem ?system .
{system_filter}  ?system bom:hasAssembly ?assembly .
  ?assembly bom:hasPartLink ?partLink .
  ?partLink bom:part ?part .
}}
"""
    rows = _run_sparql(query)
    unique_parts = int(float(_binding_value(rows[0], "uniqueParts", 0))) if rows else 0
    return {
        "skill": "count_unique_parts",
        "variant_code": variant_code,
        "system_name": system_name,
        "unique_parts": unique_parts,
    }


SKILLS = {
    "count_parts": {
        "description": "Count the total number of parts (sum of quantities) in a vehicle variant's BOM.",
        "parameters": {
            "variant_code": {
                "type": "string",
                "enum": sorted(VALID_VARIANTS),
                "description": "The car variant to query.",
                "required": True,
            },
            "system_name": {
                "type": "string",
                "description": "Optional: restrict count to a specific system (e.g. 'Engine').",
                "required": False,
            },
        },
        "returns": "integer — total part count",
        "function": count_parts,
    },
    "count_unique_parts": {
        "description": "Count distinct part URIs in a vehicle variant's BOM, optionally filtered by system.",
        "parameters": {
            "variant_code": {
                "type": "string",
                "enum": sorted(VALID_VARIANTS),
                "description": "The car variant to query.",
                "required": True,
            },
            "system_name": {
                "type": "string",
                "description": "Optional: restrict count to a specific system (e.g. 'Engine').",
                "required": False,
            },
        },
        "returns": "integer — distinct part count",
        "function": count_unique_parts,
    }
}


if __name__ == "__main__":
    print(count_unique_parts('SEDAN', 'Engine'))
