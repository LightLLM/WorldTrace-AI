"""Pydantic models for episodes, decisions, and API payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DecisionAction(str, Enum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    RETAKE_REQUIRED = "RETAKE_REQUIRED"


class ReasonCode(str, Enum):
    TRANSFER_EVIDENCE_COMPLETE = "TRANSFER_EVIDENCE_COMPLETE"
    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
    SOURCE_EVIDENCE_MISSING = "SOURCE_EVIDENCE_MISSING"
    DESTINATION_EVIDENCE_MISSING = "DESTINATION_EVIDENCE_MISSING"
    TRANSFER_INCOMPLETE = "TRANSFER_INCOMPLETE"
    EXCESSIVE_OCCLUSION = "EXCESSIVE_OCCLUSION"
    INSUFFICIENT_TRACKING_COVERAGE = "INSUFFICIENT_TRACKING_COVERAGE"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class ZoneName(str, Enum):
    SOURCE = "source"
    TRANSIT = "transit"
    DESTINATION = "destination"
    OUTSIDE = "outside"


class ScenarioName(str, Enum):
    SUCCESSFUL = "successful"
    INCOMPLETE = "incomplete"
    OCCLUDED = "occluded"


class Observation(BaseModel):
    frame_index: int
    timestamp_sec: float
    visible: bool
    cx: Optional[float] = None
    cy: Optional[float] = None
    nx: Optional[float] = None
    ny: Optional[float] = None
    area: float = 0.0
    confidence: float = 0.0
    zone: ZoneName = ZoneName.OUTSIDE
    bbox: Optional[List[int]] = None


class EvidenceCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class DecisionResult(BaseModel):
    action: DecisionAction
    reason_code: ReasonCode
    quality_score: float
    summary: str
    checks: List[EvidenceCheck]
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ReviewRequest(BaseModel):
    action: str = Field(..., description="approve or reject")
    reviewer: str = "local-reviewer"
    notes: str = ""


class ReviewResult(BaseModel):
    status: ReviewStatus
    reviewer: str
    notes: str = ""
    reviewed_at: str


class EpisodeSummary(BaseModel):
    episode_id: str
    created_at: str
    scenario: Optional[str] = None
    status: str
    decision: Optional[DecisionAction] = None
    reason_code: Optional[ReasonCode] = None
    review_status: ReviewStatus = ReviewStatus.PENDING
    quality_score: Optional[float] = None
    tracked_frames: int = 0
    total_frames: int = 0


class EpisodeDetail(EpisodeSummary):
    events: List[Dict[str, Any]] = Field(default_factory=list)
    decision_payload: Optional[DecisionResult] = None
    review: Optional[ReviewResult] = None
    media: Dict[str, str] = Field(default_factory=dict)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
