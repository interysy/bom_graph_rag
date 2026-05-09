from loguru import logger
import random
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Tuple, Set
import uuid


# Constants

RANDOM_SEED = "siemens_bom"
OUTPUT_PATH = "apex_bom.ttl"
AMOUNT_OF_SHARED_PARTS = 80
SHARED_PART_PROBABILITY = 0.2


VARIANTS = [
        ("SEDAN", "Apex Meridian Sedan", "4-door, conventional boot"),
        ("SUV", "Apex Meridian SUV", "Taller ride height, AWD, larger chassis"),
        ("COUPE", "Apex Meridian Coupé", "2-door, sport-tuned suspension"),
        ("HATCH", "Apex Meridian Hatchback", "5-door, compact body"),
        ("ESTATE", "Apex Meridian Estate", "Extended roof, higher load capacity")
]

SYSTEMS = [
        "Engine", "Transmission", "Chassis & Frame", "Suspension & Steering", "Brakes", "Body & Exterior", "Electrical & Electronics"
]

ASSEMBLIES : Dict[str, Tuple[List[str], int]] = {
    "Engine": ([
        "Cylinder Block",
        "Cylinder Head",
        "Fuel Delivery",
        "Lubrication",
        "Cooling",
    ], 80),
    "Transmission": ([
        "Gearbox",
        "Driveshaft",
        "Differential",
        "Clutch",
    ], 40),
    "Chassis & Frame": ([
        "Front Subframe",
        "Rear Subframe",
        "Cross Members",
        "Underbody Rails",
    ], 50),
    "Suspension & Steering": ([
        "Front Strut",
        "Rear Multi Link",
        "Steering Column",
        "Power Steering",
    ], 60),
    "Brakes": ([ 
        "Front Caliper", 
        "Rear Caliper", 
        "ABS Module",
        "Brake Lines"
    ], 30),
    "Body & Exterior": ([
        "Door Panels",
        "Bonnet",
        "Boot/Tailgate", 
        "Bumpers", 
        "Glass"
    ], 70),
    "Electrical & Electronics" : ([
        "Wiring Harness", 
        "Battery", 
        "ECU", 
        "Lighting",
        "Sensors"
    ],80)
}



# Models

class Part(BaseModel):
    id: str
    name: str
    part_number: str
    unit_cost_gbp: float = Field(ge=0.05, le=2500.0)
    unit_weight_kg: float = Field(ge=0.001, le=45.0)

    def to_ttl(self) -> List[str]:
        return [
            f"bom:{self.id} a bom:Part ;",
            f"  bom:partName \"{esc(self.name)}\" ;",
            f"  bom:partNumber \"{esc(self.part_number)}\" ;",
            f"  bom:unitCostGBP \"{self.unit_cost_gbp:.2f}\"^^xsd:decimal ;",
            f"  bom:unitWeightKg \"{self.unit_weight_kg:.3f}\"^^xsd:decimal .",
            "",
        ]


class PartLink(BaseModel):
    id: str
    part: Part
    quantity: int = Field(ge=1, le=50)

    def to_ttl(self) -> List[str]:
        return [
            f"bom:{self.id} a bom:PartLink ;",
            f"  bom:part bom:{self.part.id} ;",
            f"  bom:quantity {self.quantity} .",
            "",
        ]


class Assembly(BaseModel):
    id: str
    name: str
    part_links: List[PartLink] = Field(default_factory=list)
    parts : List[Part] = Field(default_factory=list)

    def to_ttl(self) -> List[str]:
        lines = [
            f"bom:{self.id} a bom:Assembly ;",
            f"  bom:assemblyName \"{esc(self.name)}\" .",
            "",
        ]
        return lines


class System(BaseModel):
    id: str
    name: str
    assemblies: List[Assembly] = Field(default_factory=list)

    def to_ttl(self) -> List[str]:
        lines = [
            f"bom:{self.id} a bom:System ;",
            f"  bom:systemName \"{esc(self.name)}\" .",
            "",
        ]

        return lines


class Variant(BaseModel):
    code: str
    full_name: str
    description: str
    systems: List[System] = Field(default_factory=list)

    @property
    def uri(self) -> str:
        """Returns the local name for the RDF URI."""
        return f"vehicle_{self.code.lower()}"

    def to_ttl(self) -> List[str]:
       
        lines = [
            f"bom:{self.uri} a bom:Vehicle ;",
            f"  rdfs:label \"{esc(self.full_name)}\" ;",
            f"  bom:variantCode \"{esc(self.code)}\" ;",
            f"  rdfs:comment \"{esc(self.description)}\" .",
            "",
        ]

        return lines


# Generator 

class BOMGenerator:
    ENCODING = "utf-8"

    def __init__(self):
        
        self.registered_parts: Set[str] = set()
        self.registered_links: Set[str] = set()
        self.registered_assemblies: Set[str] = set()
        self.registered_systems: Set[str] = set()
        
        self.lines: List[str] = [
            "@prefix bom: <http://ibom.ai/ontology/bom#> .",
            "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
            ""
        ]

    def add_part(self, part: Part) -> None:
        if part.id in self.registered_parts:
            return
        
        self.lines.extend(part.to_ttl())
        self.registered_parts.add(part.id)

    def add_part_link(self, link: PartLink) -> None:
        
        self.add_part(link.part)
        
        if link.id not in self.registered_links:
            self.lines.extend(link.to_ttl())
            self.registered_links.add(link.id)

    def add_assembly(self, assembly: 'Assembly'):
        if assembly.id in self.registered_assemblies:
            return
        
        self.lines.extend(assembly.to_ttl())
        
        for link in assembly.part_links:
            self.add_part_link(link) 

            self.lines.append(f"bom:{assembly.id} bom:hasPartLink bom:{link.id} .")
            self.lines.append(f"bom:{assembly.id} bom:hasPart bom:{link.part.id} .")
        
        self.lines.append("")
        self.registered_assemblies.add(assembly.id)

    def add_system(self, system: System) -> None:
        if system.id in self.registered_systems:
            return
        
        self.lines.extend(system.to_ttl())
        
        for assembly in system.assemblies:
            self.add_assembly(assembly) 
            self.lines.append(f"bom:{system.id} bom:hasAssembly bom:{assembly.id} .")
        
        self.lines.append("") 
        self.registered_systems.add(system.id)

    def add_variant(self, variant: Variant):
        vehicle_uri = variant.uri
        
        self.lines.extend(variant.to_ttl())
        

        for system in variant.systems:
            self.add_system(system)
            self.lines.append(f"bom:{vehicle_uri} bom:hasSystem bom:{system.id} .")
        
        self.lines.append("")

    def save(self, file_path: str = OUTPUT_PATH):
        out = Path(file_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(self.lines), encoding=self.ENCODING)
        logger.info(f"Wrote {out}")

    def output_stats(self):
        SEPERATOR_LENGTH = 30

        logger.success("Generation Complete!")
        print("-" * SEPERATOR_LENGTH)
        print(f"File Saved: {OUTPUT_PATH}")
        print(f"Total Unique Parts (Deduplicated): {len(self.registered_parts)}")
        print(f"Total Assemblies:                  {len(self.registered_assemblies)}")
        print(f"Total PartLinks (Graph Edges):     {len(self.registered_links)}")
        print("-" * SEPERATOR_LENGTH)



# Shared Parts Generator 

def generate_shared_parts(amount : int = AMOUNT_OF_SHARED_PARTS):
    shared_parts : List[Part] = []
    names = ["M8 Bolt", "Wiring Clip", "Hex Nut", "Rubber Seal", "O-Ring", "12V Relay"]

    for i in range(amount):
        part_name = f"{random.choice(names)} {random.randint(100,999)}"
        part_id = f"part_shared_{i:04d}"
        part_number = f"CM-SHARED-{i:04d}"
        unit_cost_gbp = round(random.uniform(0.05, 5.0), 2)
        unit_weight_kg = round(random.uniform(0.001, 0.5), 3)

        shared_parts.append(
            Part(
                id=part_id,
                name=part_name,
                part_number=part_number,
                unit_cost_gbp=unit_cost_gbp,
                unit_weight_kg=unit_weight_kg
            )
        )

    return shared_parts


# UTILITIES
def esc(s: str) -> str:
    """Escape quotes for Turtle string literals."""
    return s.replace('"', '\\"')

def uid(prefix: str) -> str:
    """Generate a short unique ID."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def clean_id(text: str) -> str:
    """Removes characters that are illegal in RDF URIs."""
    return text.lower().replace(" ", "_").replace("&", "and").replace("/", "_")


def random_numbers_sum_to_y(x, y) -> List[int]:
    nums = [random.random() for _ in range(x)]
    s = sum(nums)
    return [round(y * n / s) for n in nums]


def main():
    logger.info("Starting Apex BOM Generation...")

    random.seed(RANDOM_SEED)
    
    generator = BOMGenerator()

    logger.info("Generating shared parts pool...")
    shared_parts_pool = generate_shared_parts()
    
    for code, full_name, description in VARIANTS:
        logger.info(f"Building Variant: {code}")
        variant = Variant(code=code, full_name=full_name, description=description)
        
        for system_name in SYSTEMS:
            assemblies_for_system, total_system_parts = ASSEMBLIES[system_name]
            
            clean_sys_name = clean_id(system_name)
            system_id = uid(f"sys_{code.lower()}_{clean_sys_name}")
            system = System(id=system_id, name=system_name)

            logger.debug(f"Building {system_name} for {code}")

            parts_per_assembly = random_numbers_sum_to_y(len(assemblies_for_system), total_system_parts)

            for assembly_index, assembly_name in enumerate(assemblies_for_system): 
                
                clean_assy_name = clean_id(assembly_name)
                assembly = Assembly(
                    id=uid(f"assy_{system_id}_{clean_assy_name}"),
                    name=assembly_name
                )

                amount_of_parts_for_assembly = parts_per_assembly[assembly_index]

                for _ in range(amount_of_parts_for_assembly):
                    if random.random() < SHARED_PART_PROBABILITY:
                        selected_part = random.choice(shared_parts_pool)
                    else:
                        part_id = uid(f"part_{code.lower()}")
                        selected_part = Part(
                            id=part_id,
                            name=f"{assembly_name} Component {part_id}",
                            part_number=f"APX-{code}-{random.randint(10000, 99999)}",
                            unit_cost_gbp=round(random.uniform(10.0, 1500.0), 2),
                            unit_weight_kg=round(random.uniform(0.1, 25.0), 3)
                        )
                    
                    link = PartLink(
                        id=uid(f"link_{assembly.id}"),
                        part=selected_part,
                        quantity=random.randint(1, 5)
                    )
                    assembly.part_links.append(link)
                
                system.assemblies.append(assembly)
            variant.systems.append(system)
            
        generator.add_variant(variant)

    generator.save(OUTPUT_PATH)
    generator.output_stats()

if __name__ == "__main__":
    main()
