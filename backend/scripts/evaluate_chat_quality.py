"""Evaluate stored assistant responses with the configured default LLM."""

import argparse

from onyx.db.chat_quality import (
    fetch_quality_review_candidates,
    upsert_quality_evaluation,
)
from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.llm.factory import get_default_llm
from onyx.quality.judge import evaluate_response_with_llm_judge


def valid_days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= 365:
        raise argparse.ArgumentTypeError("days must be between 1 and 365")
    return days


def valid_limit(value: str) -> int:
    limit = int(value)
    if not 1 <= limit <= 100:
        raise argparse.ArgumentTypeError("limit must be between 1 and 100")
    return limit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate unreviewed assistant responses with an LLM judge."
    )
    parser.add_argument("--days", type=valid_days, default=30)
    parser.add_argument("--limit", type=valid_limit, default=20)
    parser.add_argument("--message-id", type=int)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the selected response count without sending chat data.",
    )
    parser.add_argument(
        "--confirm-external-processing",
        action="store_true",
        help="Confirm that policy permits sending stored chat data to the default LLM.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.dry_run and not args.confirm_external_processing:
        raise ValueError(
            "Add --confirm-external-processing after you verify the data policy."
        )

    SqlEngine.init_engine(pool_size=2, max_overflow=0)
    failures: list[str] = []
    try:
        with get_session_with_current_tenant() as db_session:
            candidates = fetch_quality_review_candidates(
                db_session=db_session,
                days=args.days,
                limit=args.limit,
                chat_message_id=args.message_id,
            )
            print(f"Selected {len(candidates)} unreviewed responses.")
            if args.dry_run or not candidates:
                return

            llm = get_default_llm(timeout=60, temperature=0)
            for index, candidate in enumerate(candidates, start=1):
                try:
                    evaluation = evaluate_response_with_llm_judge(candidate, llm)
                    upsert_quality_evaluation(
                        db_session=db_session,
                        chat_message_id=candidate.chat_message_id,
                        reviewer_user_id=None,
                        evaluation_input=evaluation,
                    )
                    print(
                        f"[{index}/{len(candidates)}] Evaluated message "
                        f"{candidate.chat_message_id}."
                    )
                except Exception as error:
                    failures.append(f"message {candidate.chat_message_id}: {error}")
    finally:
        SqlEngine.reset_engine()

    if failures:
        raise RuntimeError("Quality evaluation failures: " + "; ".join(failures))


if __name__ == "__main__":
    main()
