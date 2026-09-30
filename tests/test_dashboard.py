"""Read-only dashboard smoke and filter checks (no API calls)."""

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    def test_dashboard_loads_outputs_without_api_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Vireo Audio — Support SLA Breach Monitor")
        self.assertEqual([widget.label for widget in app.multiselect], ["Week", "Shift", "Agent"])
        self.assertEqual(app.multiselect[0].value, [])
        self.assertEqual(app.multiselect[2].value, [])
        self.assertEqual(len(app.dataframe[0].value), len(pd.read_csv(ROOT / "output" / "weekly_agent_shift_breaches.csv")))
        self.assertEqual(len(app.metric), 7)
        self.assertIn("30/30 agreement with assistant-generated review labels", app.info[-1].value)

    def test_filters_update_the_report_without_errors(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        row = pd.read_csv(ROOT / "output" / "weekly_agent_shift_breaches.csv").iloc[-1]
        selected_week = row.week
        app.multiselect[0].set_value([selected_week])
        app.multiselect[1].set_value([row["shift"]])
        app.multiselect[2].set_value([row.agent_name])
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.multiselect[0].value, [selected_week])
        self.assertEqual(app.multiselect[1].value, [row["shift"]])
        self.assertEqual(app.multiselect[2].value, [row.agent_name])
        displayed = app.dataframe[0].value
        self.assertEqual(len(displayed), 1)
        self.assertEqual(displayed.iloc[0]["week"], selected_week)
        self.assertEqual(displayed.iloc[0]["agent"], row.agent_name)

    def test_missing_artifacts_show_a_message_without_crashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            isolated_app = Path(temporary) / "app.py"
            shutil.copy2(ROOT / "app.py", isolated_app)
            app = AppTest.from_file(str(isolated_app), default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertIn("Required dashboard file is missing", app.error[0].value)


if __name__ == "__main__":
    unittest.main()
