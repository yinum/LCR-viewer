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

    def test_threshold_sits_just_past_parent_edge(self):
        thr = blv.auto_threshold(self.MZ, self.IT)
        # parent segment right edge is 100.6; threshold lands in the valley
        # before the next cluster at 150.0
        self.assertGreater(thr, 100.6)
        self.assertLess(thr, 150.0)

    def test_threshold_margin_clamped_to_half_gap(self):
        # fine 0.01 spacing -> gap threshold floors at 1.0, so a 1.5 m/z gap
        # splits the clusters; gap/2 (0.75) is below THRESHOLD_MARGIN (2.0),
        # so the margin is clamped to 0.75
        mz = [100.00, 100.01, 100.02, 100.03, 101.53, 101.54, 101.55]
        it = [40.0, 90.0, 50.0, 10.0, 5.0, 6.0, 4.0]
        thr = blv.auto_threshold(mz, it)
        self.assertAlmostEqual(thr, 100.78, delta=1e-4)


if __name__ == "__main__":
    unittest.main()
