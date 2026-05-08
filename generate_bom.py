from dataclasses import dataclass
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Tuple
from pydantic import BaseModel, Field
from random import choice, randint, uniform, random
import uuid



def slug(text: str) -> str:
    return text.lower().replace("&", "and").replace(" ", "_").replace("-", "_").replace("/", "_")

def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


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
        for link in self.part_links:
            lines.append(f"bom:{self.id} bom:hasPart bom:{link.part.id} .")
            lines.append(f"bom:{self.id} bom:hasPartLink bom:{link.id} .")
        lines.append("")
        for link in self.part_links:
            lines.extend(link.to_ttl())
        for part in self.parts: 
            lines.extend(part.to_ttl())
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
        for assembly in self.assemblies:
            lines.append(f"bom:{self.id} bom:hasAssembly bom:{assembly.id} .")
        lines.append("")
        for assembly in self.assemblies:
            lines.extend(assembly.to_ttl())
        return lines


class Variant(BaseModel):
    code: str
    full_name: str
    description: str
    systems: List[System] = Field(default_factory=list)

    def to_ttl(self) -> List[str]:
        slug_val = self.code.lower()
        vehicle_id = f"vehicle_{slug_val}"
        lines = [
            f"bom:{vehicle_id} a bom:Vehicle ;",
            f"  rdfs:label \"{esc(self.full_name)}\" ;",
            f"  bom:variantCode \"{esc(self.code)}\" ;",
            f"  rdfs:comment \"{esc(self.description)}\" .",
            "",
        ]
        for system in self.systems:
            lines.append(f"bom:{vehicle_id} bom:hasSystem bom:{system.id} .")
        lines.append("")
        for system in self.systems:
            lines.extend(system.to_ttl())
        return lines


VARIANTS = [
    Variant(code="SEDAN", full_name="Apex Meridian Sedan", description="4-door, conventional boot"),
    Variant(code="SUV", full_name="Apex Meridian SUV", description="Taller ride height, AWD, larger chassis"),
    Variant(code="COUPE", full_name="Apex Meridian Coupe", description="2-door, sport-tuned suspension"),
    Variant(code="HATCH", full_name="Apex Meridian Hatchback", description="5-door, compact body"),
    Variant(code="ESTATE", full_name="Apex Meridian Estate", description="Extended roof, higher load capacity"),
]


BASE_ASSEMBLIES: Dict[str, Tuple[List[str], int]] = {
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


def generate_shared_parts():
    shared_parts : List[Part] = []
    names = ["M8 Bolt", "Wiring Clip", "Hex Nut", "Rubber Seal", "O-Ring", "12V Relay"]
    AMOUNT_OF_SHARED_PARTS = 25

    for i in range(AMOUNT_OF_SHARED_PARTS):
        part_name = f"{choice(names)} {randint(100,999)}"
        part_id = f"part_shared_{i:04d}"
        part_number = f"CM-SHARED-{i:04d}"
        unit_cost_gbp = round(uniform(0.05, 5.0), 2)
        unit_weight_kg = round(uniform(0.001, 0.5), 3)

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

def create_unique_part(variant_code: str, system_name: str) -> Part:
    """
    Creates a synthetically realistic part based on the variant and system context.
    """

    PART_ADJECTIVES = ["Heavy-Duty", "Reinforced", "High-Precision", "Lightweight", "Thermal-Resistant", "Forged", "Cast"]
    PART_COMPONENTS = {
        "engine": ["Gasket", "Valve", "Piston Ring", "Sensor", "Housing", "Plug"],
        "transmission": ["Gear", "Syncro Mesh", "Bearing", "Clutch Plate", "Seal"],
        "chassis_and_frame": ["Bracket", "Mount", "Bush", "Rail Section", "Fastener"],
        "suspension_and_steering": ["Ball Joint", "Linkage", "Damper Valve", "Tie Rod"],
        "brakes": ["Piston", "Shim", "Bleed Nipple", "Retainer Clip"],
        "body_and_exterior": ["Latch", "Hinge", "Seal Strip", "Trim Clip", "Bracket"],
        "electrical_and_electronics": ["Terminal", "Fuse", "Module Case", "Connector", "Diode"]
    }

    v_low = variant_code.lower()
    sys_slug = slug(system_name)
    
    # Generate a plausible name
    # Pick a component list based on the system, default to generic if not found
    comp_list = PART_COMPONENTS.get(sys_slug, ["Component", "Module", "Part"])
    name = f"{choice(PART_ADJECTIVES)} {choice(comp_list)}"
    
    # Generate a unique ID and Part Number
    unique_id = uuid.uuid4().hex[:6]
    p_id = f"part_{v_low}_{unique_id}"
    p_number = f"APX-{v_low[:3].upper()}-{sys_slug[:3].upper()}-{unique_id.upper()}"
    
    # Adjust cost/weight based on system (Engineering Reality)
    if sys_slug == "engine":
        cost = uniform(50.0, 2500.0)
        weight = uniform(0.5, 45.0)
    elif sys_slug == "electrical_and_electronics":
        cost = uniform(5.0, 800.0)
        weight = uniform(0.001, 2.0)
    else:
        cost = uniform(0.05, 300.0)
        weight = uniform(0.01, 10.0)

    # Specific Variant adjustment: SUV parts are 20% heavier
    if v_low == "suv":
        weight *= 1.2

    return Part(
        id=p_id,
        name=name,
        part_number=p_number,
        unit_cost_gbp=round(cost, 2),
        unit_weight_kg=round(weight, 3)
    )


def give_assembly_parts(assembly: Assembly, variant_code: str, target_count: int) -> Assembly:
    PROBABILITY_OF_SHARED = 0.2
    MAX_QUANTITY = 10

    for _ in range(target_count):

        if random() < PROBABILITY_OF_SHARED:
            selected_part = choice(shared_parts)
        else:
            selected_part = create_unique_part(variant_code, assembly.name)
        
        link = PartLink(
            id=f"link_{uuid.uuid4().hex[:8]}",
            part=selected_part,
            quantity=randint(1, MAX_QUANTITY) if "Block" in assembly.name else randint(1, 20)
        )
        assembly.parts.append(selected_part)
        assembly.part_links.append(link)

    return assembly

def random_numbers_sum_to_y(x, y) -> List[int]:
    nums = [random() for _ in range(x)]
    s = sum(nums)
    return [round(y * n / s) for n in nums]

def build_base_systems(variant_code: str) -> List[System]:
    systems: List[System] = []
    v = variant_code.lower()
    for system_name, (assembly_names, amount_of_parts) in BASE_ASSEMBLIES.items():
        sys_slug = slug(system_name)

        print(system_name)
        print(assembly_names)
        print(amount_of_parts)


        amount_of_parts_per_assembly = random_numbers_sum_to_y(len(assembly_names), amount_of_parts)
        print(amount_of_parts_per_assembly)
        print(sum([round(amount) for amount in amount_of_parts_per_assembly]))
        system = System(
            id=f"system_{v}_{sys_slug}",
            name=system_name,
            assemblies=[
                give_assembly_parts(Assembly(
                    id=f"assembly_{v}_{sys_slug}_{i+1:02d}_{slug(assembly_name)}",
                    name=assembly_name,
                ), variant_code, amount_of_parts_per_assembly[i])
                for i, assembly_name in enumerate(assembly_names)
            ],
        )
        systems.append(system)
    return systems

def generate_variants_ttl(
    variants: List[Variant],
    output_path: str = "apex_bom.ttl",
) -> None:

    PREFIX_LINES = [
        "@prefix bom: <http://ibom.ai/ontology/bom#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]
    ENCODING = "utf-8"
    lines = list(PREFIX_LINES)

    for variant in variants:
        lines.extend(variant.to_ttl())
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding=ENCODING)
    print(f"Wrote {out}")

def attach_base_systems_to_variants(variants: List[Variant]) -> List[Variant]:
    for variant in variants:
        variant.systems = build_base_systems(variant.code)
    return variants

shared_parts = generate_shared_parts()

if __name__ == "__main__":
    variants = attach_base_systems_to_variants(VARIANTS)
    generate_variants_ttl(variants)