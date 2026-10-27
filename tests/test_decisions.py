from app.core.models import DecisionAction, ReasonCode
from app.services.decision import evaluate_transfer
from app.services.synthetic import (
    generate_incomplete,
    generate_occluded,
    generate_successful,
)
from app.core.config import settings
from app.vision.tracker import track_video


def _decide_from_scenario(tmp_path, generator):
    original = tmp_path / "original.mp4"
    annotated = tmp_path / "annotated.mp4"
    generator(original, settings)
    observations = track_video(original, annotated, settings)
    return evaluate_transfer(observations, settings), observations


def test_successful_transfer_decision(tmp_path):
    decision, obs = _decide_from_scenario(tmp_path, generate_successful)
    assert decision.action == DecisionAction.REVIEW_REQUIRED
    assert decision.reason_code == ReasonCode.TRANSFER_EVIDENCE_COMPLETE
    assert decision.quality_score > 70
    assert any(c.name == "settled_in_destination" and c.passed for c in decision.checks)


def test_incomplete_transfer_decision(tmp_path):
    decision, _ = _decide_from_scenario(tmp_path, generate_incomplete)
    assert decision.action == DecisionAction.RETAKE_REQUIRED
    assert decision.reason_code in {
        ReasonCode.TRANSFER_INCOMPLETE,
        ReasonCode.DESTINATION_EVIDENCE_MISSING,
    }


def test_occlusion_decision(tmp_path):
    decision, _ = _decide_from_scenario(tmp_path, generate_occluded)
    assert decision.action == DecisionAction.RETAKE_REQUIRED
    assert decision.reason_code in {
        ReasonCode.EXCESSIVE_OCCLUSION,
        ReasonCode.INSUFFICIENT_TRACKING_COVERAGE,
        ReasonCode.DESTINATION_EVIDENCE_MISSING,
        ReasonCode.TRANSFER_INCOMPLETE,
    }
    # Prefer documenting that occlusion gap is flagged in checks
    occ = next(c for c in decision.checks if c.name == "occlusion_gap")
    assert occ.passed is False
