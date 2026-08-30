from onyx.db.ai_improvement import mask_evaluation_text
from onyx.quality.offline_eval import _aggregate


def test_mask_evaluation_text_removes_contact_details() -> None:
    masked = mask_evaluation_text("Email jane@example.com or call +66 81 234 5678")

    assert masked == "Email [EMAIL] or call [PHONE]"


def test_aggregate_calculates_release_metrics() -> None:
    summary = _aggregate(
        [
            {
                "score": 0.8,
                "meets_expected_outcome": True,
                "harmful_or_unsafe": False,
            },
            {
                "score": 0.6,
                "meets_expected_outcome": False,
                "harmful_or_unsafe": True,
            },
        ]
    )

    assert summary == {
        "case_count": 2,
        "mean_score": 0.7,
        "success_rate": 0.5,
        "unsafe_count": 1,
    }
