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


class TemplateSubstitutionTests(unittest.TestCase):
    """The build inlines ladder_labeler.js into the HTML via the
    __LADDER_LABELER__ placeholder, mirroring the __PLOTLY__ pattern."""

    def _build_minimal_html(self):
        mz = [3000.0, 3100.0, 3200.0, 3300.0, 3400.0]
        it = [0.0, 1.0, 5.0, 10.0, 5.0]
        thr = 3250.0
        plotly_stub = "/* plotly stub */"
        labeler_stub_path = os.path.join(ROOT, "ladder_labeler.js")
        with open(labeler_stub_path) as fh:
            labeler_js = fh.read()
        # Build HTML through the same path main() uses.
        html = B.build_html(mz, it, thr, plotly_stub,
                            "LCR_mz3300_20260522-1200.html",
                            B.PRESET, labeler_js)
        return html, labeler_js

    def test_built_html_inlines_ladder_labeler(self):
        html, labeler_js = self._build_minimal_html()
        # Signature lines unique to ladder_labeler.js
        self.assertIn("const LadderLabelerCore", html)
        self.assertIn("const LadderLabeler", html)

    def test_built_html_no_unsubstituted_placeholder(self):
        html, _ = self._build_minimal_html()
        self.assertNotIn("__LADDER_LABELER__", html)


class PanelMarkupTests(unittest.TestCase):
    """The viewer HTML carries the ladder-labels control panel markup
    (always rendered; visible when the labeler is enabled)."""

    def _build(self, ladder_labels=None):
        preset = dict(B.PRESET)
        if ladder_labels is not None:
            preset["ladder_labels"] = ladder_labels
        html = B.build_html([3000.0, 3100.0], [0.0, 1.0], 3050.0,
                            "/* plotly */", "LCR_mz3000_20260522-1200.html",
                            preset, "/* labeler */")
        return html

    def test_panel_has_enabled_checkbox(self):
        html = self._build()
        self.assertIn('id="ladder-enabled"', html)

    def test_panel_has_tol_input(self):
        html = self._build()
        self.assertIn('id="ladder-tol"', html)

    def test_tol_input_default_from_preset(self):
        html = self._build()
        self.assertIn('value="5.0"', html)  # the default tol_mz

    def test_enabled_checked_when_preset_enabled(self):
        html = self._build({"enabled": True, "tol_mz": 5.0,
                            "sigma_amber_relative": 0.01})
        self.assertIn('id="ladder-enabled" checked', html)

    def test_panel_has_ladders_list_container(self):
        html = self._build()
        self.assertIn('id="ladder-list"', html)

    def test_panel_has_add_buttons(self):
        html = self._build()
        self.assertIn('id="ladder-add-type"', html)
        self.assertIn('id="ladder-add-twoclick"', html)
        self.assertIn('id="ladder-clear"', html)


if __name__ == "__main__":
    unittest.main()
