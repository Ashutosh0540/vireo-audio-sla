# Engineering and reporting decisions

## Source of truth and scope

**Deterministic code remains the source of truth for SLA, breach, shift, roster, and financial calculations. The LLM is used only for qualitative interpretation of likely breach causes.** It receives existing operational facts plus customer/agent text; it must not recalculate compliance or treat the customer's problem as the breach cause.

The source material available locally is `data/support-policy.pdf` (v3.2, effective 1 April 2025), the short `data/email-thread.txt`, and five CSVs. No additional source assignment README or full stakeholder email exchange is present. The local email specifies weekly reporting by agent and shift, UTC exports, time-bounded rosters, migration duplicates, roughly 40 failed IVR transcripts, frozen headcount until Q4 and a reportedly cost-neutral June Indore reshuffle.

I kept the requested weekly breach report by agent and shift as the scope. The final correction adds **`output/weekly_agent_shift_breaches.csv`**, directly delivering that report with **2,917 rows across 79 week labels and 44 agents**. This aggregation was added at this stage; it is not claimed as a pre-existing deliverable. It reads the already-calculated ticket facts after the existing time-bounded roster match and does not change the prior calculations or CSV contents.

## Implemented deterministic rules — unchanged

- **Deduplication:** prefer `helpdesk` over `legacy_fd` for a repeated `ticket_id`. The supplied 11,816 rows become 11,200 unique tickets: 616 repeated rows are removed. Source conflicts are not separately reconciled against a ledger.
- **Time:** parse ticket timestamps as UTC, as specified in the local email/API export context. Convert creation time to `Asia/Kolkata` for shift/week analysis. Response duration remains elapsed time from creation to first human response; no business-hours clock is introduced.
- **Targets:** chat 15 minutes, voice callback 120, social 240, email 480 (policy §3). Breach means a recorded first response strictly later than the channel target. Equality is not a breach. The supplied audit has no missing first responses; in future data the current implementation would not mark a missing response as a breach.
- **Policy-period assumption:** the same supplied targets and ₹350 credit are applied across the export, including 1,024 tickets created before the policy's 1 April 2025 effective date. No earlier policy is supplied, so historical rule equivalence is an assumption, not a verified fact.
- **Financial exposure:** `breaches × ₹350` estimates SLA credits. The policy issues credits on resolution; the calculation includes 120 breaches on tickets still open/pending. ₹854,000 is therefore estimated exposure, not confirmed issued credits or booked P&L. Actual refund amounts, transfers and other cost standards are not added to this figure.
- **Attribution:** policy §3 attributes breaches to the resolving `agent_id`, not necessarily the first responder. `assigned_team` is the first-assigned team (policy §9); roster `team` describes the resolving assignment.
- **Roster:** match `agent_id` against inclusive assignment dates using the IST resolution date, falling back to the IST creation date when resolution is absent (589 tickets). Blank roster bounds are treated as open-ended. When multiple matches exist, the shortest assignment span wins. Unmatched tickets would be dropped by the current join; all 11,200 unique IDs are retained in this dataset.
- **Shift:** Morning 06:00–14:00, Day 14:00–22:00, Night 22:00–06:00 IST (policy §7). `shift_summary.csv` uses the matched roster shift. `created_shift` and `overnight_created` refer to ticket arrival, not resolving-agent shift. In particular, 268 tickets attributed to Night agents is not the same metric as 2,486 overnight-created tickets.
- **Weeks:** retain Tuesday–Monday periods (`W-MON` means ending Monday). Group by creation week, not resolution week. Clip inclusive first/last labels to the observed IST date coverage: `2025-01-01/2025-01-06` and `2026-06-30/2026-06-30`. These are partial weeks, not full-week comparisons. Timezone removal occurs only on a temporary IST calendar-date series before period conversion; underlying dates and response calculations are untouched.
- **Tier 2:** exclude Tier 2 from the Tier-1 agent-volume comparison because policy §6 explicitly says not to compare Tier 2 with Tier 1 on volume. Tier 2 remains in overall, weekly, shift and channel totals, the audit and the new weekly agent/shift accounting report. Complete accounting is not a cross-tier performance comparison.

## Weekly agent/shift aggregation added in the final correction

Group the existing ticket facts by `week`, `agent_id`, roster `name` and roster `shift`. Rename `name` to `agent_name`; count ticket IDs, sum existing breach flags and sum existing `sla_credit_inr`. The rate is the group's breached fraction. The eight columns are `week`, `agent_id`, `agent_name`, `shift`, `ticket_count`, `breach_count`, `breach_rate`, `sla_credits` (INR). Only observed, nonempty groups appear, ordered by grouping keys rather than breach rate.

The week is still creation week; the shift still comes from the assignment matched at resolution, or creation when resolution is missing. No SLA, timestamp or roster selection is recalculated for this aggregation. It counts tickets attributed to the agent, not tickets necessarily resolved within that week.

Reconciliation checks establish valid week/agent/shift keys, unique report groups, `breach_count <= ticket_count`, rate arithmetic and `sla_credits = breach_count × ₹350`. Summing reproduces all 79 existing weekly totals, all three shift totals, all 46 agent/shift contexts in the audit, and all 40 contexts in the existing Tier-1 summary after applying its tier scope. Rates in reconciled summaries are calculated from total breaches/total tickets, not an average of row rates. The report includes all 11,200 tickets, 2,440 breaches and ₹854,000 in estimated credits.

## Agent interpretation and overnight diagnostic

Agent-level breach counts and rates are presented with ticket volume and shift; the audit supplies assignment periods and overnight-queue context. **They should not be interpreted as standalone performance rankings.** Summary rows omit explicit assignment dates; the weekly report can combine assignments sharing the same week/agent/name/shift, and the all-period report can combine matching agent/site/team/shift contexts. Use the audit for period-sensitive interpretation. Agents can change shifts/sites, and the next staffed shift may inherit overnight demand.

**Overnight-created tickets are strongly associated with breaches in this dataset:** 1,631 of 2,486 breached (65.6074%), accounting for 66.8443% of all breaches. Policy §7 says coverage outside a team's staffed hours is picked up by the next shift in creation order. That supports a likely queue/handoff explanation, not proof of exact handoff timing. Policy §2 also specifies 24×7 chat with Indore night coverage: it would be wrong to assume every overnight ticket had no available staff.

The observed Morning assignment totals and the reported June reshuffle do not establish individual fault or causal effects of staffing changes. No causal intervention or counterfactual is measured.

## Proposed management scenario — not a Vireo target

A **proposed planning scenario**, not a target supplied by Vireo, is to reduce the overall breach rate from 21.79% to 15%. At the **observed average volume of approximately 143.6 tickets/week**, this corresponds to roughly **9.7 fewer breaches/week** and **₹44,333.33 (approximately ₹44,000) of avoided SLA credits over a 13-week quarter**, assuming volume remains similar.

`src/analyze.py` computes and prints the following from existing ticket facts, without rounding inputs before calculating financial impact:

```text
Inclusive IST calendar coverage = 546 days
Week-equivalents = 546 / 7 = 78
Observed volume = 11,200 / 78 = 143.589743589744 tickets/week
Current breach rate = 2,440 / 11,200 = 21.785714285714%
Fewer breaches/week = (2,440 / 11,200 − 0.15) × (11,200 / 78)
                   = 9.743589743590
Quarterly avoided credits = fewer breaches/week × ₹350 × 13
                          = ₹44,333.33 (rounded to paise)
```

The report contains 79 week labels because the first and last bins are partial, but the coverage is 78 full-week equivalents. Using 79 as the volume denominator would be incorrect for this scenario. The 15% figure is a proposed planning scenario, not a target supplied by Vireo, and the financial impact is conditional on maintaining the observed ticket volume. It is not a guaranteed saving; no implementation cost, intervention effect or realized ROI is claimed. This replaces the previous hypothetical-volume scenario rather than presenting competing scenarios.

## Deliberately omitted analysis and unresolved evidence

- `orders.csv`, `customers.csv` and `products.csv` are inspected and retained, but are not primary inputs to first-response SLA determination. Product unit costs and order/refund economics belong to a separate analysis, not this credit estimate.
- No CSAT scoring, refund-leakage calculation, repeat-contact model, staffing optimizer, database, RAG or additional LLM framework was added. The source warns that legacy CSAT zero means no response; this submission does not compute CSAT averages.
- Roughly 40 failed IVR transcripts are reported in the supplied email summary, limiting qualitative voice analysis. That count is attributed to the email, not a newly inferred transcript audit.
- The policy says transfer counts exist only in the current helpdesk, while this export contains legacy transfer values too. Their provenance and timing are not validated; a count alone cannot establish a pre-response ownership delay.
- The hardening brief attributes “roughly tripled” SLA credits to Finance and “flat month-on-month” credits to Priya. Neither statement appears in the short local email summary; no historical P&L/credit ledger is supplied. Both remain attributed stakeholder statements, not independently verified or silently reconciled results.
- API cost was not separately instrumented in this run, so no precise per-ticket cost is claimed. Deterministic analysis and scoring stored labels require no LLM calls.
