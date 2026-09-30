# Vireo Audio — First-response SLA breach analysis

A small Python/pandas submission for the requested **weekly breach report by agent and shift**, with an optional Groq classification layer. Start with [submission-form.md](submission-form.md) for findings and limitations, [DECISIONS.md](DECISIONS.md) for business-rule choices, and [AI_EVALUATION.md](AI_EVALUATION.md) for experiment provenance.

## Verified findings

The supplied export covers ticket creation from **1 January 2025 to 30 June 2026 (IST)**. Deduplication reduces 11,816 source rows to **11,200 unique tickets**:

| Metric | Result |
| --- | ---: |
| First-response breaches | 2,440 |
| Overall breach rate | 21.7857% |
| Estimated SLA credits at ₹350 per breach | ₹854,000 |
| Overnight-created tickets | 2,486 |
| Overnight-created breaches | 1,631 |
| Overnight-created breach rate | 65.6074% |
| Overnight-created share of all breaches | 66.8443% |

**Overnight-created tickets are strongly associated with breaches in this dataset.** Policy permits next-shift queue pickup outside a team's staffed hours, but exact handoff timing is not observed. Neither overnight creation nor the June reshuffle establishes causation. Credits are policy-based estimates, not a reconciliation to actual issued credits or P&L.

**Required client deliverable:** `output/weekly_agent_shift_breaches.csv` now directly provides the weekly breach report by agent and shift. Added in this final correction, it contains **2,917 rows**, **79 reporting-week labels** and **44 agents**, reusing the established ticket-level facts, IST weeks and time-bounded roster assignments. Existing overall/all-period reports remain unchanged. See the column definitions below.

### Proposed planning scenario using observed volume

A proposed planning scenario is to reduce the breach rate from 21.79% to 15%. At the observed average volume of approximately **143.6 tickets/week**, this corresponds to roughly **9.7 fewer breaches/week** and **₹44,333.33 (approximately ₹44,000)** in avoided SLA credits over a 13-week quarter, assuming volume remains similar. **The 15% figure is a proposed planning scenario, not a target supplied by Vireo, and the resulting financial impact is conditional on maintaining the observed ticket volume—not a guaranteed saving.**

`src/analyze.py` calculates and prints this scenario from the audit facts: inclusive IST coverage is **546 days / 7 = 78 week-equivalents**, so weekly volume is `11,200 / 78 = 143.589744`. The 79 reporting labels include partial edge weeks; counting them as 79 full weeks would use the wrong denominator. The calculation uses unrounded volume and breach rate: `(2,440 / 11,200 − 0.15) × (11,200 / 78) × ₹350 × 13 = ₹44,333.33`.

## 1. Environment setup

Run commands from the extracted project root in a POSIX shell. Use Python **3.9–3.12**; the pinned environment was verified on Python 3.9.6. Python 3.13+ is not covered by the pinned NumPy version. Internet access is needed to install dependencies; deterministic execution and scoring stored labels do not need an API key.

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pip check
```

Direct dependencies are pinned to the versions used for the submitted artifacts. Transitive dependencies are resolved by pip, not fully locked. A fresh virtual environment installed these requirements successfully, passed `pip check` and the offline test suite. `streamlit` is used only for the optional evaluator-facing dashboard; it is not involved in the numerical or AI pipeline.

## 2. Reproduce deterministic analysis and tests — no LLM calls

```bash
./.venv/bin/python src/analyze.py
./.venv/bin/python -m unittest discover -s tests -v
```

The analysis generates the weekly agent/shift CSV alongside the seven other deterministic CSVs, whose contents remain unchanged, and prints the observed-volume planning scenario. The regression suite also runs the analyzer. Expected totals are the table above; the suite contains **39 tests**, including dashboard loading/filter checks, row-level aggregation, reconciliation to existing weekly/shift/Tier-1 totals and all-agent audit totals, scenario arithmetic, date boundaries, context preservation, retry limits, evaluation provenance and overwrite protection.

## 3. Score the stored v2 review — no LLM calls

```bash
./.venv/bin/python src/evaluate_ai.py \
  --file output/ai_human_eval_30_v2.csv
```

Expected: **30/30 agreement with assistant-generated review labels**, 100.00% agreement, 0 disagreements and 0.00% disagreement rate. **This is evidence of consistency on the reviewed sample, not an independent or generalizable model accuracy estimate.** The legacy `human_reason` column contains assistant-generated labels, identified by `Assistant-reviewed:` in every review note. The evaluator's `Errors` field means label disagreements.

The 30 cases contain 20 `overnight_queue_or_handoff` and 10 `unclear_or_other` labels, so this does not establish performance across all seven categories. Independent human validation remains outstanding. Scoring recalculates `agreement` and preserves the ticket evidence, AI outputs and review notes; it does not invoke Groq.

## 4. Optional AI classification — not needed to inspect this submission

```text
Raw tickets → deterministic SLA/roster/shift facts → LLM interpretation → likely breach reason
```

**Deterministic code remains the source of truth for SLA, breach, shift, roster, and financial calculations. The LLM is used only for qualitative interpretation of likely breach causes.**

The model is **`openai/gpt-oss-20b`**, accessed through **Groq's OpenAI-compatible endpoint** (`https://api.groq.com/openai/v1`). Configure `GROQ_API_KEY` privately in the process environment using your normal secret-management workflow. The scripts do not load `.env` files, and no API key belongs in source control or the submission ZIP.

The exact command used for the stored v2 experiment was:

```bash
export GROQ_MODEL="openai/gpt-oss-20b"
./.venv/bin/python -u src/ai_reasons.py --sample 30 \
  --output output/ai_reason_sample_v2.csv
```

**Do not rerun this merely to evaluate the submission:** v2 results are included, and the command deliberately refuses to overwrite them. For a deliberate new experiment, use a new output path, for example `--output output/ai_reason_sample_recheck.csv`. The default sample size without `--sample` is 120; the submitted v2 run explicitly used 30. Always specify the intended output path.

V2 sends a compact whitelist of existing facts (`channel`, `response_minutes`, `sla_minutes`, `created_shift`, `overnight_created`, `transfers`, `assigned_team`, `priority`, `category`, `source_system`, `agent_id`, `team`) plus `customer_message` and `agent_notes`. It classifies the first-response delay, not the customer's product/payment problem. It uses bounded 429/JSON retries, records final failures, and pauses eight seconds between tickets by default.

If intentionally reviewing that new experiment, the existing sampler can create a separate blank review:

```bash
./.venv/bin/python src/evaluate_ai.py --create-sample \
  --source output/ai_reason_sample_recheck.csv \
  --file output/ai_human_eval_30_recheck.csv
```

This command needs 30 successful unique classifications and refuses to overwrite an existing review. It creates blank `human_reason`, `agreement` and `review_notes` fields. An independent reviewer should fill `human_reason` using the taxonomy in `AI_EVALUATION.md`, optionally add notes, then score that file with `--file`. Do not relabel the stored assistant-generated review as independent human evidence.

## Expected artifacts

| File under `output/` | Contents |
| --- | --- |
| `overall.csv` | Dataset-wide totals and overnight metrics |
| `weekly_summary.csv` | Overall creation-week totals; partial edge weeks clipped to data coverage |
| `weekly_agent_shift_breaches.csv` | Required weekly report by resolving agent and roster shift; 2,917 nonempty groups, all tiers included for complete accounting |
| `shift_summary.csv` | All-period resolving-assignment shift counts/rates, not creation-shift counts |
| `agent_summary_tier1.csv` | All-period agent/site/team/shift counts and rates; Tier 2 excluded from this comparison |
| `channel_summary.csv` | All-period channel totals |
| `overnight_summary.csv` | Separate creation-time overnight diagnostic |
| `ticket_audit.csv` | 11,200 deduplicated tickets and derived facts, including roster dates |
| `ai_reason_sample_v2.csv` | Context-aware 30-case run: 30 successful, 0 final API errors |
| `ai_human_eval_30_v2.csv` | Context-rich 30-case assistant-reviewed consistency check |

The earlier v1/pre-v2 experiments are preserved under `experiments/ai_v1/`: the historical 120-case run, the text-only baseline and its blank review file. They are archived there to keep the final `output/` folder focused on evaluator-facing artifacts while retaining the v1-to-v2 evidence. See `AI_EVALUATION.md` for provenance and interpretation.

### Weekly agent/shift report columns

`output/weekly_agent_shift_breaches.csv` has exactly these columns:

| Column | Meaning |
| --- | --- |
| `week` | Existing inclusive IST **creation-week** label, with partial edge weeks clipped to coverage |
| `agent_id` | Existing resolving-agent identifier |
| `agent_name` | Name from the time-bounded roster match (`name` in the audit) |
| `shift` | Matched resolving-assignment shift: Morning, Day or Night; not creation shift |
| `ticket_count` | Unique tickets created in that week and attributed to this agent/shift, not necessarily resolved that week |
| `breach_count` | Sum of existing first-response breach flags for those tickets |
| `breach_rate` | `breach_count / ticket_count`, stored as a fraction, not a percentage string |
| `sla_credits` | Sum of existing estimated SLA credits in INR; `breach_count × ₹350` |

Only groups containing tickets are written; absent combinations are not zero-filled. The report is ordered by grouping keys, not performance. Tier 2 is included so totals reconcile to the full dataset; this is not a Tier-2 versus Tier-1 volume comparison. The existing Tier-1 report remains filtered. Tests reconcile all **79 weekly groups**, **46 all-period agent/shift contexts**, **40 Tier-1 contexts** and **three shift totals**. Rates are recomputed from summed counts, not averaged across rows.

For assignment periods, tier/site/team changes and overnight-created queue context, read the corresponding `ticket_audit.csv` rows using week, agent and shift. The report does not replace that context or establish individual culpability.

All source CSVs, `data/support-policy.pdf` and `data/email-thread.txt` are included. Orders/customers/products are deliberately not primary inputs to first-response SLA determination.

Read agent counts/rates together with volume, assignment periods in the audit, shift and overnight-queue context. They are **not standalone performance rankings**. Roster shifts describe the resolving assignment; creation shifts describe arrival time. Weeks remain Tuesday–Monday in IST, with partial first/last labels clipped to observed dates.

## Evaluator dashboard

Launch the read-only dashboard from the project root:

```bash
./.venv/bin/streamlit run app.py
```

The dashboard reads the submitted CSVs from `output/`; it does not call an LLM or calculate SLA rules. The deterministic `src/analyze.py` pipeline is the source of truth for breach detection, shift and roster attribution, credits and aggregation. Run that analysis first if you need to regenerate its outputs. The dashboard displays executive KPIs, filtered weekly trends and the weekly agent/shift report, overnight context, and AI-assisted reason examples. It requires no API key.

The workflow is: (1) run `./.venv/bin/python src/analyze.py`, (2) optionally generate a qualitative classification sample with `src/ai_reasons.py`, (3) score the stored evaluation with `src/evaluate_ai.py`, and (4) launch `./.venv/bin/streamlit run app.py`. Steps 1, 3 and 4 do not call Groq. See the AI section above for the exact optional classifier command and output protection.

The stored review currently reports 30/30 agreement with assistant-generated review labels. This is not an independent model-accuracy estimate; the labels are identified as assistant-reviewed in the evaluation CSV.

## Packaging

To package only submission material, run from the project root:

```bash
zip -r vireo_sla_submission.zip README.md DECISIONS.md AI_EVALUATION.md \
  submission-form.md requirements.txt app.py src tests data output \
  -x '*/__pycache__/*' '*.pyc'
```

Do not include `.venv`, `.env` files, `__agent__`, temporary QA environments or credentials. ZIP delivery does not create a public Drive/GitHub URL; if the submission portal requires one, the owner must publish the artifact and supply the real URL.
