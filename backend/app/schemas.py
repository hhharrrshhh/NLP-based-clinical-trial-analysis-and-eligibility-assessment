"""Strict public API request contracts."""
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Measurement(Request):
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=24)


class SyntheticProfile(Request):
    patient_id: str = Field(default="SYN-DEMO-001", min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    is_synthetic: StrictBool
    age: float | Measurement | None = None
    bmi: float | Measurement | None = None
    hba1c: float | Measurement | None = None
    systolic_bp: float | Measurement | None = None
    diastolic_bp: float | Measurement | None = None
    sex: Literal["MALE", "FEMALE"] | None = None
    type_2_diabetes: StrictBool | None = None
    type_1_diabetes: StrictBool | None = None
    severe_renal_impairment: StrictBool | None = None
    severe_kidney_disease: StrictBool | None = None
    hypertension: StrictBool | None = None
    pregnant: StrictBool | None = None

    @field_validator("is_synthetic")
    @classmethod
    def synthetic_only(cls, value):
        if value is not True:
            raise ValueError("Only explicitly synthetic profiles are supported.")
        return value

    @field_validator("age", "bmi", "hba1c", "systolic_bp", "diastolic_bp", mode="before")
    @classmethod
    def finite_measurements(cls, value):
        raw = value.get("value") if isinstance(value, dict) else value
        if raw is not None:
            try:
                valid = not isinstance(raw, bool) and isinstance(raw, (int, float)) and math.isfinite(raw) and raw >= 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("Measurements must be finite nonnegative numbers or null.")
        return value


class ExtractRequest(Request):
    text: str = Field(default="", max_length=100_000)
    study_id: str | None = Field(default=None, max_length=80)
    transformer: bool = False


class CompareRequest(Request):
    study_ids: list[str] = Field(min_length=2, max_length=2)


class EvaluateRequest(Request):
    study_id: str = Field(min_length=1, max_length=80)
    profile: SyntheticProfile


class ReviewRequest(Request):
    study_id: str = Field(min_length=1, max_length=80)
    extraction_hash: str = Field(min_length=64, max_length=64)
    rule_ids: list[str] = Field(min_length=1, max_length=1000)
    decision: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=1, max_length=80)
    purpose: Literal["synthetic_demo"] = "synthetic_demo"


class AskRequest(Request):
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["hybrid", "lexical", "semantic"] = "hybrid"
    k: int = Field(default=5, ge=1, le=10)
    country: Literal["India", "United States"] | None = None
    status: str | None = Field(default=None, max_length=60)
    generate: bool = False
    profile: SyntheticProfile | None = None
