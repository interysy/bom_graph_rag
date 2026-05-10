from typing import Any, Dict, List, Optional, Union
import os
import requests
from loguru import logger
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from generate_bom import SYSTEMS

ENV_VARIABLE_FUSEKI_HOST = "FUSEKI_HOST"
ENV_VARIABLE_FUSEKI_PORT = "FUSEKI_PORT"

BOM_PREFIX = "PREFIX bom: <http://ibom.ai/ontology/bom#>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"

VARIANT_CODES = sorted(["COUPE", "ESTATE", "HATCH", "SEDAN", "SUV"])
SYSTEM_NAMES = sorted(SYSTEMS)
COMPARE_METRICS = sorted(["total_cost", "total_parts", "total_weight"])

FUSEKI_TIMEOUT_SECONDS = 30


load_dotenv()


fuseki_host = os.getenv(ENV_VARIABLE_FUSEKI_HOST)
fuseki_port = os.getenv(ENV_VARIABLE_FUSEKI_PORT)

if not fuseki_host or not fuseki_port: 
    error_message = f"❌ Error: {ENV_VARIABLE_FUSEKI_HOST} or {ENV_VARIABLE_FUSEKI_PORT} missing."
    logger.error(error_message)
    raise ValueError(error_message)

fuseki_query_endpoint = f"http://{fuseki_host}:{fuseki_port}/apex-bom/sparql"

_LOG_QUERY_SNIP_LEN = 200


class SkillExecutionError(RuntimeError):
    """Fuseki or transport failure while running a skill query."""


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


class SystemCostEntry(BaseModel): 
    system_name : str
    total_cost : float

    def __str__(self) -> str:
        return f"{self.system_name}: £{self.total_cost:,.2f}"



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

class CostliestSystemResponse(BaseModel): 
    skill : str = "costliest_system"
    variant_code : Optional[str] 
    top_n : int 
    systems : List[SystemCostEntry]

    def __str__(self) -> str:
        scope = f"for {self.variant_code}" if self.variant_code else "across the fleet"
        header = f"--- Top {self.top_n} Costliest Systems {scope} ---"
        if not self.systems:
            return f"{header}\nNo data found."
        
        entries = "\n".join([f"  {i+1}. {entry}" for i, entry in enumerate(self.systems)])
        return f"{header}\n{entries}"

class SystemComplexityEntry(BaseModel):
    system_name: str
    total_parts: int

    def __str__(self) -> str:
        return f"{self.system_name}: {self.total_parts} parts"


class MostComplexSystemResponse(BaseModel):
    skill: str = "most_complex_system"
    variant_code: Optional[str]
    top_n: int
    systems: List[SystemComplexityEntry]

    def __str__(self) -> str:
        scope = f"for {self.variant_code}" if self.variant_code else "across the fleet"
        header = f"--- Top {self.top_n} Most Complex Systems {scope} ---"
        if not self.systems:
            return f"{header}\nNo data found."
        
        entries = "\n".join([f"  {i+1}. {entry}" for i, entry in enumerate(self.systems)])
        return f"{header}\n{entries}"


class VariantMetricEntry(BaseModel):
    variant_code: str
    value: float

    def __str__(self) -> str:
        if self.value == int(self.value):
            return f"{self.variant_code}: {int(self.value)}"
        return f"{self.variant_code}: {self.value:,.2f}"


class CompareVariantsResponse(BaseModel):
    skill: str = "compare_variants"
    metric: str
    system_name: Optional[str]
    variants: List[VariantMetricEntry]

    def __str__(self) -> str:
        scope = f" (system: '{self.system_name}')" if self.system_name else " (all systems)"
        labels = {
            "total_parts": "total part count (sum of quantities)",
            "total_weight": "total weight (kg)",
            "total_cost": "total material cost (GBP)",
        }
        header = f"--- Variant comparison: {labels.get(self.metric, self.metric)}{scope} ---"
        if not self.variants:
            return f"{header}\nNo data found."
        entries = "\n".join(f"  {e}" for e in self.variants)
        return f"{header}\n{entries}"


SkillResponseUnion = Union[
    CompareVariantsResponse,
    MostComplexSystemResponse,
    CostliestSystemResponse,
    HeaviestSystemResponse,
    UniquePartCountResponse,
    PartCountResponse,
]

# UTILITIES
def _normalize_variant_code(variant_code: str) -> str:
    ERROR_MESSAGE = f"Invalid variant_code '{variant_code}'. Must be one of {VARIANT_CODES}"

    normalized = variant_code.strip().upper()
    if normalized not in VARIANT_CODES:
        logger.error(ERROR_MESSAGE)
        raise ValueError(ERROR_MESSAGE)

    return normalized


def _normalize_system_name(system_name: Optional[str]) -> Optional[str]:
    if system_name is None or not str(system_name).strip():
        return None

    normalised = " ".join(system_name.strip().split()).casefold()
    for label in SYSTEM_NAMES:
        if " ".join(label.split()).casefold() == normalised:
            return label
    error_message = f"Invalid system_name {system_name!r}. Must be one of {SYSTEM_NAMES}"
    logger.error(error_message)
    raise ValueError(error_message)


def _ttl_string_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_system_filter(canonical_system: Optional[str], subject_var: str = "?system") -> str:
    if canonical_system is None:
        return ""
    escaped = _ttl_string_literal(canonical_system)
    return f'  {subject_var} bom:systemName "{escaped}" .\n'


def _normalize_compare_metric(metric: str) -> str:
    normalized = metric.strip().lower().replace("-", "_")
    if normalized not in COMPARE_METRICS:
        msg = f"Invalid metric '{metric}'. Must be one of {COMPARE_METRICS}"
        logger.error(msg)
        raise ValueError(msg)
    return normalized



def _build_variant_filter(variant_code : str) -> str: 
    normalised_variant_code = _normalize_variant_code(variant_code)

    escaped = _ttl_string_literal(normalised_variant_code)
    return f' ?vehicle bom:variantCode "{escaped}" .\n'


def _run_sparql(query: str) -> List[Dict[str, Any]]:
    HEADERS = {"Accept": "application/sparql-results+json"}
    query_payload = {"query": query}

    RESULTS_KEY = "results"
    BINDINGS_KEY = "bindings"

    q_snip = query.strip().replace("\n", " ")[:_LOG_QUERY_SNIP_LEN]

    try:
        response = requests.post(
            fuseki_query_endpoint,
            data=query_payload,
            headers=HEADERS,
            timeout=FUSEKI_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exception:
        logger.exception("SPARQL request failed (query starts {!r})", q_snip)
        raise SkillExecutionError(
            f"SPARQL request to Fuseki failed (query starts: {q_snip!r})"
        ) 

    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError as exc:
        text = (response.text or "")[:2000]
        logger.error(
            "Fuseki returned non-JSON (status {}), body (truncated): {}",
            response.status_code,
            text,
        )
        raise SkillExecutionError(
            f"Fuseki response was not JSON (query starts: {q_snip!r}). "
            f"Body (truncated): {text[:500]!r}"
        ) from exc

    if RESULTS_KEY not in payload:
        text = (response.text or "")[:2000]
        logger.error("SPARQL JSON missing 'results' (truncated body): {}", text)
        raise SkillExecutionError(
            f"SPARQL response missing 'results' (query starts: {q_snip!r}). "
            f"Body (truncated): {text[:500]!r}"
        )

    bindings = payload[RESULTS_KEY].get(BINDINGS_KEY)
    if bindings is None or not isinstance(bindings, list):
        logger.error(
            "SPARQL results.bindings missing or not a list: {!r}",
            payload.get("results"),
        )
        raise SkillExecutionError(
            f"SPARQL results.bindings is not a list (query starts: {q_snip!r})"
        )
    return bindings


def _binding_value(binding: Dict[str, Any], key: str, fallback: Any = None) -> Any:
    return binding.get(key, {}).get("value", fallback)


def count_parts(variant_code: str, system_name: Optional[str] = None) -> PartCountResponse:
    normalized_variant_code = _normalize_variant_code(variant_code)
    canonical_system = _normalize_system_name(system_name)
    system_filter = _build_system_filter(canonical_system)

    VARIABLE_NAME = "totalParts"

    query = f"""{BOM_PREFIX}
        SELECT (COALESCE(SUM(?qty), 0) AS ?{VARIABLE_NAME})
        WHERE {{
        ?vehicle bom:variantCode "{normalized_variant_code}" ;
                bom:hasSystem ?system .
        {system_filter}  ?system bom:hasAssembly ?assembly .
        ?assembly bom:hasPartLink ?partLink .
        ?partLink bom:quantity ?qty .
        }}
    """


    rows = _run_sparql(query)
    raw_val = _binding_value(rows[0], VARIABLE_NAME, 0) if rows else 0


    return PartCountResponse(
        variant_code=normalized_variant_code,
        system_name=canonical_system,
        total_parts=int(float(raw_val))
    )


def count_unique_parts(variant_code: str, system_name: Optional[str] = None) -> UniquePartCountResponse:
    normalized_variant_code = _normalize_variant_code(variant_code)
    canonical_system = _normalize_system_name(system_name)
    system_filter = _build_system_filter(canonical_system)

    VARIABLE_NAME = "uniqueParts"

    query = f"""{BOM_PREFIX}
        SELECT (COUNT(DISTINCT ?part) AS ?{VARIABLE_NAME})
        WHERE {{
        ?vehicle bom:variantCode "{normalized_variant_code}" ;
                bom:hasSystem ?system .
        {system_filter}  ?system bom:hasAssembly ?assembly .
        ?assembly bom:hasPartLink ?partLink .
        ?partLink bom:part ?part .
        }}
    """

    rows = _run_sparql(query)
    raw_val = _binding_value(rows[0], VARIABLE_NAME, 0) if rows else 0

    return UniquePartCountResponse(
        variant_code=normalized_variant_code,
        system_name=canonical_system,
        total_parts=int(float(raw_val))
    )

def heaviest_system(variant_code: Optional[str] = None, top_n: int = 1) -> HeaviestSystemResponse:
    variant_filter = ""
    normalized_variant_code: Optional[str] = None

    if variant_code is not None and str(variant_code).strip():
        normalized_variant_code = _normalize_variant_code(variant_code)
        variant_filter = _build_variant_filter(variant_code)
    
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
        variant_code=normalized_variant_code,
        top_n=top_n,
        systems=results
    )


def costliest_system(variant_code: Optional[str] = None, top_n: int = 1) -> CostliestSystemResponse:
    variant_filter = ""
    normalized_variant_code: Optional[str] = None

    if variant_code is not None and str(variant_code).strip():
        normalized_variant_code = _normalize_variant_code(variant_code)
        variant_filter = _build_variant_filter(variant_code)
    
    VARIABLE_SYSTEM_NAME = "systemName"
    VARIABLE_COST = "totalCost"

    query = f"""{BOM_PREFIX}
        SELECT ?{VARIABLE_SYSTEM_NAME} (SUM(?qty * ?price) AS ?{VARIABLE_COST})
        WHERE {{
            ?vehicle bom:hasSystem ?system .
            {variant_filter}
            ?system   bom:systemName   ?{VARIABLE_SYSTEM_NAME} ;
                      bom:hasAssembly  ?assembly .
            ?assembly bom:hasPartLink  ?partLink .
            ?partLink bom:part         ?part ;
                      bom:quantity     ?qty .
            ?part     bom:unitCostGBP    ?price .
        }}
        GROUP BY ?{VARIABLE_SYSTEM_NAME}
        ORDER BY DESC(?{VARIABLE_COST})
        LIMIT {top_n}
    """

    rows = _run_sparql(query)

    
    results = []
    for row in rows:
        results.append(
            SystemCostEntry(
                system_name=_binding_value(row, VARIABLE_SYSTEM_NAME),
                total_cost=round(float(_binding_value(row, VARIABLE_COST, 0)), 2)
            )
        )

    return CostliestSystemResponse(
        variant_code=normalized_variant_code,
        top_n=top_n,
        systems=results
    )


def most_complex_system(variant_code: Optional[str] = None, top_n: int = 1) -> MostComplexSystemResponse:
    variant_filter = ""
    normalized_variant_code: Optional[str] = None

    if variant_code is not None and str(variant_code).strip():
        normalized_variant_code = _normalize_variant_code(variant_code)
        variant_filter = _build_variant_filter(variant_code)
    
    VARIABLE_SYSTEM_NAME = "systemName"
    VARIABLE_COMPLEXITY = "totalParts"

    query = f"""{BOM_PREFIX}
        SELECT ?{VARIABLE_SYSTEM_NAME} (SUM(?qty) AS ?{VARIABLE_COMPLEXITY})
        WHERE {{
            ?vehicle bom:hasSystem ?system .
            {variant_filter}
            ?system   bom:systemName   ?{VARIABLE_SYSTEM_NAME} ;
                      bom:hasAssembly  ?assembly .
            ?assembly bom:hasPartLink  ?partLink .
            ?partLink bom:quantity     ?qty .
        }}
        GROUP BY ?{VARIABLE_SYSTEM_NAME}
        ORDER BY DESC(?{VARIABLE_COMPLEXITY})
        LIMIT {top_n}
    """

    rows = _run_sparql(query)
    
    results = []
    for row in rows:
        results.append(
            SystemComplexityEntry(
                system_name=_binding_value(row, VARIABLE_SYSTEM_NAME),
                total_parts=int(float(_binding_value(row, VARIABLE_COMPLEXITY, 0)))
            )
        )

    return MostComplexSystemResponse(
        variant_code=normalized_variant_code,
        top_n=top_n,
        systems=results
    )


def compare_variants(
    metric: str,
    system_name: Optional[str] = None,
) -> CompareVariantsResponse:
    metric_key = _normalize_compare_metric(metric)
    canonical_system = _normalize_system_name(system_name)
    system_filter = _build_system_filter(canonical_system)

    var_code = "variantCode"
    var_metric = "metricValue"

    if metric_key == "total_parts":
        agg = f"(COALESCE(SUM(?qty), 0) AS ?{var_metric})"
        extra_triples = """
        ?assembly bom:hasPartLink ?partLink .
        ?partLink bom:quantity ?qty .
        """
    elif metric_key == "total_weight":
        agg = f"(COALESCE(SUM(?qty * ?weight), 0) AS ?{var_metric})"
        extra_triples = """
        ?assembly bom:hasPartLink ?partLink .
        ?partLink bom:part ?part ;
                  bom:quantity ?qty .
        ?part bom:unitWeightKg ?weight .
        """
    else:
        agg = f"(COALESCE(SUM(?qty * ?price), 0) AS ?{var_metric})"
        extra_triples = """
        ?assembly bom:hasPartLink ?partLink .
        ?partLink bom:part ?part ;
                  bom:quantity ?qty .
        ?part bom:unitCostGBP ?price .
        """

    query = f"""{BOM_PREFIX}
        SELECT ?{var_code} {agg}
        WHERE {{
          ?vehicle bom:variantCode ?{var_code} ;
                   bom:hasSystem ?system .
          {system_filter}?system bom:hasAssembly ?assembly .
          {extra_triples}
        }}
        GROUP BY ?{var_code}
        ORDER BY DESC(?{var_metric})
    """

    rows = _run_sparql(query)
    variants: List[VariantMetricEntry] = []
    for row in rows:
        code = _binding_value(row, var_code)
        raw = _binding_value(row, var_metric, 0)
        val = float(raw) if raw is not None else 0.0
        if metric_key == "total_parts":
            val = float(int(round(val)))
        else:
            val = round(val, 2)
        if code:
            variants.append(VariantMetricEntry(variant_code=str(code), value=val))

    return CompareVariantsResponse(
        metric=metric_key,
        system_name=canonical_system,
        variants=variants,
    )


SKILLS = {
    "count_parts": {
        "description": "Count the total number of parts (sum of quantities) in a vehicle variant's BOM.",
        "parameters": {
            "variant_code": {
                "type": "string",
                "enum": VARIANT_CODES,
                "description": "The car variant to query.",
                "required": True,
            },
            "system_name": {
                "type": "string",
                "enum": SYSTEM_NAMES,
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
                "enum": VARIANT_CODES,
                "description": "The car variant to query.",
                "required": True,
            },
            "system_name": {
                "type": "string",
                "enum": SYSTEM_NAMES,
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
                "enum": VARIANT_CODES,
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
    },
    "costliest_system": {
        "description": (
            "Fetch the system(s) with highest total material cost (sum of quantity × unit cost) "
            "for one variant, or across the entire fleet if variant is omitted."
        ),
        "parameters": {
            "variant_code": {
                "type": "string",
                "enum": VARIANT_CODES,
                "description": "Optional: the variant to query. If omitted, aggregates across all variants.",
                "required": False,
            },
            "top_n": {
                "type": "integer",
                "description": "Optional: number of top costliest systems to return (default is 1).",
                "required": False,
            },
        },
        "returns": "CostliestSystemResponse — list of top N systems and total cost in GBP",
        "function": costliest_system,
    },
    "most_complex_system": {
        "description": (
            "Return the system(s) with the highest part count (sum of quantities over all PartLinks) "
            "for one variant, or across the fleet if variant is omitted."
        ),
        "parameters": {
            "variant_code": {
                "type": "string",
                "enum": VARIANT_CODES,
                "description": "Optional: the variant to query. If omitted, aggregates across all variants.",
                "required": False,
            },
            "top_n": {
                "type": "integer",
                "description": "Optional: number of top systems by complexity to return (default is 1).",
                "required": False,
            },
        },
        "returns": "MostComplexSystemResponse — list of top N systems and total part quantities",
        "function": most_complex_system,
    },
    "compare_variants": {
        "description": (
            "Compare all five Apex variants (SEDAN, SUV, COUPE, HATCH, ESTATE) on one metric: "
            "total_parts (sum of BOM quantities), total_weight (kg), or total_cost (GBP material cost)."
        ),
        "parameters": {
            "metric": {
                "type": "string",
                "enum": COMPARE_METRICS,
                "description": "Metric to compare across variants.",
                "required": True,
            },
            "system_name": {
                "type": "string",
                "enum": SYSTEM_NAMES,
                "description": "Optional: limit the comparison to one system (e.g. Engine).",
                "required": False,
            },
        },
        "returns": "CompareVariantsResponse — per-variant aggregated values, highest first",
        "function": compare_variants,
    },
}


if __name__ == "__main__":
    # print(count_parts('SEDAN', 'Engine'))


    for variant in VARIANT_CODES:
        for system in SYSTEM_NAMES:
            print(count_parts(variant, system))
        print(count_parts(variant))
        
    
    # for system in VARIANT_CODES: 
    #     print(count_unique_parts(system))
        
        



    print(count_unique_parts('SEDAN', 'Engine'))
    print(heaviest_system('SEDAN', 5))
    print(heaviest_system(top_n = 5))

    print(costliest_system('SEDAN', 5))
    print(costliest_system(top_n=5))


    print(most_complex_system('SEDAN' , 5))
    print(most_complex_system(top_n=5))
    print(compare_variants("total_cost"))
    print(compare_variants("total_weight", "Engine"))
