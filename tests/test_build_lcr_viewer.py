import os, sys, unittest, tempfile, datetime

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
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME)
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
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME)
        self.assertIn('id="link"', html)          # Link CSV button
        self.assertIn("showSaveFilePicker", html)  # File System Access API
        self.assertIn("buildCSV", html)            # shared CSV helper
        self.assertIn('id="dl"', html)             # download fallback kept
        # processed CSV name shares the viewer's stem (LCR_mz..._....csv)
        self.assertIn("LCR_mz2092_20260522-0907.csv", html)
        self.assertNotIn("polyP_LCR_processed.csv", html)


class TestMainIntegration(unittest.TestCase):
    def test_folder_input_writes_named_viewers(self):
        src = tempfile.mkdtemp()
        out = tempfile.mkdtemp()
        # one spectrum: parent envelope near m/z 200, small cluster near 260
        spec = "".join("%.1f %.1f\n" % (m, i) for m, i in [
            (200.0, 40), (200.2, 90), (200.4, 50), (200.6, 10),
            (260.0, 4), (260.2, 6), (260.4, 3)])
        with open(os.path.join(src, "run1.txt"), "w") as f:
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


if __name__ == "__main__":
    unittest.main()
