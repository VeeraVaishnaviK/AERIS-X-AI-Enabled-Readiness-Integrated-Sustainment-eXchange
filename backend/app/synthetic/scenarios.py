"""
AERIS-X Synthetic Data Scenarios
Tagged scenario definitions for deterministic telemetry generation.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DegradationScenario:
    """Defines how a component degrades over time for synthetic data generation."""
    tag: str
    description: str
    # Day range within the 90-day window when the degradation becomes active
    onset_day: int = 30
    peak_day: int = 80
    # Sensor channels affected and their degradation multipliers
    affected_sensors: Dict[str, float] = field(default_factory=dict)
    # Whether this scenario ends in a failure event
    causes_failure: bool = False
    failure_day: Optional[int] = None
    # Whether a replacement occurs after failure
    replacement_after_failure: bool = False
    replacement_day: Optional[int] = None


SCENARIOS: List[DegradationScenario] = [
    DegradationScenario(
        tag="NORMAL",
        description="Healthy component, nominal sensor readings with small random noise.",
        onset_day=999,  # Never degrades within 90-day window
        peak_day=999,
        affected_sensors={},
        causes_failure=False,
    ),
    DegradationScenario(
        tag="GRADUAL_DEGRADATION",
        description="Slow exponential wear on vibration and EGT; classic bearing fatigue.",
        onset_day=20,
        peak_day=75,
        affected_sensors={"vibration": 2.5, "egt": 1.4, "oil_temperature": 1.2},
        causes_failure=False,
    ),
    DegradationScenario(
        tag="SUDDEN_ANOMALY",
        description="Abrupt spike in hydraulic pressure and oil pressure at day 55.",
        onset_day=55,
        peak_day=60,
        affected_sensors={"hydraulic_pressure": 3.0, "oil_pressure": 2.0, "vibration": 1.8},
        causes_failure=False,
    ),
    DegradationScenario(
        tag="SENSOR_FAILURE",
        description="Battery voltage sensor drifts then flatlines (stuck sensor fault).",
        onset_day=40,
        peak_day=50,
        affected_sensors={"battery_voltage": -0.5, "n1_rpm": 0.0},  # voltage drops, n1 stuck
        causes_failure=False,
    ),
    DegradationScenario(
        tag="COMPONENT_REPLACEMENT",
        description="Engine degradation leads to scheduled replacement at day 65, then recovery.",
        onset_day=15,
        peak_day=60,
        affected_sensors={"vibration": 3.0, "egt": 2.0, "fuel_flow": 1.5, "n2_rpm": 1.3},
        causes_failure=True,
        failure_day=60,
        replacement_after_failure=True,
        replacement_day=65,
    ),
    DegradationScenario(
        tag="REPEATED_ISSUE",
        description="Recurring vibration spikes every 20 days (periodic misalignment).",
        onset_day=10,
        peak_day=90,
        affected_sensors={"vibration": 2.0, "egt": 1.2},
        causes_failure=False,
    ),
    DegradationScenario(
        tag="SPARE_SHORTAGE",
        description="Gradual hydraulic system degradation; needed spare part is backordered.",
        onset_day=25,
        peak_day=70,
        affected_sensors={"hydraulic_pressure": 2.5, "oil_pressure": 1.8, "oil_temperature": 1.4},
        causes_failure=False,
    ),
    DegradationScenario(
        tag="TECHNICIAN_SHORTAGE",
        description="Avionics degradation needing specialist who is unavailable.",
        onset_day=30,
        peak_day=75,
        affected_sensors={"battery_voltage": 1.5, "n1_rpm": 1.3, "n2_rpm": 1.2},
        causes_failure=False,
    ),
]


# Aircraft type definitions
AIRCRAFT_TYPES = {
    "Su-30MKI": {
        "squadron_prefix": "No.",
        "squadrons": ["No. 2 Winged Arrows", "No. 8 Pursoots", "No. 20 Lightnings", "No. 24 Hawks"],
        "bases": ["Bareilly AFS", "Pune AFS", "Tezpur AFS", "Chabua AFS"],
        "components": [
            ("ENG-L", "AL-31FP Turbofan (Left)", "ENGINES"),
            ("ENG-R", "AL-31FP Turbofan (Right)", "ENGINES"),
            ("HYD-PRI", "Primary Hydraulic System", "HYDRAULICS"),
            ("HYD-SEC", "Secondary Hydraulic System", "HYDRAULICS"),
            ("AVI-MAIN", "RLSU-30MKI Radar & Avionics Suite", "AVIONICS"),
            ("FUEL-SYS", "Integrated Fuel Management System", "FUEL"),
            ("LG-NOSE", "Nose Landing Gear Assembly", "LANDING_GEAR"),
            ("AFR-WING", "Wing Structure & Control Surfaces", "AIRFRAME"),
        ],
    },
    "Rafale": {
        "squadron_prefix": "No.",
        "squadrons": ["No. 17 Golden Arrows", "No. 101 Falcons of Chamb"],
        "bases": ["Ambala AFS", "Hashimara AFS"],
        "components": [
            ("ENG-L", "M88-2 Turbofan (Left)", "ENGINES"),
            ("ENG-R", "M88-2 Turbofan (Right)", "ENGINES"),
            ("HYD-MAIN", "Rafale Hydraulic Power Unit", "HYDRAULICS"),
            ("AVI-RBE2", "RBE2-AA AESA Radar Suite", "AVIONICS"),
            ("AVI-SPECTRA", "SPECTRA EW & Self-Protection Suite", "AVIONICS"),
            ("FUEL-CFT", "Conformal Fuel Tank System", "FUEL"),
            ("LG-MAIN", "Main Landing Gear Assembly", "LANDING_GEAR"),
            ("AFR-DELTA", "Delta Wing & Canard Structures", "AIRFRAME"),
        ],
    },
    "Tejas Mk1A": {
        "squadron_prefix": "No.",
        "squadrons": ["No. 18 Flying Bullets", "No. 45 Flying Daggers"],
        "bases": ["Sulur AFS", "Naliya AFS"],
        "components": [
            ("ENG-SINGLE", "GE F404-IN20 Turbofan", "ENGINES"),
            ("HYD-FBW", "Fly-By-Wire Hydraulic Actuator System", "HYDRAULICS"),
            ("AVI-EL2052", "ELTA EL/M-2052 AESA Radar", "AVIONICS"),
            ("FUEL-INT", "Internal Fuel Management System", "FUEL"),
            ("LG-TRI", "Tricycle Landing Gear Assembly", "LANDING_GEAR"),
            ("AFR-COMP", "Carbon Composite Airframe", "AIRFRAME"),
        ],
    },
}

# Sensor baseline ranges (nominal min, nominal max)
SENSOR_BASELINES = {
    "vibration":          (0.8, 2.5),    # mm/s RMS
    "egt":                (580.0, 720.0), # °C
    "oil_pressure":       (38.0, 52.0),   # psi
    "oil_temperature":    (80.0, 110.0),  # °C
    "fuel_flow":          (900.0, 1400.0),# kg/h
    "hydraulic_pressure": (2700.0, 3200.0), # psi
    "battery_voltage":    (26.5, 29.0),   # V
    "n1_rpm":             (94.0, 100.0),  # %
    "n2_rpm":             (90.0, 98.0),   # %
}

# Technician pool
TECHNICIAN_POOL = [
    {"name": "JWO K. Nair",           "rank": "Master Specialist", "specialty": "Propulsion",  "certs": ["AL-31FP", "M88-2", "GE F404"], "shift": "DAY"},
    {"name": "Sgt. R. Kumar",         "rank": "Lead Tech",         "specialty": "Propulsion",  "certs": ["AL-31FP", "GE F404"],           "shift": "DAY"},
    {"name": "Cpl. A. Deshmukh",      "rank": "Senior Tech",       "specialty": "Avionics",    "certs": ["RLSU-30MKI", "RBE2-AA", "EL/M-2052"], "shift": "DAY"},
    {"name": "Sgt. P. Menon",         "rank": "Lead Tech",         "specialty": "Avionics",    "certs": ["SPECTRA EW", "RBE2-AA"],        "shift": "NIGHT"},
    {"name": "JWO S. Choudhury",      "rank": "Master Specialist", "specialty": "Hydraulics",  "certs": ["FBW Actuators", "Heavy Hydraulics"], "shift": "DAY"},
    {"name": "Cpl. V. Sharma",        "rank": "Senior Tech",       "specialty": "Hydraulics",  "certs": ["FBW Actuators"],                "shift": "NIGHT"},
    {"name": "Sgt. D. Singh",         "rank": "Lead Tech",         "specialty": "Airframe",    "certs": ["Composite Repair", "NDT Inspector"], "shift": "DAY"},
    {"name": "AC T. Prasad",          "rank": "Junior Tech",       "specialty": "Airframe",    "certs": ["Structural Repair"],            "shift": "DAY"},
    {"name": "Cpl. M. Reddy",         "rank": "Senior Tech",       "specialty": "Fuel Systems","certs": ["CFT Specialist", "Fuel Tanks"], "shift": "DAY"},
    {"name": "Sgt. B. Patil",         "rank": "Lead Tech",         "specialty": "Landing Gear","certs": ["Tricycle LG", "Heavy LG"],      "shift": "NIGHT"},
    {"name": "JWO H. Gupta",          "rank": "Master Specialist", "specialty": "Propulsion",  "certs": ["AL-31FP", "M88-2"],             "shift": "NIGHT"},
    {"name": "AC L. Verma",           "rank": "Junior Tech",       "specialty": "Avionics",    "certs": ["EL/M-2052"],                    "shift": "NIGHT"},
]

# Maintenance bay definitions
BAY_DEFINITIONS = [
    {"code": "BAY-01", "name": "Heavy Maintenance Bay Alpha",    "hangar": "Hangar-1", "type": "HEAVY_MAINTENANCE",     "caps": ["Engine Overhaul", "Structural Repair", "Full Inspection"]},
    {"code": "BAY-02", "name": "Heavy Maintenance Bay Bravo",    "hangar": "Hangar-1", "type": "HEAVY_MAINTENANCE",     "caps": ["Engine Overhaul", "Landing Gear Overhaul"]},
    {"code": "BAY-03", "name": "Quick Turnaround Bay Charlie",   "hangar": "Hangar-2", "type": "QUICK_TURNAROUND",      "caps": ["Component Swap", "Sensor Calibration", "Software Update"]},
    {"code": "BAY-04", "name": "Quick Turnaround Bay Delta",     "hangar": "Hangar-2", "type": "QUICK_TURNAROUND",      "caps": ["Component Swap", "Minor Repair"]},
    {"code": "BAY-05", "name": "Avionics Cleanroom Echo",        "hangar": "Hangar-3", "type": "AVIONICS_CLEANROOM",    "caps": ["Radar Repair", "EW Suite Servicing", "Avionics Diagnostics"]},
    {"code": "BAY-06", "name": "Fuel & Hydraulics Bay Foxtrot",  "hangar": "Hangar-3", "type": "QUICK_TURNAROUND",      "caps": ["Fuel System Repair", "Hydraulic Flush", "Pressure Test"]},
]

# Spare parts catalog
SPARE_PARTS_CATALOG = [
    {"pn": "SP-ENG-BRG-001", "name": "Main Shaft Bearing Assembly",       "cat": "Propulsion",  "compat": ["Su-30MKI", "Rafale"], "stock": 8,  "min": 4, "lead": 21, "cost": 45000.0},
    {"pn": "SP-ENG-TUR-002", "name": "High-Pressure Turbine Blade Set",   "cat": "Propulsion",  "compat": ["Su-30MKI"],           "stock": 3,  "min": 2, "lead": 45, "cost": 120000.0},
    {"pn": "SP-ENG-IGN-003", "name": "Engine Igniter Module",             "cat": "Propulsion",  "compat": ["Rafale", "Tejas Mk1A"],"stock": 12, "min": 6, "lead": 14, "cost": 8500.0},
    {"pn": "SP-HYD-PMP-004", "name": "Hydraulic Pump Assembly",           "cat": "Hydraulics",  "compat": ["Su-30MKI", "Rafale", "Tejas Mk1A"], "stock": 6, "min": 3, "lead": 28, "cost": 32000.0},
    {"pn": "SP-HYD-ACT-005", "name": "FBW Hydraulic Actuator",            "cat": "Hydraulics",  "compat": ["Tejas Mk1A"],         "stock": 4,  "min": 2, "lead": 35, "cost": 55000.0},
    {"pn": "SP-AVI-LRU-006", "name": "Radar LRU Module",                  "cat": "Avionics",    "compat": ["Su-30MKI", "Rafale", "Tejas Mk1A"], "stock": 5, "min": 3, "lead": 30, "cost": 95000.0},
    {"pn": "SP-AVI-EWP-007", "name": "EW Processor Card",                 "cat": "Avionics",    "compat": ["Rafale"],             "stock": 2,  "min": 2, "lead": 60, "cost": 140000.0},
    {"pn": "SP-FUEL-VLV-008","name": "Fuel Control Valve Assembly",        "cat": "Fuel Systems","compat": ["Su-30MKI", "Rafale", "Tejas Mk1A"], "stock": 10, "min": 5, "lead": 14, "cost": 12000.0},
    {"pn": "SP-LG-STRUT-009","name": "Landing Gear Oleo Strut",           "cat": "Landing Gear","compat": ["Su-30MKI", "Rafale"], "stock": 3,  "min": 2, "lead": 42, "cost": 75000.0},
    {"pn": "SP-LG-TIRE-010", "name": "Main Wheel Tire Assembly",          "cat": "Landing Gear","compat": ["Su-30MKI", "Rafale", "Tejas Mk1A"], "stock": 20, "min": 10,"lead": 7, "cost": 3500.0},
    {"pn": "SP-AFR-PNL-011", "name": "Composite Skin Panel",              "cat": "Airframe",    "compat": ["Tejas Mk1A"],         "stock": 6,  "min": 3, "lead": 21, "cost": 28000.0},
    {"pn": "SP-BAT-CELL-012","name": "Main Battery Cell Module",           "cat": "Electrical",  "compat": ["Su-30MKI", "Rafale", "Tejas Mk1A"], "stock": 15, "min": 8, "lead": 10, "cost": 6500.0},
]
