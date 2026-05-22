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


if __name__ == "__main__":
    unittest.main()
