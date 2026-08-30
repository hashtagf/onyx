# AI response quality

The AI quality dashboard combines automatic telemetry with explicit response
reviews. Open **Admin > Usage Report** and select a period.

## Automatic measures

These measures use existing chat and usage data. They need no manual review.

| Measure | Definition |
| --- | --- |
| Response error rate | Assistant messages with an error divided by all assistant messages. |
| Citation coverage | Assistant messages with one or more citations divided by all assistant messages. |
| Feedback coverage | Rated assistant messages divided by all assistant messages. |
| Positive feedback | Positive ratings divided by all rated messages. |
| P95 response time | The 95th percentile of stored response processing time. |
| Conversation effort | Average user turns in each active chat session. |

## Reviewed measures

These measures need a human review or an approved judge-model review. A missing
review is not a failed response. The dashboard shows `n` for every measure.

| Measure | Definition |
| --- | --- |
| Task success | Reviews marked as a completed user task. |
| First-answer resolution | Reviews where the first response completed the task. |
| Required rephrase | Reviews where the user had to state the request again. |
| Answer quality | `correctness × 35% + relevance × 25% + completeness × 20% + clarity × 10% + instruction following × 10%`. Each input uses a 1–5 score. |
| Grounded answer | Reviews where the available sources support the response. |
| Citation accuracy | A 1–5 score for how well citations support claims. |
| Retrieval relevance | A 1–5 score for the retrieved source quality. |
| Hallucination | Reviews that found an unsupported claim. |
| Refusal quality | Appropriate refusals and false refusals are reported separately. |

The estimated cost per successful response uses the reviewed task-success rate
to estimate successful responses for the full period. It then divides period
cost by that estimate. Use it as a trend, not as an accounting value.

## Review a response

1. Open **Admin > Usage Report**.
2. Select the required period.
3. Find a conversation in **Chat History**.
4. Select the conversation row.
5. Complete **Quality review** below an assistant response.
6. Set all five answer-quality scores together.
7. Select each safety incident that occurred.
8. Select **Save review**.

The dashboard refreshes after the review is saved. Select **Remove review** to
delete an incorrect review.

The review queue assigns work to full administrators. A reviewer selects
**Claim** before scoring a response. The claim expires if the reviewer does not
finish it. The queue prioritizes safety incidents, hallucinations, false
refusals, negative feedback, low-confidence judge results, and a random sample.

Human and judge reviews remain separate. Reports use the human review when both
sources exist. The dashboard reports agreement and score error for paired
reviews. Use these measures to calibrate the judge.

## Run the automatic LLM judge

The judge selects only unreviewed assistant responses. It uses the configured
default LLM and stores `evaluation_source=llm_judge`.

First, check the selection without sending chat content:

```bash
uv run --directory backend python scripts/evaluate_chat_quality.py \
  --days 30 --limit 20 --dry-run
```

Review the organization's data-processing policy. The configured LLM can be an
external service. Run the judge only after the policy permits this transfer:

```bash
uv run --directory backend python scripts/evaluate_chat_quality.py \
  --days 30 --limit 20 --confirm-external-processing
```

Use `--message-id ID` to evaluate one response. The limit cannot exceed 100 in
one run. The script truncates long inputs and uses at most 10 source blurbs.
It reports all failed message IDs and exits with an error when any review fails.

Compare judge scores with a human-reviewed sample before using them for a
decision. The judge does not replace a security investigation or a source-of-
truth check.

For scheduled evaluation, set both values to `true`:

```text
ENABLE_CHAT_QUALITY_JUDGE=true
CHAT_QUALITY_EXTERNAL_PROCESSING_APPROVED=true
```

The second setting records the required data-processing approval. Keep it
`false` if chat data cannot go to the configured LLM. Scheduled jobs have daily
limits, retries, timeouts, and durable status records.

## Improve Prompt and Skill configurations

Open **Admin > AI Improvement**. This page controls the change cycle.

1. Select an Agent, custom Skill, or built-in Skill.
2. Edit the Prompt or Skill instructions.
3. State the cause and expected effect.
4. Save an immutable candidate version.
5. Create and freeze an offline evaluation dataset.
6. Run the baseline and candidate on the same cases.
7. Approve only a candidate that passes all release gates.
8. Start a stable 10 percent canary.
9. Stop the canary or promote it to production.

Saving a candidate does not change live traffic. New chat sessions store the
selected configuration version. Each assistant message also stores that
version. Existing sessions keep their assigned version.

The offline gate requires a candidate score of at least 0.70. It also requires
no quality regression, no success-rate regression, and no unsafe result. A
reviewed canary safety incident stops new canary assignments automatically.

Built-in Skill source files stay deployment-controlled. The studio versions
the Skill description and `SKILL.md` instructions. The system applies the new
instructions only after promotion.

## Safety guardrails

The dashboard counts harmful responses, sensitive data leaks, unauthorized
document exposure, policy violations, and successful prompt injections. These
counts do not contribute to the average quality score. Investigate every count
above zero.

## API

All endpoints require full admin access.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/manage/admin/usage-insights/quality-overview?days=30` | Read KPI aggregates. |
| `GET` | `/api/manage/admin/usage-insights/quality-evaluations/{message_id}` | Read one evaluation. |
| `PUT` | `/api/manage/admin/usage-insights/quality-evaluations/{message_id}` | Create or replace one evaluation. |
| `DELETE` | `/api/manage/admin/usage-insights/quality-evaluations/{message_id}` | Remove one evaluation. |
| `GET` | `/api/manage/admin/usage-insights/quality-review-queue` | Read assigned review work. |
| `GET` | `/api/manage/admin/ai-improvement/targets` | Read versioned Agent and Skill targets. |
| `POST` | `/api/manage/admin/ai-improvement/versions` | Create an immutable candidate. |
| `POST` | `/api/manage/admin/ai-improvement/runs` | Create an offline evaluation run. |
| `POST` | `/api/manage/admin/ai-improvement/canaries` | Start a controlled release. |

Run `uv run alembic upgrade head` from `backend/` before the first use.

## Privacy

The page exposes conversation content to full administrators. Limit this role
to approved reviewers. Apply the organization's retention, consent, and access
review rules. Incognito usage-only sessions contain no stored content and
cannot be reviewed.
