import os
from typing import Any, Dict, List, Optional
import requests
from loguru import logger
from pydantic import BaseModel, Field

BOM_PREFIX = "PREFIX bom: <http://ibom.ai/ontology/bom#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
VALID_VARIANTS = {"SEDAN", "SUV", "COUPE", "HATCH", "ESTATE"}
VALID_SYSTEMS = [
        "ENGINE", "TRANSMISSION", "CHASSIS & FRAME", "SUSPENSION & STEERING", "BRAKES", "BODY & EXTERIOR", "ELECTRICAL & ELECTRONICS"
]

FUSEKI_QUERY_ENDPOINT = "http://host.docker.internal:3030/apex-bom/sparql" 
FUSEKI_TIMEOUT_SECONDS = 30


# MODELS

class PartCountResponse(BaseModel):
    skill: str = "count_parts"
    variant_code: str
    system_name: Optional[str]
    total_parts: int = Field(description="The total quantity of parts found.")

    def __str__(self) -> str:
        scope = f"system '{self.system_name}'" if self.system_name else "all systems"
        return f"<{self.variant_code}> Total parts in {scope}: {self.total_parts}"


class UniquePartCountResponse(BaseModel):
    skill: str = "count_unique_parts"
    variant_code: str
    system_name: Optional[str]
    total_parts: int = Field(description="The total quantity of unique parts found.")

    def __str__(self) -> str:
        scope = f"system '{self.system_name}'" if self.system_name else "all systems"
        return f"<{self.variant_code}> Unique parts in {scope}: {self.total_parts}"


class SystemWeightEntry(BaseModel):
    system_name: str
    total_weight_kg: float

    def __str__(self) -> str:
        return f"{self.system_name}: {self.total_weight_kg:.2f}kg"


class HeaviestSystemResponse(BaseModel):
    skill: str = "heaviest_system"
    variant_code: Optional[str]
    top_n: int
    systems: List[SystemWeightEntry]

    def __str__(self) -> str:
        scope = f"for {self.variant_code}" if self.variant_code else "across the fleet"
        header = f"--- Top {self.top_n} Heaviest Systems {scope} ---"
        if not self.systems:
            return f"{header}\nNo data found."
        
        entries = "\n".join([f"  {i+1}. {entry}" for i, entry in enumerate(self.systems)])
        return f"{header}\n{entries}"


# UTILITIES
def _normalize_variant_code(variant_code: str) -> str:
    ERROR_MESSAGE = f"Invalid variant_code '{variant_code}'. Must be one of {VALID_VARIANTS}"

    normalized = variant_code.strip().upper()
    if normalized not in VALID_VARIANTS:
        logger.error(ERROR_MESSAGE)
        raise ValueError(ERROR_MESSAGE)

    return normalized

def _normalize_system(system_name : str) -> str: 
    ERROR_MESSAGE = f"Invalid system_name '{system_name}'. Must be one of {VALID_SYSTEMS}"

    normalized = system_name.strip().upper()
    if normalized not in VALID_SYSTEMS:
        logger.error(ERROR_MESSAGE)
        raise ValueError(ERROR_MESSAGE)

    return normalized



def _build_system_filter(system_name: Optional[str], subject_var: str = "?system") -> str:
    if not system_name:
        return ""

    try:
        normalised_system_name = _normalize_system(system_name)
    except ValueError: 
        logger.warning(f"Unable to normalize system name {system_name}. Continuing without system filter.")
        return ""


    escaped = system_name.replace('"', '\\"')
    return f'  {subject_var} bom:systemName "{escaped}" .\n'


def _build_variant_filter(variant_code : str) -> str: 
    normalised_variant_code = _normalize_variant_code(variant_code)

    escaped = normalised_variant_code.replace('"', '\\"')
    return f' ?variant bom:variantCode "{escaped}" .\n'
    


def _run_sparql(query: str) -> List[Dict[str, Any]]:
    HEADERS = {"Accept": "application/sparql-results+json"}

    response = requests.post(
        FUSEKI_QUERY_ENDPOINT,
        data={"query": query},
        headers=HEADERS,
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

    VARIABLE_NAME = "totalParts"

    query = f"""{BOM_PREFIX}
        SELECT (COALESCE(SUM(?qty), 0) AS ?{VARIABLE_NAME})
        WHERE {{
        ?vehicle bom:variantCode "{variant_code}" ;
                bom:hasSystem ?system .
        {system_filter}  ?system bom:hasAssembly ?assembly .
        ?assembly bom:hasPartLink ?partLink .
        ?partLink bom:quantity ?qty .
        }}
    """


    rows = _run_sparql(query)
    raw_val = _binding_value(rows[0], VARIABLE_NAME, 0) if rows else 0


    return PartCountResponse(
        variant_code=variant_code,
        system_name=system_name,
        total_parts=int(float(raw_val))
    )


def count_unique_parts(variant_code: str, system_name: Optional[str] = None) -> Dict[str, Any]:
    variant_code = _normalize_variant_code(variant_code)
    system_filter = _build_system_filter(system_name)

    VARIABLE_NAME = "uniqueParts"

    query = f"""{BOM_PREFIX}
        SELECT (COUNT(DISTINCT ?part) AS ?{VARIABLE_NAME})
        WHERE {{
        ?vehicle bom:variantCode "{variant_code}" ;
                bom:hasSystem ?system .
        {system_filter}  ?system bom:hasAssembly ?assembly .
        ?assembly bom:hasPartLink ?partLink .
        ?partLink bom:part ?part .
        }}
    """

    rows = _run_sparql(query)
    raw_val = _binding_value(rows[0], VARIABLE_NAME, 0) if rows else 0

    return PartCountResponse(
        variant_code=variant_code,
        system_name=system_name,
        total_parts=int(float(raw_val))
    )

def heaviest_system(variant_code: Optional[str] = None, top_n: int = 1) -> HeaviestSystemResponse:
    variant_filter = ""

    if variant_code:
        variant_code = _normalize_variant_code(variant_code)
        variant_filter = f'?vehicle bom:variantCode "{variant_code}" .'
    
    VARIABLE_SYSTEM_NAME = "systemName"
    VARIABLE_WEIGHT = "totalWeightKg"

    query = f"""{BOM_PREFIX}
        SELECT ?{VARIABLE_SYSTEM_NAME} (SUM(?qty * ?weight) AS ?{VARIABLE_WEIGHT})
        WHERE {{
            ?vehicle bom:hasSystem ?system .
            {variant_filter}
            ?system   bom:systemName   ?{VARIABLE_SYSTEM_NAME} ;
                      bom:hasAssembly  ?assembly .
            ?assembly bom:hasPartLink  ?partLink .
            ?partLink bom:part         ?part ;
                      bom:quantity     ?qty .
            ?part     bom:unitWeightKg ?weight .
        }}
        GROUP BY ?{VARIABLE_SYSTEM_NAME}
        ORDER BY DESC(?{VARIABLE_WEIGHT})
        LIMIT {top_n}
    """

    rows = _run_sparql(query)
    
    results = []
    for row in rows:
        results.append(
            SystemWeightEntry(
                system_name=_binding_value(row, VARIABLE_SYSTEM_NAME),
                total_weight_kg=round(float(_binding_value(row, VARIABLE_WEIGHT, 0)), 2)
            )
        )

    return HeaviestSystemResponse(
        variant_code=variant_code,
        top_n=top_n,
        systems=results
    )

SKILLS = {
    "count_parts": {
        "description": "Count the total number of parts (sum of quantities) in a vehicle variant's BOM.",
        "parameters": {
            "variant_code": {
                "type": "string",
                "enum": VALID_VARIANTS,
                "description": "The car variant to query.",
                "required": True,
            },
            "system_name": {
                "type": "string",
                "enum": VALID_SYSTEMS,
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
                "enum": VALID_VARIANTS,
                "description": "The car variant to query.",
                "required": True,
            },
            "system_name": {
                "type": "string",
                "enum": VALID_SYSTEMS,
                "description": "Optional: restrict count to a specific system (e.g. 'Engine').",
                "required": False,
            },
        },
        "returns": "integer — distinct part count",
        "function": count_unique_parts,
    }, 
    "heaviest_system" : {
        "description" : "Fetch the heaviest system in the Graph or the heaviest system in the Graph for a specific Variant.",
        "parameters" : {
            "variant_code": {
                "type": "string",
                "enum": VALID_VARIANTS,
                "description": "Optional: The car variant to query. If omitted, queries across the entire fleet.",
                "required": False,
            },
            "top_n": {
                "type": "integer",
                "description": "Optional: The number of top heaviest systems to return (default is 1).",
                "required": False,
            }
        },
        "returns": "HeaviestSystemResponse object — list of top N systems and their weights in kg",
        "function": heaviest_system,
    }
}


if __name__ == "__main__":
    print(count_parts('SEDAN', 'Engine'))
    print(count_unique_parts('SEDAN', 'Engine'))
    print(heaviest_system('SEDAN', 5))
    print(heaviest_system(top_n = 5))
