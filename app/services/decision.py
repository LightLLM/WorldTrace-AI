"""Explicit evidence checks and decision state machine.

Quality score formula (transparent heuristic, NOT a probability):

    quality_score = 100 * (
        0.20 * started_in_source
      + 0.15 * left_source
      + 0.15 * transit_observed
      + 0.20 * reached_destination
      + 0.15 * settled_in_destination
      + 0.10 * visibility_ratio
      + 0.05 * min(1.0, tracking_coverage)
    )

Each boolean term is 1.0 if true else 0.0.
visibility_ratio = visible_frames / total_frames
tracking_coverage = distinct_zone_transitions_and_path_span heuristic:
    tracked_visible_frames / total_frames
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.core.config import Settings, settings
from app.core.models import (
    DecisionAction,
    DecisionResult,
    EvidenceCheck,
    Observation,
    ReasonCode,
    ZoneName,
)


def _longest_false_run(flags: List[bool]) -> int:
    longest = current = 0
    for visible in flags:
        if not visible:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _max_consecutive_zone(observations: List[Observation], zone: ZoneName) -> int:
    best = current = 0
    for obs in observations:
        if obs.visible and obs.zone == zone:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def evaluate_transfer(
    observations: List[Observation],
    cfg: Settings = settings,
) -> DecisionResult:
    total = len(observations)
    if total == 0:
        return DecisionResult(
            action=DecisionAction.RETAKE_REQUIRED,
            reason_code=ReasonCode.OBJECT_NOT_FOUND,
            quality_score=0.0,
            summary="No frames available for evaluation.",
            checks=[
                EvidenceCheck(
                    name="frames_present",
                    passed=False,
                    detail="Observation list is empty.",
                )
            ],
            metrics={"total_frames": 0},
        )

    visible_flags = [o.visible for o in observations]
    visible_count = sum(1 for v in visible_flags if v)
    visibility_ratio = visible_count / total
    tracking_coverage = visibility_ratio
    occlusion_gap = _longest_false_run(visible_flags)

    zones_seq = [o.zone for o in observations if o.visible]
    first_visible_zone = zones_seq[0] if zones_seq else None

    started_in_source = first_visible_zone == ZoneName.SOURCE
    saw_source = any(z == ZoneName.SOURCE for z in zones_seq)
    saw_transit = sum(1 for z in zones_seq if z == ZoneName.TRANSIT) >= cfg.min_transit_frames
    saw_destination = any(z == ZoneName.DESTINATION for z in zones_seq)
    settled = _max_consecutive_zone(observations, ZoneName.DESTINATION) >= cfg.settle_frames_required

    left_source = False
    if saw_source:
        seen_source = False
        for z in zones_seq:
            if z == ZoneName.SOURCE:
                seen_source = True
            elif seen_source and z != ZoneName.SOURCE:
                left_source = True
                break

    reached_destination = saw_destination and left_source
    object_found = visible_count > 0

    checks = [
        EvidenceCheck(
            name="object_found",
            passed=object_found,
            detail=f"Visible frames: {visible_count}/{total}",
        ),
        EvidenceCheck(
            name="started_in_source",
            passed=started_in_source,
            detail=f"First visible zone: {first_visible_zone}",
        ),
        EvidenceCheck(
            name="left_source",
            passed=left_source,
            detail="Object left the source zone after being observed there."
            if left_source
            else "Object never left source after source observation.",
        ),
        EvidenceCheck(
            name="transit_observed",
            passed=saw_transit,
            detail=f"Transit frames observed: {sum(1 for z in zones_seq if z == ZoneName.TRANSIT)} "
            f"(min {cfg.min_transit_frames})",
        ),
        EvidenceCheck(
            name="reached_destination",
            passed=reached_destination,
            detail="Destination reached after leaving source."
            if reached_destination
            else "Destination not reached after a valid leave-source sequence.",
        ),
        EvidenceCheck(
            name="settled_in_destination",
            passed=settled,
            detail=f"Max consecutive destination frames: "
            f"{_max_consecutive_zone(observations, ZoneName.DESTINATION)} "
            f"(required {cfg.settle_frames_required})",
        ),
        EvidenceCheck(
            name="visibility_ratio",
            passed=visibility_ratio >= cfg.min_visibility_ratio,
            detail=f"visibility_ratio={visibility_ratio:.3f} "
            f"(min {cfg.min_visibility_ratio})",
        ),
        EvidenceCheck(
            name="tracking_coverage",
            passed=tracking_coverage >= cfg.min_tracking_coverage,
            detail=f"tracking_coverage={tracking_coverage:.3f} "
            f"(min {cfg.min_tracking_coverage})",
        ),
        EvidenceCheck(
            name="occlusion_gap",
            passed=occlusion_gap <= cfg.max_occlusion_gap_frames,
            detail=f"Longest occlusion gap={occlusion_gap} "
            f"(max allowed {cfg.max_occlusion_gap_frames})",
        ),
    ]

    quality = 100.0 * (
        0.20 * float(started_in_source)
        + 0.15 * float(left_source)
        + 0.15 * float(saw_transit)
        + 0.20 * float(reached_destination)
        + 0.15 * float(settled)
        + 0.10 * float(visibility_ratio)
        + 0.05 * float(min(1.0, tracking_coverage))
    )
    quality = round(quality, 2)

    metrics: Dict[str, Any] = {
        "total_frames": total,
        "visible_frames": visible_count,
        "visibility_ratio": round(visibility_ratio, 4),
        "tracking_coverage": round(tracking_coverage, 4),
        "occlusion_gap": occlusion_gap,
        "source_frames": sum(1 for z in zones_seq if z == ZoneName.SOURCE),
        "transit_frames": sum(1 for z in zones_seq if z == ZoneName.TRANSIT),
        "destination_frames": sum(1 for z in zones_seq if z == ZoneName.DESTINATION),
        "max_destination_streak": _max_consecutive_zone(observations, ZoneName.DESTINATION),
        "quality_formula": (
            "100*(0.20*started_in_source + 0.15*left_source + 0.15*transit_observed + "
            "0.20*reached_destination + 0.15*settled_in_destination + "
            "0.10*visibility_ratio + 0.05*min(1, tracking_coverage))"
        ),
    }

    action, reason, summary = _decide(
        object_found=object_found,
        started_in_source=started_in_source,
        left_source=left_source,
        saw_transit=saw_transit,
        reached_destination=reached_destination,
        settled=settled,
        visibility_ok=visibility_ratio >= cfg.min_visibility_ratio,
        coverage_ok=tracking_coverage >= cfg.min_tracking_coverage,
        occlusion_ok=occlusion_gap <= cfg.max_occlusion_gap_frames,
        visibility_ratio=visibility_ratio,
        tracking_coverage=tracking_coverage,
        occlusion_gap=occlusion_gap,
    )

    return DecisionResult(
        action=action,
        reason_code=reason,
        quality_score=quality,
        summary=summary,
        checks=checks,
        metrics=metrics,
    )


def _decide(
    *,
    object_found: bool,
    started_in_source: bool,
    left_source: bool,
    saw_transit: bool,
    reached_destination: bool,
    settled: bool,
    visibility_ok: bool,
    coverage_ok: bool,
    occlusion_ok: bool,
    visibility_ratio: float,
    tracking_coverage: float,
    occlusion_gap: int,
) -> Tuple[DecisionAction, ReasonCode, str]:
    if not object_found:
        return (
            DecisionAction.RETAKE_REQUIRED,
            ReasonCode.OBJECT_NOT_FOUND,
            "No trackable object was detected. Retake with a clearer colored target.",
        )

    if not occlusion_ok or (not visibility_ok and occlusion_gap > 0):
        # Prefer occlusion reason when a long gap is the primary failure.
        if not occlusion_ok:
            return (
                DecisionAction.RETAKE_REQUIRED,
                ReasonCode.EXCESSIVE_OCCLUSION,
                f"Occlusion gap of {occlusion_gap} frames exceeds the allowed maximum.",
            )

    if not coverage_ok:
        return (
            DecisionAction.RETAKE_REQUIRED,
            ReasonCode.INSUFFICIENT_TRACKING_COVERAGE,
            f"Tracking coverage {tracking_coverage:.2f} is below the minimum threshold.",
        )

    if not started_in_source:
        return (
            DecisionAction.RETAKE_REQUIRED,
            ReasonCode.SOURCE_EVIDENCE_MISSING,
            "Object was not observed beginning in the source zone.",
        )

    if not reached_destination and not left_source:
        return (
            DecisionAction.RETAKE_REQUIRED,
            ReasonCode.TRANSFER_INCOMPLETE,
            "Object did not leave the source zone; transfer incomplete.",
        )

    if not reached_destination:
        return (
            DecisionAction.RETAKE_REQUIRED,
            ReasonCode.DESTINATION_EVIDENCE_MISSING
            if not settled and left_source
            else ReasonCode.TRANSFER_INCOMPLETE,
            "Object left source but never produced destination evidence.",
        )

    if not settled or not saw_transit:
        return (
            DecisionAction.RETAKE_REQUIRED,
            ReasonCode.TRANSFER_INCOMPLETE,
            "Transfer path or destination settle evidence is incomplete.",
        )

    if not visibility_ok:
        return (
            DecisionAction.RETAKE_REQUIRED,
            ReasonCode.INSUFFICIENT_TRACKING_COVERAGE,
            f"Visibility ratio {visibility_ratio:.2f} is below the minimum threshold.",
        )

    # All primary evidence checks passed.
    return (
        DecisionAction.REVIEW_REQUIRED,
        ReasonCode.TRANSFER_EVIDENCE_COMPLETE,
        "Evidence supports a completed source-to-destination transfer. Human review required.",
    )


def extract_events(observations: List[Observation]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    prev_zone = None
    for obs in observations:
        if not obs.visible:
            if prev_zone is not None:
                events.append(
                    {
                        "frame_index": obs.frame_index,
                        "type": "occlusion_start",
                        "detail": f"Lost track after {prev_zone}",
                    }
                )
                prev_zone = None
            continue
        if obs.zone != prev_zone:
            events.append(
                {
                    "frame_index": obs.frame_index,
                    "type": "zone_enter",
                    "zone": obs.zone.value,
                    "nx": obs.nx,
                    "ny": obs.ny,
                }
            )
            prev_zone = obs.zone
    return events
