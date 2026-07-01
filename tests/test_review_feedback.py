import pytest
from pydantic import ValidationError

from src.review.feedback import create_review_feedback


def test_create_approved_feedback():
    feedback = create_review_feedback(review_status="approved", quality_score=5)

    assert feedback.review_status == "approved"
    assert feedback.edit_required is False
    assert feedback.quality_score == 5


def test_create_rejected_feedback():
    feedback = create_review_feedback(review_status="rejected")

    assert feedback.edit_required is True
    assert feedback.rewrite_required is False


def test_needs_rewrite_sets_flags():
    feedback = create_review_feedback(review_status="needs_rewrite")

    assert feedback.edit_required is True
    assert feedback.rewrite_required is True


def test_needs_source_fix_sets_flags():
    feedback = create_review_feedback(review_status="needs_source_fix")

    assert feedback.edit_required is True
    assert feedback.source_fix_required is True


def test_needs_compliance_fix_sets_flags():
    feedback = create_review_feedback(review_status="needs_compliance_fix")

    assert feedback.edit_required is True
    assert feedback.compliance_fix_required is True


def test_needs_language_fix_sets_flags():
    feedback = create_review_feedback(review_status="needs_language_fix")

    assert feedback.edit_required is True
    assert feedback.language_fix_required is True


def test_scores_one_to_five_pass():
    feedback = create_review_feedback(
        review_status="approved",
        quality_score=1,
        factuality_score=2,
        language_score=3,
        seo_score=4,
        compliance_score=5,
    )

    assert feedback.compliance_score == 5


def test_score_zero_or_six_fails():
    with pytest.raises(ValidationError):
        create_review_feedback(review_status="approved", quality_score=0)
    with pytest.raises(ValidationError):
        create_review_feedback(review_status="approved", quality_score=6)


def test_feedback_id_and_timestamp_are_generated():
    feedback = create_review_feedback(review_status="approved")

    assert feedback.feedback_id.startswith("feedback-")
    assert feedback.timestamp.endswith("Z")
