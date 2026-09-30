# Vireo Audio — Submission form

## What did you build, and what business outcome does it move?

I built an explainable first-response SLA analysis using Python/pandas, ticket-level audit evidence, CSV reports and an optional Groq breach-reason classifier. It deduplicates migration re-imports, interprets UTC/IST correctly, applies channel targets and matches resolving agents to time-bounded roster assignments. The requested **weekly breach report by agent and shift is delivered in `output/weekly_agent_shift_breaches.csv`**: 2,917 rows across 79 reporting-week labels and 44 agents.

The observed business problem is a **21.79% first-response SLA breach rate across 11,200 unique tickets**, corresponding to **₹854,000 in estimated SLA credits at ₹350 per breach**. The exact breach rate is 21.7857%; there are 2,440 breaches. This is policy-based credit exposure, not verified posted credits or a P&L reconciliation.

A **proposed planning scenario** is to reduce the breach rate from 21.79% to 15%. At the **observed average volume of approximately 143.6 tickets/week**, this corresponds to roughly **9.7 fewer breaches per week** and **₹44,333.33 (approximately ₹44,000)** of avoided SLA credits over a 13-week quarter, assuming volume remains similar. **The 15% figure is a proposed planning scenario, not a target supplied by Vireo, and the resulting financial impact is conditional on maintaining the observed ticket volume.** It is not a guaranteed saving and excludes intervention costs.

**Programmatically verified calculation:** `src/analyze.py` uses 546 inclusive IST calendar days / 7 = **78 week-equivalents**, observed volume `11,200 / 78 = 143.589744`, and the unrounded rate `2,440 / 11,200`. Thus `(2,440 / 11,200 − 0.15) × (11,200 / 78) = 9.743590` fewer breaches/week; multiplying by ₹350 and 13 gives **₹44,333.33**. There are 79 reporting labels because edge weeks are partial; they are not 79 full weeks.

## How do you know it works? What was checked, and on how much data?

### Deterministic evidence

The 11,816 input rows contain **11,200 unique ticket IDs**; deduplication removes 616 repeated rows. All 11,200 IDs survive roster matching. Ticket creation covers 1 January 2025 through 30 June 2026 IST. The audit contains no missing first responses or negative response durations. Overall, weekly, shift, channel and overnight totals reconcile to 11,200 tickets, 2,440 breaches and ₹854,000 estimated credits.

| Resolving-assignment shift | Tickets | Breaches | Breach rate |
| --- | ---: | ---: | ---: |
| Day | 4,668 | 393 | 8.419% |
| Morning | 6,264 | 2,018 | 32.216% |
| Night | 268 | 29 | 10.821% |

These are roster-assignment shifts, not creation shifts.

| Channel | Tickets | Breaches | Breach rate |
| --- | ---: | ---: | ---: |
| Chat | 4,959 | 1,368 | 27.586% |
| Email | 3,647 | 745 | 20.428% |
| Social | 1,106 | 243 | 21.971% |
| Voice | 1,488 | 84 | 5.645% |

There are **2,486 overnight-created tickets**, of which **1,631 breached** (65.6074%). They account for **66.8443%, approximately 66.8%, of all breaches**. Overnight-created tickets are strongly associated with breaches in this dataset; that does not establish causation.

Checking method: inspect the policy and export schema, reconcile CSV aggregates to the ticket audit, run the **39-test offline suite**, rerun deterministic analysis and compare SHA-256 hashes with the existing outputs. Tests check every weekly-agent-shift row's keys and arithmetic, reconcile all 79 weekly totals, three all-period shifts, 46 all-agent/shift audit contexts and 40 Tier-1 contexts, verify the observed-volume scenario, and smoke-test the read-only dashboard and filters. The new report sums to 11,200 tickets, 2,440 breaches and ₹854,000. All 12 pre-existing output CSVs remain byte-for-byte unchanged; historical AI experiment CSVs are archived under `experiments/ai_v1/`. Passing regressions are evidence of reproducibility under the implemented assumptions, not proof that all business assumptions are historically correct.

### AI sample, checking method and error types

- **Historical v1/pre-v2 run:** 120 cases, 115 successful, 5 final API/model-processing cases: **4.17% processing/API failure rate**. Four were 429/rate-limit errors; one was JSON validation. These are not established classification errors and are not an accuracy estimate.
- **Later text-only baseline:** 30 cases, 30 successfully processed. It lacks the explicit deterministic operational context supplied in v2. This is distinct from the earlier 120-case error statistic.
- **V2:** 30 cases, 30 successful, **0 final API errors**. Successful processing is not classification accuracy.
- **Stored review:** **30/30 agreement with assistant-generated review labels**; agreement 100.00%, disagreements 0, disagreement rate 0.00%, no observed disagreement categories against those labels. **This is evidence of consistency on the reviewed sample, not an independent or generalizable model accuracy estimate.**

The assistant reviewed first-response evidence and deterministic context; all notes identify `Assistant-reviewed:` provenance. Exact equality between `human_reason` and `ai_reason` determines agreement. The sample contains **20 `overnight_queue_or_handoff` and 10 `unclear_or_other`** cases. It does not establish performance across all seven categories. No independent human validation, generalizable accuracy or invented disagreement example is claimed.

## What does one run cost, and what would a month cost at the observed volume?

**API cost was not separately instrumented in this run, so no precise per-ticket cost is claimed.** The repository has no recorded token-usage/billing ledger from which to calculate a reliable run or monthly price. No monthly extrapolation is fabricated.

Deterministic analysis and scoring stored labels require no LLM calls. AI classification is an optional qualitative layer over sampled breaches. The ₹350 policy credit and the management scenario are business-exposure figures, not API costs. Local compute/hosting costs were also not separately measured.

## Did you change, narrow, or push back on the client's ask?

**I kept and delivered the requested weekly breach report by agent and shift. I narrowed the AI component to qualitative breach-reason classification rather than allowing an LLM to calculate SLA compliance.**

I retained count and rate together and added an overnight diagnostic because policy §7 explicitly states that queue coverage outside a team's staffed hours is picked up by the next shift in order of creation. Policy §3 attributes breaches to the resolving agent, so those agents may inherit delayed demand. The policy also specifies overnight chat coverage; overnight does not automatically mean unstaffed.

**Final deliverable correction:** QA identified that separate weekly-overall and all-period agent/shift summaries did not directly answer the requested cross-tab. I then added `output/weekly_agent_shift_breaches.csv` from the existing ticket facts, without redesigning SLA/roster/week logic or changing prior CSV contents. Its columns are `week`, `agent_id`, `agent_name`, `shift`, `ticket_count`, `breach_count`, `breach_rate` and `sla_credits` (INR). It uses creation week and resolving-assignment shift, counts all attributed tickets rather than only those resolved that week, includes all tiers for accounting completeness and does not rank agents. It was added in this correction, not present in the earlier submission.

Agent-level breach counts and rates must be read with ticket volume, assignment periods, shift and overnight-queue context. They should not be interpreted as standalone performance rankings. Assignment periods and overnight context are in the audit rather than all being repeated in the agent summary.

## What is wrong with what you are handing us? Specific shortcuts and known inaccuracies

1. The 30-case AI review is assistant-generated, not independent human validation, and covers only two of seven categories. Confidence is uncalibrated.
2. Overnight queue/handoff is a likely operational explanation supported by policy and timing, not proof of exact handoff chronology. Transfers, escalation/RMA activity and customer follow-ups may occur after first response. The June reshuffle is not established as a cause.
3. The local email reports approximately 40 failed IVR transcripts, limiting qualitative voice analysis. That is an attributed source count, not a newly validated transcription audit.
4. Migration duplicates exist; deterministic deduplication prefers helpdesk records but does not independently resolve every conflicting source field. The policy limits transfer-count provenance to the current helpdesk, whereas the export also contains legacy values.
5. One policy version is applied across the export, including 1,024 tickets before its 1 April 2025 effective date. No prior policy is supplied to validate historical equivalence.
6. Missing resolution timestamps on 589 tickets use creation date for roster matching. Credits include 120 breaches on open/pending tickets, so ₹854,000 is estimated exposure rather than confirmed issued credits. Unmatched roster cases would be dropped by the current code; none are lost here.
7. The weekly agent/shift report now delivers the requested breakdown, but its compact summary does not repeat assignment dates, tier/site/team or overnight-arrival context. Use the audit for that context, and do not treat partial edge weeks as comparable full weeks.
8. The brief attributes “roughly tripled” credits to Finance and “flat month-on-month” credits to Priya. Neither statement appears in the short local email summary, and historical P&L data are absent. They remain attributed stakeholder statements, not independently verified or silently reconciled findings.
9. The submission is a small batch tool, not a production service. Future data/schema anomalies, API failures, customer-data handling controls and independent review still need attention. Direct dependencies are pinned; transitive dependencies are not fully locked.

## What did you deliberately leave out, and why?

- **Orders/customers/products as primary SLA inputs:** first-response compliance requires ticket timestamps/channel and roster context, not commercial joins. These source files were inspected and retained, not forgotten.
- **Tier-2 versus Tier-1 volume comparison:** policy §6 explicitly prohibits it because Tier-2 cases are multi-touch. Tier 2 is omitted only from the Tier-1 agent comparison; it remains in full-dataset totals and the new weekly agent/shift accounting breakdown. Inclusion for reconciliation is not a cross-tier performance comparison.
- **Refund/replacement leakage, CSAT, repeat-contact economics and staffing optimization:** separate business questions beyond the breach-report scope. In particular, no legacy zero-valued CSAT was silently treated as satisfaction data.
- **Production application features or frameworks:** no database, RAG, agents, authentication or orchestration framework was added. A small read-only Streamlit dashboard presents the submitted CSV artifacts; the CSVs and CLI commands remain the reproducible source of truth.
- **Additional AI reruns:** final hardening reuses the stored experiment and labels rather than spending calls to seek more favorable results.

## Anything you built or found that nobody asked for?

The overnight-created diagnostic distinguishes arrival-time demand from resolving-shift attribution: 1,631 overnight-created breaches account for approximately 66.8% of all breaches. This provides a concrete reason to investigate coverage/queue handoffs before attributing outcomes to individuals. It does not prove a staffing intervention would work or override the email's frozen-headcount constraint.

The audit trail, bounded API retries, experiment overwrite protection, separate v1/v2 artifacts and regression checks make the small tool easier to inspect and reproduce. Weekly edge labels were previously clipped to avoid implying July coverage beyond the dataset's final creation date; no SLA facts were changed by that correction.

## What AI tools/models did you use, and where did AI help?

- **Runtime classifier:** `openai/gpt-oss-20b` through Groq's OpenAI-compatible API using the OpenAI Python SDK. Credentials/model selection come from `GROQ_API_KEY` and `GROQ_MODEL`.
- **Coding/review assistance:** the omnirush coding assistant helped inspect code, implement reliability and evaluation support, write tests/documentation and generate the explicitly marked review labels. A separate coding-assistant model/version and its billing are not recorded in the submission artifacts, so no precise claim is made about them.
- **Useful role:** interpreting inconsistent free-text notes in the context of precomputed operational facts, and helping build/check a transparent implementation. The resulting labels remain qualitative hypotheses.

## Where was AI unnecessary or wasted? What work was discarded or revised?

AI was unnecessary for SLA arithmetic, deduplication, timezone conversion, roster matching, grouping or credit calculations; deterministic code handles those tasks. The text-only prompt was an inadequate final approach because it omitted SLA/shift context and could confuse the customer problem with the breach cause. A successful API response alone was also not a sufficient evaluation method.

The historical 120-case run had four 429 errors and one JSON-validation failure. A later text-only 30-case baseline processed successfully but lacked operational evidence. V2 added `channel`, `response_minutes`, `sla_minutes`, `created_shift`, `overnight_created`, `transfers`, `assigned_team`, `priority`, `category`, `source_system`, `agent_id` and `team`, alongside the text. It uses bounded JSON retries, 429 exponential backoff, final-error recording and eight-second inter-ticket pacing.

The earlier prompts were superseded, not erased; all three classification files and both review files are retained. This was prompt iteration, not retraining. The 120-case prompt had some basic metadata, so its 5/120 failure statistic must not be misattributed to the later strictly text-only 30-case run. No quantitative accuracy improvement is claimed.

## Someone picks this up on Monday: the three things they need to know

1. **Run the numerical layer first and read its assumptions.** `src/analyze.py` generates `output/weekly_agent_shift_breaches.csv` and prints the observed-volume scenario; `DECISIONS.md` explains compliance, attribution and estimated exposure. Do not mix resolving-agent shift with arrival shift or treat the agent report as a standalone ranking.
2. **The stored AI review is a consistency check, not human ground truth.** Inspect `AI_EVALUATION.md`; use the explicit v2 path when scoring. Preserve original experiment files and seek independent review before making stronger claims.
3. **Reproduce without an API key first.** Follow the commands below. Groq is optional, costs are unmeasured, and existing output paths are overwrite-protected. Validate exact handoff timing and business-volume assumptions before using the scenario for a decision.

## Reproduction instructions

From the extracted project root with Python 3.9–3.12:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python src/analyze.py
./.venv/bin/python -m unittest discover -s tests -v
./.venv/bin/python src/evaluate_ai.py --file output/ai_human_eval_30_v2.csv
./.venv/bin/streamlit run app.py
```

The deterministic analysis, tests, stored-label scoring and dashboard do not call Groq. The tests regenerate deterministic outputs. The dashboard reads existing CSV outputs and requires no API key. `README.md` lists expected files, the optional historical AI command and safe packaging instructions. All submitted results can be inspected without rerunning the classifier.

## Public Google Drive link

No public Drive URL has been created or supplied in this local project. The deliverable is the project folder, packageable as a ZIP using `README.md`. If the receiving portal requires a public link, the owner must upload the actual artifact and provide its real URL; no link is fabricated here.

## Honest hours spent

Actual working time was not reliably recorded in the project, so a precise hour total cannot be substantiated. The five-hour description is the intended exercise scope, not a measured time claim.

## GitHub repository link

No GitHub URL is supplied, and this directory is not a Git checkout. The included source, tests, data and output files constitute the reproducible local submission; no repository URL is invented.
