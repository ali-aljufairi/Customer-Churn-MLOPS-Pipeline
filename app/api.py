from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = Path(os.getenv("MODEL_DIR", ROOT / "artifacts"))


class CustomerFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")
    State: str = Field(pattern=r"^[A-Za-z]{2}$", description="Two-letter US state code")
    Account_Length: int = Field(alias="Account Length", ge=1, le=5000)
    Area_Code: int = Field(alias="Area Code", ge=100, le=999)
    Int_l_Plan: Literal["yes", "no"] = Field(alias="Int'l Plan")
    VMail_Plan: Literal["yes", "no"] = Field(alias="VMail Plan")
    VMail_Message: int = Field(alias="VMail Message", ge=0, le=1000)
    Day_Mins: float = Field(alias="Day Mins", ge=0, le=2000)
    Day_Calls: int = Field(alias="Day Calls", ge=0, le=1000)
    Day_Charge: float = Field(alias="Day Charge", ge=0, le=1000)
    Eve_Mins: float = Field(alias="Eve Mins", ge=0, le=2000)
    Eve_Calls: int = Field(alias="Eve Calls", ge=0, le=1000)
    Eve_Charge: float = Field(alias="Eve Charge", ge=0, le=1000)
    Night_Mins: float = Field(alias="Night Mins", ge=0, le=2000)
    Night_Calls: int = Field(alias="Night Calls", ge=0, le=1000)
    Night_Charge: float = Field(alias="Night Charge", ge=0, le=1000)
    Intl_Mins: float = Field(alias="Intl Mins", ge=0, le=2000)
    Intl_Calls: int = Field(alias="Intl Calls", ge=0, le=1000)
    Intl_Charge: float = Field(alias="Intl Charge", ge=0, le=1000)
    CustServ_Calls: int = Field(alias="CustServ Calls", ge=0, le=1000)


class Prediction(BaseModel):
    churn: bool
    churn_probability: float = Field(ge=0, le=1)
    risk_level: Literal["low", "moderate", "high"]
    threshold: float
    explanation: list[str]
    model_version: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = None
    app.state.metadata = None
    try:
        app.state.model = joblib.load(ARTIFACT_DIR / "model.joblib")
        app.state.metadata = json.loads((ARTIFACT_DIR / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, EOFError, KeyError):
        pass
    yield


app = FastAPI(title="Customer Churn Risk API", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="Model is not available")
    return {"status": "ready"}


@app.get("/metadata")
def metadata() -> dict:
    if app.state.metadata is None:
        raise HTTPException(status_code=503, detail="Model metadata is not available")
    return app.state.metadata


def _explanation(values: dict) -> list[str]:
    reasons = []
    if values["CustServ Calls"] >= 3:
        reasons.append("Frequent customer-service calls may signal unresolved issues.")
    if values["Int'l Plan"] == "yes":
        reasons.append("An international plan is associated with higher churn in this dataset.")
    if values["Day Mins"] >= 250:
        reasons.append("High daytime usage can be a useful retention-review signal.")
    if not reasons:
        reasons.append("No selected high-signal indicators were triggered; probability reflects the full model.")
    return reasons


@app.post("/predict", response_model=Prediction)
def predict(customer: CustomerFeatures) -> Prediction:
    if app.state.model is None or app.state.metadata is None:
        raise HTTPException(status_code=503, detail="Prediction model is not available")
    values = customer.model_dump(by_alias=True)
    try:
        probability = float(app.state.model.predict_proba(pd.DataFrame([values]))[0][1])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail="Features could not be processed") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Prediction failed") from exc
    threshold = float(app.state.metadata.get("threshold", 0.5))
    return Prediction(
        churn=probability >= threshold, churn_probability=probability,
        risk_level="high" if probability >= 0.65 else "moderate" if probability >= 0.35 else "low",
        threshold=threshold, explanation=_explanation(values),
        model_version=str(app.state.metadata.get("model_version", "unknown")),
    )
