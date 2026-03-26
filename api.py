"""
api.py — ThrottleGuard DPF Status API

Exposes a FastAPI server for both internal use (AI Dispatcher / Streamlit)
and external clients (fleet management software, mobile apps, etc.).

Authentication:
  All endpoints except /health require an API key in the X-API-Key header.
  Set THROTTLEGUARD_API_KEY environment variable to enable key enforcement.
  If the env var is not set, auth is skipped (useful for local dev).

Endpoints:
  GET  /health                 — Railway health check (no auth required)
  GET  /api/dpf-status         — All trucks' current DPF risk (used by AI Dispatcher)
  POST /predict                — Single truck prediction from live sensor readings
  POST /predict/batch          — Multiple trucks in one request
  POST /validate               — Validate sensor data before prediction

Run:
  uvicorn api:app --host 0.0.0.0 --port 8001
"""

import os
import pathlib
from typing import List, Optional, Dict, Any

import pandas as pd
import uvicorn
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data_processing import preprocess

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="ThrottleGuard DPF API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

BASE_DIR = pathlib.Path(__file__).parent

# ── Risk thresholds (matches ThrottleGuard spec exactly) ─────────────────────
# CRITICAL <= 3 days, HIGH <= 7, MEDIUM <= 21, LOW > 21

RISK_THRESHOLDS = {"CRITICAL": 3, "HIGH": 7, "MEDIUM": 21}

# Risk weights for scoring — higher = more urgent
RISK_WEIGHTS = {"CRITICAL": 10, "HIGH": 5, "MEDIUM": 2, "LOW": 1}

# ── J1939 feature set — all 24 required inputs ───────────────────────────────
# These are the exact features the model was trained on.
# Any incoming data missing these will be flagged by /validate.

J1939_FEATURES = [
    "soot_load_pct", "diff_pressure_psi", "peak_regen_temp_f",
    "regen_completion_rate", "incomplete_regen_streak", "regens_last_7_days",
    "nox_ppm", "pm_level_mg", "egt_pre_turbo_f", "egt_post_turbo_f",
    "egt_pre_dpf_f", "egt_post_dpf_f", "egt_dpf_delta_f", "def_level_pct",
    "idle_hours_24h", "idle_pct", "engine_load_pct", "engine_hours_total",
    "miles_on_dpf", "engine_age_years", "ambient_temp_f", "baro_pressure_kpa",
    "coolant_temp_f", "fuel_quality_score",
]

# Valid sensor ranges for validation — based on 20 years field experience
# Values outside these ranges are flagged as WARN or FAIL
SENSOR_RANGES = {
    "soot_load_pct":          (0, 100),
    "diff_pressure_psi":      (0, 15),
    "peak_regen_temp_f":      (800, 1350),
    "regen_completion_rate":  (0, 1.0),
    "incomplete_regen_streak":(0, 20),
    "regens_last_7_days":     (0, 30),
    "nox_ppm":                (0, 2000),
    "pm_level_mg":            (0, 100),
    "egt_pre_turbo_f":        (300, 1400),
    "egt_post_turbo_f":       (300, 1400),
    "egt_pre_dpf_f":          (300, 1400),
    "egt_post_dpf_f":         (300, 1400),
    "egt_dpf_delta_f":        (0, 400),
    "def_level_pct":          (0, 100),
    "idle_hours_24h":         (0, 24),
    "idle_pct":               (0, 100),
    "engine_load_pct":        (0, 100),
    "engine_hours_total":     (0, 1_000_000),
    "miles_on_dpf":           (0, 500_000),
    "engine_age_years":       (0, 30),
    "ambient_temp_f":         (-40, 130),
    "baro_pressure_kpa":      (80, 110),
    "coolant_temp_f":         (150, 250),
    "fuel_quality_score":     (0, 1.0),
}

# ── API Key authentication ────────────────────────────────────────────────────
# Set THROTTLEGUARD_API_KEY in Railway environment variables.
# External clients must send: X-Api-Key: <your-key>
# If env var is not set, auth is disabled (local dev mode).

API_KEY = os.getenv("THROTTLEGUARD_API_KEY")


def verify_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Dependency — rejects requests with wrong or missing API key."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key. Send X-Api-Key header.")


# ── Pydantic models ───────────────────────────────────────────────────────────

class SensorReading(BaseModel):
    """A single truck's J1939 sensor snapshot. All sensor fields are optional
    so /validate can report which are missing rather than returning a 422 error."""
    truck_id: str
    engine_type: Optional[str] = None  # e.g. "Cummins X15", "Detroit DD15"
    # J1939 features
    soot_load_pct: Optional[float] = None
    diff_pressure_psi: Optional[float] = None
    peak_regen_temp_f: Optional[float] = None
    regen_completion_rate: Optional[float] = None
    incomplete_regen_streak: Optional[float] = None
    regens_last_7_days: Optional[float] = None
    nox_ppm: Optional[float] = None
    pm_level_mg: Optional[float] = None
    egt_pre_turbo_f: Optional[float] = None
    egt_post_turbo_f: Optional[float] = None
    egt_pre_dpf_f: Optional[float] = None
    egt_post_dpf_f: Optional[float] = None
    egt_dpf_delta_f: Optional[float] = None
    def_level_pct: Optional[float] = None
    idle_hours_24h: Optional[float] = None
    idle_pct: Optional[float] = None
    engine_load_pct: Optional[float] = None
    engine_hours_total: Optional[float] = None
    miles_on_dpf: Optional[float] = None
    engine_age_years: Optional[float] = None
    ambient_temp_f: Optional[float] = None
    baro_pressure_kpa: Optional[float] = None
    coolant_temp_f: Optional[float] = None
    fuel_quality_score: Optional[float] = None


class PredictionResult(BaseModel):
    truck_id: str
    risk_level: str
    days_until_cleaning: Optional[float]
    risk_weight: int
    warnings: List[str]  # Domain-rule warnings from the sensor data


class ValidationIssue(BaseModel):
    field: str
    status: str   # WARN or FAIL
    message: str


class ValidationResult(BaseModel):
    truck_id: str
    status: str   # PASS, WARN, or FAIL
    issues: List[ValidationIssue]


class TruckDPFStatus(BaseModel):
    truck_id: str
    risk_level: str
    days_until_cleaning: Optional[float]


# ── Risk helpers ──────────────────────────────────────────────────────────────

def categorize_risk(days: Optional[float]) -> str:
    if days is None:
        return "UNKNOWN"
    if days <= RISK_THRESHOLDS["CRITICAL"]:
        return "CRITICAL"
    if days <= RISK_THRESHOLDS["HIGH"]:
        return "HIGH"
    if days <= RISK_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


# ── Model loading ─────────────────────────────────────────────────────────────

def load_model():
    model_path = os.getenv("MODEL_PATH", str(BASE_DIR / "model.xgb"))
    if not os.path.exists(model_path):
        return None
    try:
        import xgboost as xgb
        booster = xgb.Booster()
        booster.load_model(model_path)
        return booster
    except Exception as e:
        print(f"[ThrottleGuard API] Model load failed: {e}")
        return None


# ── Data loading (for /api/dpf-status batch read) ────────────────────────────

def load_data() -> pd.DataFrame:
    candidates = [
        os.getenv("THROTTLEGUARD_DATA_PATH", ""),
        str(BASE_DIR / "dpf_cleaning_schedule_v15.csv"),
        str(BASE_DIR / "sample_data.csv"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                df = pd.read_csv(path)
                df = preprocess(df)
                return df
            except Exception as e:
                print(f"[ThrottleGuard API] Could not load {path}: {e}")
    raise FileNotFoundError("No valid data file found for ThrottleGuard API")


# ── Prediction helpers ────────────────────────────────────────────────────────

def predict_from_df(df: pd.DataFrame) -> pd.Series:
    """Run model prediction on a DataFrame. Falls back to sensor average heuristic
    if the model file is missing — keeps the API running during early development."""
    model = load_model()
    if model is not None:
        try:
            import xgboost as xgb
            feature_cols = [c for c in df.columns
                            if c in J1939_FEATURES and pd.api.types.is_numeric_dtype(df[c])]
            dmatrix = xgb.DMatrix(df[feature_cols])
            return pd.Series(model.predict(dmatrix), index=df.index)
        except Exception as e:
            print(f"[ThrottleGuard API] Prediction failed, using fallback: {e}")

    # Fallback: higher average sensor reading = fewer days until cleaning
    numeric_cols = [c for c in df.columns if c in J1939_FEATURES
                    and pd.api.types.is_numeric_dtype(df[c])]
    if numeric_cols:
        sensor_mean = df[numeric_cols].mean(axis=1)
        return (1 - sensor_mean.clip(0, 1)) * 29 + 1
    return pd.Series([None] * len(df), index=df.index)


def reading_to_df(reading: SensorReading) -> pd.DataFrame:
    """Convert a SensorReading Pydantic model to a single-row DataFrame."""
    data = {f: [getattr(reading, f)] for f in J1939_FEATURES}
    return pd.DataFrame(data)


def check_domain_warnings(reading: SensorReading) -> List[str]:
    """Apply domain rules from 20 years of diesel experience.
    These catch patterns the model score alone might not surface clearly."""
    warnings = []

    # High backpressure matters even when soot looks OK — could be ash buildup
    if (reading.diff_pressure_psi or 0) > 8 and (reading.soot_load_pct or 0) < 40:
        warnings.append(
            "High backpressure with low soot — possible ash buildup, not just soot clogging"
        )

    # All 4 EGT sensors identical on a hot engine = sensor fault or channeling
    egt_vals = [reading.egt_pre_turbo_f, reading.egt_post_turbo_f,
                reading.egt_pre_dpf_f, reading.egt_post_dpf_f]
    if all(v is not None for v in egt_vals) and len(set(egt_vals)) == 1:
        warnings.append(
            "All 4 EGT sensors read identical — possible sensor fault or severe ash channeling"
        )

    # Declining regen temps over time = DPF degrading, not just dirty
    if (reading.peak_regen_temp_f or 999) < 900 and (reading.engine_hours_total or 0) > 50_000:
        warnings.append(
            "Low regen temp on a high-hour engine — DPF may be degrading, not just dirty"
        )

    # Classic fast-clogging combination: short-haul + high idle + poor fuel
    if ((reading.idle_pct or 0) > 40
            and (reading.fuel_quality_score or 1) < 0.4
            and (reading.miles_on_dpf or 999_999) < 100_000):
        warnings.append(
            "High idle + poor fuel quality + low miles — fastest DPF clogging combination"
        )

    # DEF critically low — SCR system at risk, nox will spike
    if (reading.def_level_pct or 100) < 10:
        warnings.append(
            "DEF level critically low — SCR system at risk, separate from DPF issue"
        )

    # Failed regens piling up
    if (reading.incomplete_regen_streak or 0) > 5:
        warnings.append(
            "Multiple consecutive failed regens — DPF is not recovering on its own"
        )

    return warnings


# ── Validation helper ─────────────────────────────────────────────────────────

def validate_reading(reading: SensorReading) -> ValidationResult:
    """Validate a single sensor reading against expected ranges and domain rules."""
    issues: List[ValidationIssue] = []

    # Check all 24 J1939 features are present
    for feature in J1939_FEATURES:
        value = getattr(reading, feature)
        if value is None:
            issues.append(ValidationIssue(
                field=feature,
                status="FAIL",
                message=f"Missing required feature: {feature}"
            ))
            continue

        # Check value is within expected range
        lo, hi = SENSOR_RANGES[feature]
        if not (lo <= value <= hi):
            issues.append(ValidationIssue(
                field=feature,
                status="WARN",
                message=f"{feature}={value} is outside expected range [{lo}, {hi}]"
            ))

    # Domain rule: high backpressure + low soot is valid — do not flag as contradiction
    # (This is intentionally not an error — ash buildup causes this)

    # Domain rule: DEF = 0 with high nox = DEF system issue, not DPF
    if (reading.def_level_pct == 0) and (reading.nox_ppm or 0) > 500:
        issues.append(ValidationIssue(
            field="def_level_pct",
            status="WARN",
            message="DEF=0 with high NOx — this is a DEF/SCR system issue, not a DPF issue"
        ))

    # Determine overall status
    if any(i.status == "FAIL" for i in issues):
        overall = "FAIL"
    elif any(i.status == "WARN" for i in issues):
        overall = "WARN"
    else:
        overall = "PASS"

    return ValidationResult(truck_id=reading.truck_id, status=overall, issues=issues)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Railway health check — no auth required."""
    return {"status": "ok", "service": "ThrottleGuard DPF API", "version": "2.0.0"}


@app.get("/api/dpf-status", response_model=List[TruckDPFStatus],
         dependencies=[Depends(verify_api_key)])
def get_dpf_status():
    """
    Returns DPF risk status for every truck in the latest dataset.
    Used by the AI Dispatcher to decide which trucks are safe to dispatch.
    Requires X-Api-Key header.
    """
    try:
        df = load_data()
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    df["_days"] = predict_from_df(df)
    df["_risk"] = df["_days"].apply(categorize_risk)

    if "truck_id" not in df.columns:
        df["truck_id"] = [f"T{i+1}" for i in range(len(df))]

    # One reading per truck — use worst-case (lowest days) reading
    result = (
        df.groupby("truck_id")
        .apply(lambda g: g.loc[g["_days"].idxmin()] if g["_days"].notna().any() else g.iloc[0])
        .reset_index(drop=True)
    )

    return [
        TruckDPFStatus(
            truck_id=str(row["truck_id"]),
            risk_level=str(row["_risk"]),
            days_until_cleaning=round(float(row["_days"]), 1) if pd.notna(row["_days"]) else None,
        )
        for _, row in result.iterrows()
    ]


@app.post("/predict", response_model=PredictionResult,
          dependencies=[Depends(verify_api_key)])
def predict(reading: SensorReading):
    """
    Predict DPF risk for a single truck from live sensor readings.
    Returns risk level, days until service, and any domain-rule warnings.
    Requires X-Api-Key header.
    """
    # Validate first — don't predict on garbage data
    validation = validate_reading(reading)
    if validation.status == "FAIL":
        missing = [i.field for i in validation.issues if i.status == "FAIL"]
        raise HTTPException(
            status_code=422,
            detail=f"Missing required sensor fields: {missing}. Run POST /validate for details."
        )

    df = reading_to_df(reading)
    days_series = predict_from_df(df)
    days = float(days_series.iloc[0]) if days_series.iloc[0] is not None else None
    risk = categorize_risk(days)
    warnings = check_domain_warnings(reading)

    print(f"[ThrottleGuard API] /predict — truck={reading.truck_id} risk={risk} days={days}")

    return PredictionResult(
        truck_id=reading.truck_id,
        risk_level=risk,
        days_until_cleaning=round(days, 1) if days is not None else None,
        risk_weight=RISK_WEIGHTS.get(risk, 1),
        warnings=warnings,
    )


@app.post("/predict/batch", response_model=List[PredictionResult],
          dependencies=[Depends(verify_api_key)])
def predict_batch(readings: List[SensorReading]):
    """
    Predict DPF risk for multiple trucks in a single request.
    Each truck is validated individually — FAIL units are returned with
    risk_level=UNKNOWN rather than rejecting the entire batch.
    Requires X-Api-Key header.
    """
    results = []

    for reading in readings:
        validation = validate_reading(reading)
        if validation.status == "FAIL":
            # Don't block the whole batch — return UNKNOWN for bad units
            missing = [i.field for i in validation.issues if i.status == "FAIL"]
            results.append(PredictionResult(
                truck_id=reading.truck_id,
                risk_level="UNKNOWN",
                days_until_cleaning=None,
                risk_weight=0,
                warnings=[f"Missing fields, cannot predict: {missing}"],
            ))
            continue

        df = reading_to_df(reading)
        days_series = predict_from_df(df)
        days = float(days_series.iloc[0]) if days_series.iloc[0] is not None else None
        risk = categorize_risk(days)
        warnings = check_domain_warnings(reading)

        results.append(PredictionResult(
            truck_id=reading.truck_id,
            risk_level=risk,
            days_until_cleaning=round(days, 1) if days is not None else None,
            risk_weight=RISK_WEIGHTS.get(risk, 1),
            warnings=warnings,
        ))

    print(f"[ThrottleGuard API] /predict/batch — {len(readings)} units, "
          f"{sum(1 for r in results if r.risk_level == 'CRITICAL')} CRITICAL")

    return results


@app.post("/validate", response_model=List[ValidationResult],
          dependencies=[Depends(verify_api_key)])
def validate(readings: List[SensorReading]):
    """
    Validate sensor data against expected J1939 ranges and domain rules
    before sending to /predict. Use this to catch bad data early.
    Returns PASS / WARN / FAIL per unit with specific issue details.
    Requires X-Api-Key header.
    """
    results = [validate_reading(r) for r in readings]

    passed = sum(1 for r in results if r.status == "PASS")
    warned = sum(1 for r in results if r.status == "WARN")
    failed = sum(1 for r in results if r.status == "FAIL")
    print(f"[ThrottleGuard API] /validate — {passed} PASS, {warned} WARN, {failed} FAIL")

    return results


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("THROTTLEGUARD_PORT", "8001"))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
