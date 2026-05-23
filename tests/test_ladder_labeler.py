"""Tests for the LCR ladder-labeling Python wiring (preset block,
load_preset nested merge, build-time substitution of __LADDER_LABELER__).
The labeler JS itself is tested by tests/ladder_labeler_test.html in a
browser; this suite covers only the Python build surface."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import build_lcr_viewer as B


class PresetBlockTests(unittest.TestCase):
    def test_preset_has_ladder_labels_block(self):
        self.assertIn("ladder_labels", B.PRESET)
        block = B.PRESET["ladder_labels"]
        self.assertEqual(block["enabled"], False)
        self.assertEqual(block["tol_mz"], 5.0)
        self.assertEqual(block["sigma_amber_relative"], 0.01)

    def test_load_preset_no_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            eff = B.load_preset(td)
            self.assertEqual(eff["ladder_labels"], B.PRESET["ladder_labels"])

    def test_load_preset_partial_merge_keeps_unspecified_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "preset.json"), "w") as fh:
                json.dump({"ladder_labels": {"enabled": True}}, fh)
            eff = B.load_preset(td)
            # 'enabled' came from saved; tol_mz and sigma_amber_relative stay default
            self.assertEqual(eff["ladder_labels"]["enabled"], True)
            self.assertEqual(eff["ladder_labels"]["tol_mz"], 5.0)
            self.assertEqual(eff["ladder_labels"]["sigma_amber_relative"], 0.01)

    def test_load_preset_full_override(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "preset.json"), "w") as fh:
                json.dump({"ladder_labels": {
                    "enabled": True, "tol_mz": 8.0, "sigma_amber_relative": 0.02
                }}, fh)
            eff = B.load_preset(td)
            self.assertEqual(eff["ladder_labels"]["enabled"], True)
            self.assertEqual(eff["ladder_labels"]["tol_mz"], 8.0)
            self.assertEqual(eff["ladder_labels"]["sigma_amber_relative"], 0.02)

    def test_load_preset_ignores_non_dict_ladder_labels(self):
        """A malformed saved value (e.g. boolean) for a dict-valued preset
        key must not corrupt eff[k] — the defaults stand."""
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "preset.json"), "w") as fh:
                json.dump({"ladder_labels": True}, fh)
            eff = B.load_preset(td)
            self.assertEqual(eff["ladder_labels"], B.PRESET["ladder_labels"])

    def test_load_preset_empty_ladder_labels_keeps_defaults(self):
        """An empty saved ladder_labels block is valid; all sub-keys
        fall back to their defaults via the nested merge."""
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "preset.json"), "w") as fh:
                json.dump({"ladder_labels": {}}, fh)
            eff = B.load_preset(td)
            self.assertEqual(eff["ladder_labels"]["enabled"], False)
            self.assertEqual(eff["ladder_labels"]["tol_mz"], 5.0)
            self.assertEqual(eff["ladder_labels"]["sigma_amber_relative"], 0.01)


if __name__ == "__main__":
    unittest.main()
