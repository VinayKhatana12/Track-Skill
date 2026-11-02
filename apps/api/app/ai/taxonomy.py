"""TrackSkill AI skills taxonomy and job-role definitions.

A compact, English-only taxonomy: 60 skills across the 6 seeded sectors,
plus job roles expressed as weighted skill sets. Keeping the taxonomy as
code (not DB rows) keeps embeddings cacheable and the matcher explainable —
every confidence can be traced back to a canonical skill name.

Sector names intentionally match the seed's sectors so course skills,
market demand and taxonomy align.
"""

SECTORS = (
    "Information Technology",
    "Healthcare",
    "Construction",
    "Retail",
    "Textiles",
    "Green Energy",
)

# (canonical skill name, sector, aliases) — 10 per sector = 60 skills.
SKILLS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # Information Technology
    ("JavaScript", "Information Technology", ("js", "es6")),
    ("HTML & CSS", "Information Technology", ("html", "css", "web design")),
    ("React", "Information Technology", ("reactjs", "react js")),
    ("SQL", "Information Technology", ("database queries", "sql queries")),
    ("Python Programming", "Information Technology", ("python", "python coding")),
    ("Cloud Support", "Information Technology", ("cloud", "cloud assistance")),
    ("Linux Administration", "Information Technology", ("linux", "linux admin")),
    ("Networking Basics", "Information Technology", ("networking", "computer networks")),
    ("Git Version Control", "Information Technology", ("git", "version control")),
    ("Data Entry", "Information Technology", ("data entry operator", "entering data")),
    # Healthcare
    (
        "Patient Care",
        "Healthcare",
        (
            "caring for patients",
            "patient care assistant",
            "care of patients",
            "take care of patients",
        ),
    ),
    ("Vital Monitoring", "Healthcare", ("vitals", "monitoring vitals")),
    ("First Aid", "Healthcare", ("first-aid", "emergency aid")),
    ("Phlebotomy", "Healthcare", ("blood collection", "phlebotomist")),
    ("Lab Safety", "Healthcare", ("laboratory safety", "lab protocols")),
    ("Medical Billing", "Healthcare", ("billing", "claims processing")),
    ("Medical Coding", "Healthcare", ("icd coding", "medical coder")),
    ("Records Management", "Healthcare", ("medical records", "file management")),
    ("Nursing Assistance", "Healthcare", ("nursing assistant", "nurse aide")),
    ("Specimen Handling", "Healthcare", ("specimen collection", "sample handling")),
    # Construction
    ("Masonry", "Construction", ("brickwork", "mason")),
    ("Tiling", "Construction", ("tile work", "tiler")),
    ("Bar Bending", "Construction", ("steel fixing", "bar bender")),
    ("Reinforcement Work", "Construction", ("reinforcement", "reo work")),
    ("Blueprint Reading", "Construction", ("blueprints", "drawing reading")),
    ("Site Safety", "Construction", ("site safety protocols", "construction safety")),
    ("Surveying", "Construction", ("land survey", "surveyor assistant")),
    ("Total Station Operation", "Construction", ("total station", "survey instrument")),
    ("Leveling", "Construction", ("levelling", "level survey")),
    ("Concrete Work", "Construction", ("concreting", "concrete pouring")),
    # Retail
    ("Sales Operations", "Retail", ("sales", "retail sales")),
    ("POS Operations", "Retail", ("point of sale", "cash register", "pos")),
    ("Merchandising", "Retail", ("shelf display", "merchandise")),
    ("Customer Service", "Retail", ("customer support", "customer care")),
    ("Complaint Handling", "Retail", ("complaints", "grievance handling")),
    ("CRM Software", "Retail", ("crm", "crm tool")),
    ("Inventory Management", "Retail", ("inventory", "stock management")),
    ("Barcode Systems", "Retail", ("barcodes", "barcode scanner")),
    ("Warehouse Packing", "Retail", ("packing", "warehouse work")),
    ("Cash Handling", "Retail", ("cashier", "handling cash")),
    # Textiles
    ("Stitching", "Textiles", ("sewing", "stitching operator")),
    ("Machine Operation", "Textiles", ("operating machines", "machine operator")),
    ("Fabric Handling", "Textiles", ("fabric", "fabric care")),
    ("Quality Inspection", "Textiles", ("quality check", "quality control")),
    ("Defect Analysis", "Textiles", ("defects", "defect checking")),
    ("Pattern Making", "Textiles", ("patterns", "pattern cutting")),
    ("Textile Printing", "Textiles", ("printing", "fabric printing")),
    ("Colour Matching", "Textiles", ("color matching", "colour shade")),
    ("Garment Finishing", "Textiles", ("finishing", "garment pressing")),
    ("Fabric Sourcing", "Textiles", ("sourcing fabric", "fabric procurement")),
    # Green Energy
    ("Solar Installation", "Green Energy", ("solar panels", "solar fitting")),
    ("Electrical Wiring", "Green Energy", ("wiring", "electrician work")),
    ("Roof Safety", "Green Energy", ("roof work", "working at height")),
    ("Battery Systems", "Green Energy", ("batteries", "battery storage")),
    ("Energy Auditing", "Green Energy", ("energy audit", "energy assessment")),
    ("Inverter Basics", "Green Energy", ("inverter", "inverters")),
    ("EV Charging Systems", "Green Energy", ("ev charging", "electric vehicle charging")),
    ("Turbine Maintenance", "Green Energy", ("wind turbine", "turbine servicing")),
    ("Meter Reading", "Green Energy", ("meter", "reading meters")),
    ("Load Analysis", "Green Energy", ("load calculation", "power load")),
)

SKILL_BY_NAME = {name: (sector, aliases) for name, sector, aliases in SKILLS}
SKILL_SECTOR = {name: sector for name, sector, _ in SKILLS}

# Job roles as weighted skill sets — the matcher scores a trainee's skill
# profile against these weights and explains which skills matched.
JOB_ROLES: tuple[dict, ...] = (
    {
        "title": "Frontend Developer",
        "sector": "Information Technology",
        "skills": {"React": 1.0, "JavaScript": 1.0, "HTML & CSS": 0.9, "Git Version Control": 0.7},
    },
    {
        "title": "Data Entry Operator",
        "sector": "Information Technology",
        "skills": {"Data Entry": 1.0, "CRM Software": 0.5, "SQL": 0.4},
    },
    {
        "title": "Cloud Support Associate",
        "sector": "Information Technology",
        "skills": {"Cloud Support": 1.0, "Linux Administration": 0.9, "Networking Basics": 0.8},
    },
    {
        "title": "Nursing Assistant",
        "sector": "Healthcare",
        "skills": {
            "Nursing Assistance": 1.0,
            "Patient Care": 1.0,
            "Vital Monitoring": 0.9,
            "First Aid": 0.7,
        },
    },
    {
        "title": "Phlebotomy Technician",
        "sector": "Healthcare",
        "skills": {"Phlebotomy": 1.0, "Lab Safety": 0.9, "Specimen Handling": 0.9},
    },
    {
        "title": "Medical Billing Assistant",
        "sector": "Healthcare",
        "skills": {"Medical Billing": 1.0, "Medical Coding": 0.9, "Records Management": 0.7},
    },
    {
        "title": "Mason",
        "sector": "Construction",
        "skills": {"Masonry": 1.0, "Tiling": 0.8, "Concrete Work": 0.7, "Site Safety": 0.6},
    },
    {
        "title": "Surveying Assistant",
        "sector": "Construction",
        "skills": {
            "Surveying": 1.0,
            "Total Station Operation": 0.9,
            "Leveling": 0.8,
            "Blueprint Reading": 0.6,
        },
    },
    {
        "title": "Retail Sales Associate",
        "sector": "Retail",
        "skills": {"Sales Operations": 1.0, "Customer Service": 0.9, "POS Operations": 0.8},
    },
    {
        "title": "Warehouse Assistant",
        "sector": "Retail",
        "skills": {"Inventory Management": 1.0, "Barcode Systems": 0.9, "Warehouse Packing": 0.9},
    },
    {
        "title": "Garment Stitching Operator",
        "sector": "Textiles",
        "skills": {"Stitching": 1.0, "Machine Operation": 0.9, "Fabric Handling": 0.8},
    },
    {
        "title": "Quality Inspector (Textiles)",
        "sector": "Textiles",
        "skills": {"Quality Inspection": 1.0, "Defect Analysis": 0.9, "Colour Matching": 0.6},
    },
    {
        "title": "Solar Installation Technician",
        "sector": "Green Energy",
        "skills": {"Solar Installation": 1.0, "Electrical Wiring": 0.9, "Roof Safety": 0.8},
    },
    {
        "title": "EV Service Assistant",
        "sector": "Green Energy",
        "skills": {"Battery Systems": 1.0, "EV Charging Systems": 0.9, "Electrical Wiring": 0.7},
    },
)

# Confidence at or above this value lands a taxonomy skill in the profile.
PROFILE_CONFIDENCE_THRESHOLD = 0.45
# An exact (alias) mention is near-certain evidence of the skill.
EXACT_MATCH_CONFIDENCE = 0.95
