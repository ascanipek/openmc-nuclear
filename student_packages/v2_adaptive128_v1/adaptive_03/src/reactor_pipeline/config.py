"""Strict versioned JSON scenario definitions and stable identities."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

MODEL_ID = "openmc_example_pwr_assembly_pilot"
SCHEMA_VERSION = 1

def keys(value, required):
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required)
    if missing or unknown:
        raise ValueError(f"Missing: {sorted(missing)}; unknown: {sorted(unknown)}")

def number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be finite and in [{low}, {high}]")
    return float(value)

def integer(value, label, low):
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise ValueError(f"{label} must be an integer >= {low}")
    return value

def digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

@dataclass(frozen=True)
class Physics:
    model: str
    boron_ppm_mass: float
    water_density_g_cm3: float
    temperature_K: float
    temperature_method: str

    @classmethod
    def parse(cls, data):
        keys(data, cls.__dataclass_fields__)
        if data["model"] != MODEL_ID:
            raise ValueError(f"Only {MODEL_ID} is supported")
        if data["temperature_method"] != "nearest":
            raise ValueError("Only nearest temperature lookup is supported")
        return cls(data["model"], number(data["boron_ppm_mass"], "boron_ppm_mass", 0, 10000),
                   number(data["water_density_g_cm3"], "water_density_g_cm3", 0.01, 2),
                   number(data["temperature_K"], "temperature_K", 250, 1500), data["temperature_method"])

@dataclass(frozen=True)
class Calculation:
    batches: int
    inactive: int
    particles: int
    seed: int
    threads: int

    @classmethod
    def parse(cls, data):
        keys(data, cls.__dataclass_fields__)
        batches = integer(data["batches"], "batches", 2)
        inactive = integer(data["inactive"], "inactive", 0)
        if inactive >= batches:
            raise ValueError("inactive must be less than batches")
        return cls(batches, inactive, integer(data["particles"], "particles", 1),
                   integer(data["seed"], "seed", 1), integer(data["threads"], "threads", 1))

@dataclass(frozen=True)
class Scenario:
    name: str
    physics: Physics
    calculation: Calculation

    @property
    def scenario_id(self):
        return digest(asdict(self.physics))

    def definition(self):
        return {"schema_version": SCHEMA_VERSION, "name": self.name,
                "physics": asdict(self.physics), "calculation": asdict(self.calculation)}

    @classmethod
    def parse(cls, data):
        keys(data, ("schema_version", "name", "physics", "calculation"))
        if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
            raise ValueError(f"Only schema_version {SCHEMA_VERSION} is supported")
        if not isinstance(data["name"], str) or not data["name"].strip():
            raise ValueError("name must be nonempty")
        return cls(data["name"], Physics.parse(data["physics"]), Calculation.parse(data["calculation"]))

def load_scenarios(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "scenarios" in data:
        keys(data, ("schema_version", "scenarios"))
        if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
            raise ValueError("Unsupported scenario list schema_version")
        if not isinstance(data["scenarios"], list) or not data["scenarios"]:
            raise ValueError("scenarios must be a nonempty list")
        return [Scenario.parse({"schema_version": SCHEMA_VERSION, **item}) for item in data["scenarios"]]
    return [Scenario.parse(data)]

