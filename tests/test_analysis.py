"""Regression checks for the supplied dataset; no API calls."""

from pathlib import Path
import subprocess
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis_run = subprocess.run(
            [sys.executable, str(ROOT / "src" / "analyze.py")],
            capture_output=True, text=True, check=True,
        )
        cls.audit = pd.read_csv(ROOT / "output" / "ticket_audit.csv")
        cls.weekly = pd.read_csv(ROOT / "output" / "weekly_summary.csv")
        cls.weekly_agent_shift = pd.read_csv(ROOT / "output" / "weekly_agent_shift_breaches.csv")
        cls.report = cls.weekly_agent_shift.rename(columns={
            "agent_name": "name", "ticket_count": "tickets",
            "breach_count": "breaches", "sla_credits": "credits_inr",
        })

    def aggregate_report(self, keys, report=None):
        if report is None:
            report = self.report
        totals = report.groupby(keys, as_index=False)[["tickets", "breaches", "credits_inr"]].sum()
        totals["breach_rate"] = totals.breaches / totals.tickets
        return totals

    def test_core_totals(self):
        t = self.audit
        self.assertEqual(len(t), 11200)
        self.assertEqual(t.ticket_id.nunique(), 11200)
        self.assertEqual(int(t.breach.sum()), 2440)
        self.assertAlmostEqual(t.breach.mean(), 2440 / 11200)
        self.assertEqual(int(t.sla_credit_inr.sum()), 854000)

    def test_overnight_totals(self):
        overnight = self.audit.loc[self.audit.overnight_created]
        self.assertEqual(len(overnight), 2486)
        self.assertEqual(int(overnight.breach.sum()), 1631)
        self.assertAlmostEqual(overnight.breach.mean(), 1631 / 2486)
        self.assertAlmostEqual(overnight.breach.sum() / self.audit.breach.sum(), 1631 / 2440)

    def test_week_ranges_are_clipped_and_include_every_ticket(self):
        dates = pd.to_datetime(self.audit.created_at, utc=True).dt.tz_convert("Asia/Kolkata").dt.strftime("%Y-%m-%d")
        bounds = self.audit.week.str.split("/", expand=True)
        self.assertTrue((bounds[0] <= dates).all())
        self.assertTrue((bounds[1] >= dates).all())
        self.assertTrue((bounds[0] >= dates.min()).all())
        self.assertTrue((bounds[1] <= dates.max()).all())
        self.assertEqual(self.weekly.iloc[0].week, "2025-01-01/2025-01-06")
        self.assertEqual(self.weekly.iloc[-1].week, "2026-06-30/2026-06-30")
        self.assertEqual(self.weekly.tickets.sum(), 11200)
        self.assertEqual(self.weekly.breaches.sum(), 2440)
        self.assertEqual(self.weekly.credits_inr.sum(), 854000)

    def test_weekly_agent_shift_schema_and_keys(self):
        report = self.weekly_agent_shift
        self.assertEqual(list(report.columns), [
            "week", "agent_id", "agent_name", "shift", "ticket_count",
            "breach_count", "breach_rate", "sla_credits",
        ])
        self.assertFalse(report.isna().any().any())
        self.assertTrue(report.week.str.fullmatch(r"\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}").all())
        bounds = report.week.str.split("/", expand=True)
        self.assertTrue((pd.to_datetime(bounds[0]) <= pd.to_datetime(bounds[1])).all())
        self.assertEqual(set(report.week), set(self.weekly.week))
        self.assertTrue(report["shift"].isin(["Morning", "Day", "Night"]).all())
        self.assertFalse(report.duplicated(["week", "agent_id", "shift"]).any())
        roster = pd.read_csv(ROOT / "data" / "agents.csv")
        valid_assignments = set(roster[["agent_id", "name", "shift"]].itertuples(index=False, name=None))
        actual_assignments = set(self.report[["agent_id", "name", "shift"]].itertuples(index=False, name=None))
        self.assertTrue(actual_assignments <= valid_assignments)

    def test_weekly_agent_shift_row_arithmetic(self):
        report = self.weekly_agent_shift
        self.assertTrue(report.ticket_count.gt(0).all())
        self.assertTrue(report.breach_count.ge(0).all())
        self.assertTrue(report.breach_count.le(report.ticket_count).all())
        self.assertTrue(report.ticket_count.mod(1).eq(0).all())
        self.assertTrue(report.breach_count.mod(1).eq(0).all())
        pd.testing.assert_series_equal(
            report.breach_rate, report.breach_count / report.ticket_count,
            check_names=False, rtol=1e-12, atol=1e-12,
        )
        pd.testing.assert_series_equal(report.sla_credits, report.breach_count * 350, check_names=False)

    def test_weekly_agent_shift_matches_ticket_audit_facts(self):
        keys = ["week", "agent_id", "name", "shift"]
        expected = self.audit.groupby(keys, as_index=False).agg(
            tickets=("ticket_id", "count"), breaches=("breach", "sum"),
            credits_inr=("sla_credit_inr", "sum"),
        )
        expected["breach_rate"] = expected.breaches / expected.tickets
        actual = self.report.sort_values(keys).reset_index(drop=True)
        pd.testing.assert_frame_equal(actual[expected.columns], expected, rtol=1e-12, atol=1e-12)

    def test_weekly_agent_shift_reconciles_existing_weekly_totals(self):
        actual = self.aggregate_report(["week"])
        pd.testing.assert_frame_equal(actual, self.weekly, rtol=1e-12, atol=1e-12)

    def test_weekly_agent_shift_reconciles_all_agent_shift_totals(self):
        keys = ["agent_id", "name", "shift"]
        expected = self.audit.groupby(keys, as_index=False).agg(
            tickets=("ticket_id", "count"), breaches=("breach", "sum"),
            credits_inr=("sla_credit_inr", "sum"),
        )
        expected["breach_rate"] = expected.breaches / expected.tickets
        pd.testing.assert_frame_equal(self.aggregate_report(keys), expected, rtol=1e-12, atol=1e-12)
        self.assertEqual(int(self.report.tickets.sum()), 11200)
        self.assertEqual(int(self.report.breaches.sum()), 2440)
        self.assertEqual(int(self.report.credits_inr.sum()), 854000)

    def test_weekly_agent_shift_reconciles_existing_tier1_totals(self):
        keys = ["agent_id", "name", "shift"]
        contexts = self.audit[keys + ["tier"]].drop_duplicates()
        # This supplied dataset has one tier per agent/name/shift context.
        self.assertFalse(contexts.duplicated(keys).any())
        tier1_contexts = contexts.loc[~contexts.tier.astype(str).str.contains("2"), keys]
        tier1_report = self.report.merge(tier1_contexts, on=keys, validate="many_to_one")
        existing = pd.read_csv(ROOT / "output" / "agent_summary_tier1.csv")
        expected = self.aggregate_report(keys, existing)
        actual = self.aggregate_report(keys, tier1_report)
        pd.testing.assert_frame_equal(actual, expected, rtol=1e-12, atol=1e-12)

    def test_weekly_agent_shift_reconciles_existing_shift_totals(self):
        existing = pd.read_csv(ROOT / "output" / "shift_summary.csv")
        pd.testing.assert_frame_equal(self.aggregate_report(["shift"]), existing, rtol=1e-12, atol=1e-12)

    def test_planning_scenario_uses_observed_calendar_coverage(self):
        dates = pd.to_datetime(self.audit.created_at, utc=True).dt.tz_convert("Asia/Kolkata").dt.normalize()
        weeks = ((dates.max() - dates.min()).days + 1) / 7
        self.assertEqual(weeks, 78)
        self.assertEqual(len(self.weekly), 79)  # Partial edge bins are not 79 full weeks.
        output = self.analysis_run.stdout
        values = dict(line.split(": ", 1) for line in output.splitlines() if ": " in line)
        self.assertAlmostEqual(float(values["Observed tickets/week"]), len(self.audit) / weeks, places=5)
        expected_fewer = (int(self.audit.breach.sum()) - 0.15 * len(self.audit)) / weeks
        self.assertAlmostEqual(float(values["Fewer breaches/week at unchanged volume"]), expected_fewer, places=5)
        self.assertAlmostEqual(float(values["Avoided SLA credits over 13 weeks (INR)"]), expected_fewer * 350 * 13, places=2)
        self.assertIn("Proposed breach rate: 15.00%", output)
        self.assertIn("not a Vireo target; conditional, not guaranteed savings", output)

    def test_no_timezone_conversion_warning(self):
        self.assertNotIn("timezone", self.analysis_run.stderr.lower())


if __name__ == "__main__":
    unittest.main()
