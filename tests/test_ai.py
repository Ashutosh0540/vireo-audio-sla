"""Offline checks: run with python3 -m unittest discover -s tests -v."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import BadRequestError, RateLimitError
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import ai_reasons
import evaluate_ai


def response(reason="unclear_or_other"):
    content = json.dumps({"reason": reason, "confidence": 0.5, "evidence": "Insufficient evidence."})
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def api_error(status, code, headers=None):
    reply = httpx.Response(status, headers=headers, request=httpx.Request("POST", "https://example.test"))
    cls = RateLimitError if status == 429 else BadRequestError
    return cls(code, response=reply, body={"code": code})


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch("ai_reasons.time.sleep").start()
        self.addCleanup(patch.stopall)
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.client = Mock()
        self.row = {"customer_message": "Help", "agent_notes": None, "response_minutes": 900}

    def classify(self, responses):
        self.client.chat.completions.create.side_effect = responses
        return ai_reasons.classify_ticket(self.client, self.row, "openai/gpt-oss-20b")

    def test_rate_limits_back_off_then_succeed(self):
        result = self.classify([api_error(429, "rate_limit_exceeded") for _ in range(3)] + [response()])
        self.assertEqual(result["ai_error"], "")
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [2, 4, 8])
        self.assertEqual(self.client.chat.completions.create.call_count, 4)
        payload = json.loads(self.client.chat.completions.create.call_args.kwargs["messages"][1]["content"])
        self.assertEqual(payload, {"response_minutes": 900, "customer_message": "Help", "agent_notes": ""})

    def test_exhausted_rate_limit_preserves_final_exception(self):
        errors = [api_error(429, f"limit_{i}") for i in range(4)]
        with self.assertRaises(RateLimitError) as caught:
            self.classify(errors)
        self.assertIs(caught.exception, errors[-1])
        self.assertEqual(self.client.chat.completions.create.call_count, 4)

    def test_retry_after_is_respected_and_capped(self):
        self.classify([api_error(429, "rate_limit", {"retry-after": "120"}), response()])
        self.sleep.assert_called_once_with(60)

    def test_provider_json_failure_gets_one_stricter_retry(self):
        self.classify([api_error(400, "json_validate_failed"), response()])
        calls = self.client.chat.completions.create.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertNotIn(ai_reasons.STRICT_PROMPT, calls[0].kwargs["messages"][0]["content"])
        self.assertIn(ai_reasons.STRICT_PROMPT, calls[1].kwargs["messages"][0]["content"])

    def test_invalid_reason_gets_retry_not_silent_other_label(self):
        result = self.classify([response("invented_category"), response("high_queue_volume")])
        self.assertEqual(result["ai_reason"], "high_queue_volume")

    def test_json_retry_is_bounded(self):
        with self.assertRaises(ValueError):
            self.classify([response("invalid"), response("still_invalid")])
        self.assertEqual(self.client.chat.completions.create.call_count, 2)

    def test_mixed_errors_have_total_budget_of_five_calls(self):
        with self.assertRaises(BadRequestError):
            self.classify([
                api_error(429, "rate_limit"), api_error(400, "json_validate_failed"),
                api_error(429, "rate_limit"), api_error(429, "rate_limit"),
                api_error(400, "json_validate_failed"),
            ])
        self.assertEqual(self.client.chat.completions.create.call_count, 5)

    def test_unrelated_bad_request_is_not_retried(self):
        with self.assertRaises(BadRequestError):
            self.classify([api_error(400, "model_not_found")])
        self.assertEqual(self.client.chat.completions.create.call_count, 1)

    def test_malformed_json_schema_is_rejected(self):
        for content in ("not json", "[]", "{}", None,
                        '{"reason":"unclear_or_other","confidence":true,"evidence":"x"}',
                        '{"reason":"unclear_or_other","confidence":NaN,"evidence":"x"}',
                        '{"reason":"unclear_or_other","confidence":1.1,"evidence":"x"}',
                        '{"reason":"unclear_or_other","confidence":0.5,"evidence":""}'):
            with self.subTest(content=content), self.assertRaises(ValueError):
                ai_reasons.parse_classification(content)


class ContextAndHistoryTests(unittest.TestCase):
    def test_whitelisted_operational_context_preserves_existing_values(self):
        row = pd.Series({
            "channel": "chat", "response_minutes": 421.5, "sla_minutes": 15,
            "created_shift": "Night", "overnight_created": True, "transfers": 1,
            "assigned_team": "Logistics", "priority": "High", "category": "Delivery",
            "source_system": "helpdesk", "agent_id": "TEST-AGENT", "team": "Logistics",
            "customer_message": "Where is my order?", "agent_notes": "Picked up next shift",
            "customer_id": "excluded", "sla_credit_inr": 350, "breach": True,
        })
        before = row.copy()
        payload = ai_reasons.build_payload(row)
        self.assertEqual(set(payload), set(ai_reasons.CONTEXT_FIELDS) | {"customer_message", "agent_notes"})
        for key in ai_reasons.CONTEXT_FIELDS:
            self.assertEqual(payload[key], row[key])
        self.assertIs(payload["overnight_created"], True)
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)
        pd.testing.assert_series_equal(row, before)

    def test_missing_context_is_omitted_not_invented_and_zero_false_survive(self):
        payload = ai_reasons.build_payload({
            "transfers": pd.Series([0]).iloc[0],
            "overnight_created": pd.Series([False]).iloc[0],
            "response_minutes": float("nan"), "sla_minutes": pd.NA,
            "channel": "", "agent_notes": None,
        })
        self.assertEqual(payload, {"transfers": 0, "overnight_created": False,
                                   "customer_message": "", "agent_notes": ""})
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)

    def test_classifier_refuses_to_overwrite_experiment_before_api_call(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "existing.csv"
            output.write_text("existing experiment")
            argv = ["ai_reasons.py", "--sample", "30", "--output", str(output)]
            with patch.object(sys, "argv", argv), patch("ai_reasons.OpenAI") as client:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    ai_reasons.main()
                client.assert_not_called()
            self.assertEqual(output.read_text(), "existing experiment")

    def test_custom_output_records_final_error_without_touching_default(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "v2.csv"
            tickets = pd.DataFrame([{"ticket_id": "test-error", "breach": True}])
            argv = ["ai_reasons.py", "--sample", "1", "--output", str(output)]
            with patch.object(sys, "argv", argv), patch.dict("os.environ", {"GROQ_API_KEY": "test-only"}):
                with patch("ai_reasons.pd.read_csv", return_value=tickets), patch("ai_reasons.OpenAI"):
                    with patch("ai_reasons.classify_ticket", side_effect=ValueError("final JSON failure")):
                        with contextlib.redirect_stdout(io.StringIO()):
                            ai_reasons.main()
            saved = pd.read_csv(output, keep_default_na=False)
            self.assertEqual(saved.loc[0, "ai_error"], "final JSON failure")
            self.assertEqual(saved.loc[0, "ai_reason"], "")


class HumanEvaluationTests(unittest.TestCase):
    def source(self):
        rows = []
        for i, reason in enumerate(ai_reasons.REASONS):
            for j in range(10 if i == 0 else 5):
                rows.append({
                    "ticket_id": f"test-{i}-{j}", "customer_message": "Test only",
                    "agent_notes": "Test only", "ai_reason": reason,
                    "ai_confidence": "0.5", "ai_evidence": "Test only", "ai_error": "",
                    "channel": "chat", "response_minutes": "421", "sla_minutes": "15",
                    "created_shift": "Night", "overnight_created": "True",
                    "transfers": "1", "assigned_team": "Logistics",
                })
        rows.append({**rows[0], "ticket_id": "failed-ticket", "ai_error": "429"})
        rows.append(rows[0].copy())  # Duplicate tickets cannot inflate the sample.
        return pd.DataFrame(rows)

    def test_sample_is_successful_unique_representative_and_unlabeled(self):
        source = self.source()
        sample = evaluate_ai.create_sample(source)
        self.assertEqual(len(sample), 30)
        self.assertEqual(sample.ticket_id.nunique(), 30)
        self.assertEqual(set(sample.ai_reason), set(ai_reasons.REASONS))
        self.assertNotIn("failed-ticket", set(sample.ticket_id))
        self.assertEqual(list(sample.columns), evaluate_ai.EVAL_COLUMNS)
        self.assertTrue(sample[["human_reason", "agreement", "review_notes"]].eq("").all().all())
        pd.testing.assert_frame_equal(sample, evaluate_ai.create_sample(source))

    def test_sample_retains_deterministic_context_from_source(self):
        source = self.source()
        source.loc[0, "transfers"] = "0"
        source.loc[0, "overnight_created"] = "False"
        sample = evaluate_ai.create_sample(source, size=40).set_index("ticket_id")
        expected = source.loc[source.ai_error.eq("")].drop_duplicates("ticket_id").set_index("ticket_id")
        columns = evaluate_ai.CONTEXT_COLUMNS
        pd.testing.assert_frame_equal(sample[columns].sort_index(), expected[columns].sort_index())

    def test_original_evaluation_schema_still_scores_without_added_context(self):
        legacy = evaluate_ai.create_sample(self.source())[evaluate_ai.BASE_EVAL_COLUMNS]
        legacy.loc[0, "human_reason"] = legacy.loc[0, "ai_reason"]
        with contextlib.redirect_stdout(io.StringIO()):
            evaluated = evaluate_ai.evaluate(legacy)
        self.assertEqual(list(evaluated.columns), evaluate_ai.BASE_EVAL_COLUMNS)
        self.assertEqual(evaluated.loc[0, "agreement"], "yes")

    def test_sample_creation_does_not_erase_existing_human_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "human_eval.csv"
            original = "ticket_id,human_reason,review_notes\n1,unclear_or_other,Keep my review\n"
            output.write_text(original)
            argv = ["evaluate_ai.py", "--create-sample", "--file", str(output)]
            with patch.object(sys, "argv", argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    evaluate_ai.main()
            self.assertEqual(output.read_text(), original)

    def test_insufficient_successes_fails_instead_of_padding(self):
        with self.assertRaisesRegex(ValueError, "found 2"):
            evaluate_ai.create_sample(self.source().iloc[:2])

    def test_sampling_can_handle_more_categories_than_slots(self):
        sample = evaluate_ai.create_sample(self.source(), size=3)
        self.assertEqual(len(sample), 3)

    def test_pending_labels_do_not_report_zero_accuracy(self):
        sample = evaluate_ai.create_sample(self.source())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            evaluate_ai.evaluate(sample)
        self.assertIn("Pending manual labels", output.getvalue())
        self.assertNotIn("Agreement rate:", output.getvalue())
        self.assertNotIn("Error rate:", output.getvalue())

    def test_partial_review_counts_only_labeled_rows_and_computes_agreement(self):
        sample = evaluate_ai.create_sample(self.source())
        sample.loc[0, "human_reason"] = sample.loc[0, "ai_reason"]
        sample.loc[1, "human_reason"] = next(r for r in ai_reasons.REASONS if r != sample.loc[1, "ai_reason"])
        sample.loc[1, "review_notes"] = "Human explanation"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            evaluated = evaluate_ai.evaluate(sample)
        for text in ("Sample size: 2", "Unlabeled tickets: 28", "Agreement: 1/2",
                     "Agreement rate: 50.00%", "Errors: 1", "Error rate: 50.00%",
                     "Most common disagreements", "Confusion matrix"):
            self.assertIn(text, output.getvalue())
        self.assertEqual(evaluated.loc[0, "agreement"], "yes")
        self.assertEqual(evaluated.loc[1, "agreement"], "no")
        self.assertEqual(evaluated.loc[2, "agreement"], "")
        self.assertEqual(evaluated.loc[1, "review_notes"], "Human explanation")

    def test_assistant_review_provenance_is_not_presented_as_human_accuracy(self):
        sample = evaluate_ai.create_sample(self.source())
        sample.loc[0, "human_reason"] = sample.loc[0, "ai_reason"]
        sample.loc[0, "review_notes"] = "Assistant-reviewed: supplied facts support this label."
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            evaluate_ai.evaluate(sample)
        self.assertIn("1/1 assistant-generated review labels", output.getvalue())
        self.assertIn("not an independent model accuracy estimate", output.getvalue())
        self.assertIn("Agreement: 1/1", output.getvalue())

    def test_invalid_human_label_is_rejected_not_counted_as_error(self):
        sample = evaluate_ai.create_sample(self.source())
        sample.loc[0, "human_reason"] = "a typo"
        with self.assertRaisesRegex(ValueError, "Invalid human_reason"):
            evaluate_ai.evaluate(sample)

    def test_duplicate_evaluation_rows_are_rejected(self):
        sample = evaluate_ai.create_sample(self.source())
        sample.loc[1, "ticket_id"] = sample.loc[0, "ticket_id"]
        with self.assertRaisesRegex(ValueError, "unique"):
            evaluate_ai.evaluate(sample)


if __name__ == "__main__":
    unittest.main()
