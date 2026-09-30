# AI evaluation and experiment provenance

## 1. Bounded AI responsibility

**Deterministic code remains the source of truth for SLA, breach, shift, roster, and financial calculations. The LLM is used only for qualitative interpretation of likely breach causes.**

```text
Raw tickets → deterministic analysis → SLA facts / operational context
            → LLM interpretation → likely first-response breach reason
```

The model interprets an already-established first-response breach. The customer's problem is not necessarily the reason the response was late: an app crash describes a support issue, whereas overnight queue/handoff may explain timing. The prompt forbids recalculation of SLA facts, unsupported staffing/queue assumptions and assuming transfers or escalations preceded the first response.

Model: **`openai/gpt-oss-20b` via Groq's OpenAI-compatible API**, using `GROQ_API_KEY` and `GROQ_MODEL` from the environment. Temperature is 0, GPT-OSS reasoning effort is low, and completion generation is capped at 512 tokens. Confidence is model-reported and uncalibrated, not a measured probability of correctness.

V2 includes these available fields from the deterministic audit, without dumping the full row:

```text
channel, response_minutes, sla_minutes, created_shift, overnight_created,
transfers, assigned_team, priority, category, source_system, agent_id, team,
customer_message, agent_notes
```

Missing operational fields are omitted rather than inferred; numbers/booleans retain their values. `assigned_team` is the first-assigned team; `agent_id` and roster `team` describe the resolving assignment, not necessarily the first responder.

## 2. Seven-category taxonomy — unchanged

| Label | Required interpretation |
| --- | --- |
| `overnight_queue_or_handoff` | Overnight creation plus a delay consistent with next-shift pickup/queue handoff; not the flag alone. |
| `high_queue_volume` | Evidence of active queue overload or insufficient response capacity; a breach alone is insufficient. |
| `complex_or_escalated_case` | Complex investigation, specialist review, escalation or warranty/RMA work plausibly delayed first response, not merely resolution. |
| `transfer_or_ownership_delay` | Team transfer/handoff or ownership ambiguity contributed to first-response delay; an untimed transfer count is weak evidence. |
| `system_or_process_issue` | A documented support-system/workflow/process failure explains the response delay, not merely an app/payment/delivery problem experienced by the customer. |
| `customer_dependency` | Waiting for customer information/action explains first-response delay, not a later resolution wait. |
| `unclear_or_other` | Available evidence does not establish a confident primary reason, including small unexplained breaches. |

These are likely operational explanations, not proof of causation or agent culpability. Policy-supported next-shift pickup is a hypothesis about timing; the policy also specifies overnight chat coverage.

## 3. V1/pre-v2 → v2 history: keep the runs distinct

The project has three stored classification artifacts. They must not be collapsed into one evaluation:

| Artifact | Experiment | Cases | Successful | Final processing/API errors |
| --- | --- | ---: | ---: | ---: |
| `experiments/ai_v1/ai_reason_sample_initial_120.csv` | Historical v1/pre-v2 run | 120 | 115 | 5 (4.17%) |
| `experiments/ai_v1/ai_reason_sample.csv` | Later text-only 30-case baseline | 30 | 30 | 0 |
| `output/ai_reason_sample_v2.csv` | Explicit deterministic-context v2 | 30 | 30 | 0 |

**V1/pre-v2 limitation:** classification relied on customer message and agent notes without the explicit precomputed SLA/created-shift/overnight context now supplied in v2. The historical 120-ticket prompt did include some basic metadata; the later 30-ticket baseline was text-only. The **5/120 failure statistic belongs to the historical 120-case file**, not to the text-only 30-case run. The earlier runs lacked enough operational context to reliably distinguish customer issues from overnight queue/shift explanations.

The 120-case errors were **four Groq 429/rate-limit errors and one JSON-validation error**. These were API/model-output-processing issues, **not established classification errors**. The 4.17% rate is a processing/API failure rate, not model accuracy or classification error rate. Historical failures can carry an `unclear_or_other` placeholder; the `ai_error` field identifies them and excludes them from successful-only review sampling.

**Revision:** v2 added the deterministic fields listed above and explicit first-response/category instructions. It retained bounded retries and introduced eight-second inter-ticket pacing for the larger prompt. V2 and the text-only baseline use the **same 30 ticket IDs**, sampled from breaches with seed 42, with unchanged source facts. This is a prompt revision, not model training/fine-tuning.

Original v1/pre-v2 classification and review files were preserved under `experiments/ai_v1/` rather than mixed into the final `output/` folder. The archived `ai_human_eval_30.csv` remains the old blank-label review file. A separate `output/ai_human_eval_30_v2.csv` was created, then filled with **assistant-generated** review labels. No independent human labels were collected. No improvement in independent classification accuracy is claimed from the category shift or the new context.

## 4. Current v2 result: processing and consistency are different measures

### Operational processing

- Sample: **30** confirmed breach tickets.
- Successful classifications: **30**.
- Final API/errors: **0/30 (0.00%)**.

V2's zero final API errors demonstrate successful processing, not classification accuracy. Bounded retries can still fail on a future run.

### Agreement with supplied review labels

| Metric | Verified result |
| --- | ---: |
| Reviewed sample | 30 |
| Agreement | 30/30 |
| Agreement rate | 100.00% |
| Disagreements | 0 |
| Disagreement rate | 0.00% |
| Disagreement categories | None observed against these labels |

**30/30 agreement with assistant-generated review labels. This is evidence of consistency on the reviewed sample, not an independent or generalizable model accuracy estimate.**

Despite its historical name, the `human_reason` column contains assistant-generated labels. Every note begins `Assistant-reviewed:`. The assistant inspected the row evidence and deterministic context, applied the stated first-response rules, and then computed exact equality against `ai_reason`; this is not an independent annotator or a blinded human validation study. Prior involvement in developing the prompt is another source of dependence. No disagreement example is invented when none exists in this review.

| Review label | Count |
| --- | ---: |
| `overnight_queue_or_handoff` | 20 |
| `unclear_or_other` | 10 |

The sample contains only two of the seven categories. It cannot establish category-wide performance, population accuracy or reliability of the other five categories. The 20 overnight explanations remain hypotheses; some model evidence phrases overstate certainty about next-shift staffing. Review notes flag ambiguous transfer timing and the distinction between a customer issue and a response-delay cause.

## 5. Reliability handling

`src/ai_reasons.py` uses:

- At most three 429 retries with **2 → 4 → 8 second** backoff. A numeric provider `Retry-After` can increase a delay, capped at 60 seconds.
- **One** stricter-prompt retry for provider JSON-generation/validation errors or locally invalid JSON/schema. Validation checks exact fields, taxonomy membership, numeric confidence in [0, 1] and nonempty evidence.
- Shared per-ticket budgets: at most five API attempts when errors are mixed. SDK automatic retries are disabled; each request has a 60-second timeout. Unrelated failures are not retried indefinitely.
- A compact context whitelist and **eight-second inter-ticket pacing** by default, reducing pressure on the 8,000 TPM limit without promising quota availability.
- Final-error recording in `ai_error`, with blank classification fields if a ticket still fails. Failed rows are processing failures, not reason-classification disagreements.
- Output overwrite protection so an experiment is not silently replaced.

## 6. Reproduce the stored evaluation without calling Groq

From the project root after installing `requirements.txt`:

```bash
./.venv/bin/python src/evaluate_ai.py \
  --file output/ai_human_eval_30_v2.csv
```

The evaluator reports sample size, agreement/disagreement rates, common disagreement pairs and a confusion matrix (review-label rows, AI-label columns). It writes `yes`/`no` into `agreement`; its `Errors` field means **label disagreements**, not independently established model mistakes. It now prints the assistant-label provenance when present. Blank labels are excluded, partial reviews are identified, and invalid labels/duplicate ticket IDs are rejected.

The stored review has 16 columns:

```text
ticket_id,customer_message,agent_notes,channel,response_minutes,sla_minutes,
created_shift,overnight_created,transfers,assigned_team,ai_reason,ai_confidence,
ai_evidence,human_reason,agreement,review_notes
```

The existing sampler selects successful unique tickets only, uses seed 42 and approximately proportional category allocation, and reserves at least one case per available category when size permits. In this v2 run exactly 30 successes were available, so all 30 are included. It cannot manufacture coverage of missing categories and refuses to create a 30-case file from fewer than 30 successes.

See `README.md` for the exact historical Groq command and safe instructions for a deliberate new experiment. **Do not regenerate the submitted sample simply to score it.** Fresh samples start with blank review fields; scoring stored labels does not call the API. Both original and context-rich review schemas are supported.

For independent validation, an actual human reviewer should assess the text and deterministic facts without seeing model predictions or assistant review notes, in a separately preserved review file. That independent study has not been performed here.

## 7. Limitations and cost

- Assistant-generated labels are not independent human validation; agreement does not measure generalizable accuracy. The review is small, breach-only and concentrated in two categories.
- Operational context supports hypotheses, not exact staffing, queue load, transfer chronology or causation. The June reshuffle is not a demonstrated cause. Resolving-agent attribution is not evidence of individual fault.
- Sparse notes and the approximately 40 failed IVR transcripts reported in the supplied email limit qualitative analysis, especially for voice. Transfer-field provenance differs between policy and legacy export values.
- Confidence is uncalibrated; temperature 0 and a fixed sampling seed do not guarantee identical future API responses. Category overlap and prompt/provider changes can affect results.
- Network/quota failures and repeatedly invalid/truncated output remain possible. Successful processing is not proof of a correct reason.
- Ticket text/context sent to Groq can contain customer/agent details; production use would require appropriate approval, redaction and data-handling controls.
- **API cost was not separately instrumented in this run, so no precise per-ticket cost is claimed.** No measured monthly cost is available. Deterministic analysis and stored-label scoring require no LLM calls; classification is optional.

## 8. Offline checks

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

The **39-test** suite checks retry budgets, schema validation, context preservation, output protection, final-error recording, successful-only sampling, review provenance, old/new CSV compatibility, partial reviews and deterministic totals/date boundaries. It also checks the required `output/weekly_agent_shift_breaches.csv` aggregation against existing weekly/shift/Tier-1 totals and all-agent audit facts, the observed-volume planning scenario, and dashboard loading/filter behavior without API calls. Tests use mocked API calls, not live Groq requests. The final report/scenario correction did not rerun classification, change AI outputs or relabel any review cases. Tests are regression evidence for the implemented rules, not a claim that every historical business assumption is proven. See `DECISIONS.md` for those assumptions.
