"""api/schemas/analytics.py — request/response models for the Analytics screen."""

from __future__ import annotations

from pydantic import BaseModel


class AnalysisTypeInfo(BaseModel):
    id: str
    label: str
    param_label: str
    min_default: float
    max_default: float


class AnalyticsConfig(BaseModel):
    types: list[AnalysisTypeInfo]


class RunAnalysisRequest(BaseModel):
    analysis_type: str
    min_pct: float
    max_pct: float
