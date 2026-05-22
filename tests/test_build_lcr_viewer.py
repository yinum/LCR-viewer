import os, sys, json, unittest, tempfile, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_lcr_viewer as blv


class TestParseSpectrum(unittest.TestCase):
    def _write(self, text):
        fh = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        fh.write(text)
        fh.close()
        return fh.name

    def test_whitespace_and_comma_rows(self):
        path = self._write("100.0 5\n200.5\t8\n300.0,3\njunk line\n")
        mz, it = blv.parse_spectrum(path)
        os.unlink(path)
        self.assertEqual(mz, [100.0, 200.5, 300.0])
        self.assertEqual(it, [5.0, 8.0, 3.0])

    def test_empty_file_raises(self):
        path = self._write("not numbers\n")
        with self.assertRaises(ValueError):
            blv.parse_spectrum(path)
        os.unlink(path)


class TestFindSegments(unittest.TestCase):
    def test_two_clusters_split_at_large_gap(self):
        # cluster A: 100.0..100.6 step 0.2 ; big gap ; cluster B: 150.0..150.4
        mz = [100.0, 100.2, 100.4, 100.6, 150.0, 150.2, 150.4]
        segs = blv.find_segments(mz)
        self.assertEqual(segs, [(0, 3), (4, 6)])

    def test_single_cluster_one_segment(self):
        mz = [100.0, 100.2, 100.4, 100.6]
        self.assertEqual(blv.find_segments(mz), [(0, 3)])

    def test_empty_input(self):
        self.assertEqual(blv.find_segments([]), [])


class TestBasePeakAnalysis(unittest.TestCase):
    # parent envelope 100.0..100.6 (base peak at 100.2, intensity 90);
    # charge-reduced cluster 150.0..150.4 (small)
    MZ = [100.0, 100.2, 100.4, 100.6, 150.0, 150.2, 150.4]
    IT = [40.0, 90.0, 50.0, 10.0, 4.0, 6.0, 3.0]

    def test_precursor_mz_is_rounded_base_peak(self):
        self.assertEqual(blv.precursor_mz(self.MZ, self.IT), 100)

    def test_threshold_is_fixed_margin_past_parent_edge(self):
        # parent envelope right edge is 100.6; threshold = edge + THRESHOLD_MARGIN,
        # with no clamping against satellite peaks just above the envelope
        thr = blv.auto_threshold(self.MZ, self.IT)
        self.assertAlmostEqual(thr, 100.6 + blv.THRESHOLD_MARGIN, delta=1e-6)


class TestOutputFilename(unittest.TestCase):
    def test_name_format(self):
        when = datetime.datetime(2026, 5, 22, 9, 7)
        name = blv.output_filename(2092, when)
        self.assertEqual(name, "LCR_mz2092_20260522-0907.html")

    def test_rounds_float_precursor(self):
        when = datetime.datetime(2026, 5, 22, 9, 7)
        self.assertEqual(blv.output_filename(3300.0, when),
                         "LCR_mz3300_20260522-0907.html")
        self.assertEqual(blv.output_filename(3300.7, when),
                         "LCR_mz3301_20260522-0907.html")


class TestIterSpectrumFiles(unittest.TestCase):
    def test_single_file_yields_itself(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        fh.close()
        self.assertEqual(blv.iter_spectrum_files(fh.name), [fh.name])
        os.unlink(fh.name)

    def test_directory_yields_sorted_txt_and_csv(self):
        d = tempfile.mkdtemp()
        for name in ["b.txt", "a.csv", "skip.json", ".hidden.txt"]:
            open(os.path.join(d, name), "w").close()
        got = [os.path.basename(p) for p in blv.iter_spectrum_files(d)]
        self.assertEqual(got, ["a.csv", "b.txt"])
        for name in os.listdir(d):
            os.unlink(os.path.join(d, name))
        os.rmdir(d)


class TestBuildHtml(unittest.TestCase):
    MZ = [100.0, 100.2, 100.4, 150.0, 150.2]
    IT = [40.0, 90.0, 50.0, 4.0, 6.0]
    NAME = "LCR_mz2092_20260522-0907.html"

    def test_preset_values_baked_in(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET)
        self.assertIn('id="scale" value="10"', html)
        self.assertIn('id="win" value="299"', html)
        self.assertIn('id="thr" value="123.45"', html)
        self.assertIn('value="avg" selected', html)
        # overlay preset is False -> rawov checkbox must NOT be checked
        self.assertNotIn('id="rawov" checked', html)
        # data and plotly are inlined
        self.assertIn("/*plotly*/", html)
        self.assertNotIn("__MZ__", html)
        self.assertNotIn("__SCALE__", html)

    def test_linked_csv_feature_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET)
        self.assertIn('id="link"', html)          # Link CSV button
        self.assertIn("showSaveFilePicker", html)  # File System Access API
        self.assertIn("buildCSV", html)            # shared CSV helper
        self.assertIn('id="dl"', html)             # download fallback kept
        # processed CSV name shares the viewer's stem (LCR_mz..._....csv)
        self.assertIn("LCR_mz2092_20260522-0907.csv", html)
        self.assertNotIn("polyP_LCR_processed.csv", html)

    def test_custom_preset_overrides_controls(self):
        custom = {"scale": 7, "method": "sg", "window": 15,
                  "poly": 2, "show_overlay": True}
        html = blv.build_html(self.MZ, self.IT, 50.0, "/*plotly*/", self.NAME, custom)
        self.assertIn('id="scale" value="7"', html)
        self.assertIn('id="win" value="15"', html)
        self.assertIn('value="sg" selected', html)
        self.assertIn('id="rawov" checked', html)

    def test_save_preset_button_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET)
        self.assertIn('id="savepreset"', html)   # Save preset button
        self.assertIn("buildPreset", html)       # JS gathers control values
        self.assertIn("preset.json", html)       # target filename


class TestMainIntegration(unittest.TestCase):
    def test_folder_input_writes_named_viewers(self):
        src = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        # one spectrum: parent envelope near m/z 200, small cluster near 260
        spec = "".join("%.1f %.1f\n" % (m, i) for m, i in [
            (200.0, 40), (200.2, 90), (200.4, 50), (200.6, 10),
            (260.0, 4), (260.2, 6), (260.4, 3)])
        with open(os.path.join(src, "run.txt"), "w") as f:
            f.write(spec)
        argv = sys.argv
        sys.argv = ["build_lcr_viewer.py", src, out]
        try:
            blv.main()
        finally:
            sys.argv = argv
        files = os.listdir(out)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("LCR_mz200_"))
        self.assertTrue(files[0].endswith(".html"))
        for d in (src, out):
            for n in os.listdir(d):
                os.unlink(os.path.join(d, n))
            os.rmdir(d)


    def test_filename_precursor_names_the_viewer(self):
        src = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        # base peak is near m/z 600, but the filename says precursor 250
        spec = "".join("%.1f %.1f\n" % (m, i) for m, i in [
            (250.0, 30), (250.2, 45), (250.4, 25),
            (600.0, 40), (600.2, 95), (600.4, 50)])
        with open(os.path.join(src, "sample_250.txt"), "w") as f:
            f.write(spec)
        argv = sys.argv
        sys.argv = ["build_lcr_viewer.py", src, out]
        try:
            blv.main()
        finally:
            sys.argv = argv
        files = os.listdir(out)
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("LCR_mz250_"))
        for d in (src, out):
            for n in os.listdir(d):
                os.unlink(os.path.join(d, n))
            os.rmdir(d)


class TestLoadPreset(unittest.TestCase):
    def test_no_file_returns_builtin_defaults(self):
        d = tempfile.mkdtemp()
        self.assertEqual(blv.load_preset(d), blv.PRESET)
        os.rmdir(d)

    def test_valid_file_overrides(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "preset.json"), "w") as fh:
            json.dump({"scale": 25, "method": "sg", "window": 51,
                       "poly": 4, "show_overlay": True}, fh)
        eff = blv.load_preset(d)
        self.assertEqual(eff["scale"], 25)
        self.assertEqual(eff["method"], "sg")
        self.assertEqual(eff["window"], 51)
        self.assertEqual(eff["show_overlay"], True)
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)

    def test_partial_keys_merge_over_defaults(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "preset.json"), "w") as fh:
            json.dump({"window": 777, "bogus": 1}, fh)
        eff = blv.load_preset(d)
        self.assertEqual(eff["window"], 777)                  # overridden
        self.assertEqual(eff["scale"], blv.PRESET["scale"])   # default kept
        self.assertNotIn("bogus", eff)                        # unknown ignored
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)

    def test_malformed_json_returns_defaults(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "preset.json"), "w") as fh:
            fh.write("{not valid json")
        self.assertEqual(blv.load_preset(d), blv.PRESET)
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)


class TestPrecursorFromName(unittest.TestCase):
    def test_integer_trailing_number(self):
        self.assertEqual(blv.precursor_from_name("PF4_polyP_3300.xy"), 3300.0)

    def test_decimal_trailing_number(self):
        self.assertEqual(blv.precursor_from_name("run_3300.5.xy"), 3300.5)

    def test_path_is_handled(self):
        self.assertEqual(blv.precursor_from_name("/data/LCR/PF4_polyP_3700.xy"),
                         3700.0)

    def test_no_trailing_number_returns_none(self):
        self.assertIsNone(blv.precursor_from_name("clipboard_spectrum.txt"))


class TestPrecursorThreshold(unittest.TestCase):
    # cluster A near m/z 100 (minor); cluster B near m/z 200 (holds the base peak)
    MZ = [100.0, 100.1, 100.2, 200.0, 200.1, 200.2]
    IT = [20.0, 30.0, 20.0, 40.0, 90.0, 40.0]

    def test_no_precursor_uses_base_peak_cluster(self):
        thr = blv.auto_threshold(self.MZ, self.IT)
        self.assertAlmostEqual(thr, 200.2 + blv.THRESHOLD_MARGIN, delta=1e-6)

    def test_precursor_anchors_to_its_own_cluster(self):
        # base peak is in cluster B (~200), but precursor 100 -> cluster A
        thr = blv.auto_threshold(self.MZ, self.IT, 100.0)
        self.assertAlmostEqual(thr, 100.2 + blv.THRESHOLD_MARGIN, delta=1e-6)

    def test_precursor_in_gap_uses_nearest_cluster(self):
        # precursor 130 lies between the clusters; nearest edge is A's (100.2)
        thr = blv.auto_threshold(self.MZ, self.IT, 130.0)
        self.assertAlmostEqual(thr, 100.2 + blv.THRESHOLD_MARGIN, delta=1e-6)


if __name__ == "__main__":
    unittest.main()
