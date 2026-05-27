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

    def test_directory_yields_sorted_txt_csv_xy(self):
        d = tempfile.mkdtemp()
        for name in ["b.txt", "a.csv", "c.xy", "skip.json", ".hidden.txt"]:
            open(os.path.join(d, name), "w").close()
        got = [os.path.basename(p) for p in blv.iter_spectrum_files(d)]
        self.assertEqual(got, ["a.csv", "b.txt", "c.xy"])
        for name in os.listdir(d):
            os.unlink(os.path.join(d, name))
        os.rmdir(d)


class TestBuildHtml(unittest.TestCase):
    MZ = [100.0, 100.2, 100.4, 150.0, 150.2]
    IT = [40.0, 90.0, 50.0, 4.0, 6.0]
    NAME = "LCR_mz2092_20260522-0907.html"

    def test_preset_values_baked_in(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET, "")
        self.assertIn('id="scale" value="10"', html)
        self.assertIn('id="width" value="0.04"', html)
        self.assertIn('id="thr" value="123.45"', html)
        self.assertIn('value="avg" selected', html)
        # overlay preset is False -> rawov checkbox must NOT be checked
        self.assertNotIn('id="rawov" checked', html)
        # data and plotly are inlined
        self.assertIn("/*plotly*/", html)
        self.assertNotIn("__MZ__", html)
        self.assertNotIn("__SCALE__", html)

    def test_linked_csv_feature_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET, "")
        self.assertIn('id="link"', html)          # Link CSV button
        self.assertIn("showSaveFilePicker", html)  # File System Access API
        self.assertIn("buildCSV", html)            # shared CSV helper
        self.assertIn('id="dl"', html)             # download fallback kept
        # processed CSV name shares the viewer's stem (LCR_mz..._....csv)
        self.assertIn("LCR_mz2092_20260522-0907.csv", html)
        self.assertNotIn("polyP_LCR_processed.csv", html)

    def test_sibling_csv_hyperlink_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET, "")
        self.assertIn('id="csvfile"', html)        # header hyperlink element
        # links to the sibling CSV file in the same folder
        self.assertIn('href="LCR_mz2092_20260522-0907.csv"', html)
        self.assertNotIn("__CSVHREF__", html)      # placeholder fully replaced

    def test_custom_preset_overrides_controls(self):
        custom = {"scale": 7, "method": "sg", "width_mz": 0.02,
                  "poly": 2, "show_overlay": True}
        html = blv.build_html(self.MZ, self.IT, 50.0, "/*plotly*/", self.NAME, custom, "")
        self.assertIn('id="scale" value="7"', html)
        self.assertIn('id="width" value="0.02"', html)
        self.assertIn('value="sg" selected', html)
        self.assertIn('id="rawov" checked', html)

    def test_save_preset_button_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET, "")
        self.assertIn('id="savepreset"', html)   # Save preset button
        self.assertIn("buildPreset", html)       # JS gathers control values
        self.assertIn("preset.json", html)       # target filename

    def test_update_sibling_csv_button_present(self):
        html = blv.build_html(self.MZ, self.IT, 123.45, "/*plotly*/", self.NAME, blv.PRESET, "")
        self.assertIn('id="updatecsv"', html)    # Update sibling CSV button
        self.assertIn("/csv?name=", html)        # serve-mode POST endpoint
        self.assertIn("siblingHandle", html)     # file:// FSA handle cache

    def test_default_build_calls_loadSpectrum_at_startup(self):
        """A default build's HTML must call loadSpectrum(mz, it, csvName)
        once at startup so the uploader can reuse the same entry point."""
        import re
        mz = [100.0, 200.0, 300.0]
        it = [10.0, 20.0, 30.0]
        html = blv.build_html(
            mz, it, 250.0, "/* plotly stub */",
            "LCR_mz200_20260101-0000.html",
            blv.PRESET,
            "/* labeler stub */",
        )
        # loadSpectrum(...) must be called exactly once with the inlined arrays.
        matches = re.findall(r"loadSpectrum\(", html)
        self.assertEqual(len(matches), 1,
                         "expected exactly one loadSpectrum(...) call in default build")

    def test_hdb_keys_bound_at_loadSpectrum_call_time_not_script_init(self):
        """HDB_SIBLING and HDB_LINK must be assigned inside loadSpectrum so they
        reflect the per-spectrum CSV_NAME; capturing them at script-init time
        (when CSV_NAME is still '') breaks IndexedDB handle persistence on reload.

        Regression test for the bug introduced by 959f5bf: the refactor made
        CSV_NAME mutable but left HDB_SIBLING/HDB_LINK as top-level const
        expressions that evaluated before loadSpectrum was ever called."""
        mz = [100.0, 200.0, 300.0]
        it = [10.0, 20.0, 30.0]
        html = blv.build_html(
            mz, it, 500.0, "/* plotly stub */",
            "LCR_mz500_test.html",
            blv.PRESET,
            "/* labeler stub */",
        )
        # --- Bug check: the top-level const form must NOT appear ---
        # Before the fix, the template contained:
        #   const HDB_SIBLING='sibling:'+CSV_NAME,HDB_LINK='link:'+CSV_NAME;
        # which captured CSV_NAME="" at script-init time, not at call time.
        self.assertNotIn(
            "const HDB_SIBLING='sibling:'+CSV_NAME",
            html,
            "HDB_SIBLING must not be a top-level const capturing CSV_NAME at "
            "script-init time; it must be assigned inside loadSpectrum instead",
        )
        self.assertNotIn(
            "const HDB_LINK='link:'+CSV_NAME",
            html,
            "HDB_LINK must not be a top-level const capturing CSV_NAME at "
            "script-init time; it must be assigned inside loadSpectrum instead",
        )
        # --- Fix check: mutable top-level declarations with empty initial value ---
        self.assertIn(
            "let HDB_SIBLING='',HDB_LINK='';",
            html,
            "HDB_SIBLING and HDB_LINK should be declared as mutable (let) "
            "top-level vars initialized to '' so loadSpectrum can assign them",
        )
        # --- Fix check: assignments appear inside the loadSpectrum body ---
        # The assignment must use the mutable-variable form (not const).
        self.assertIn(
            "HDB_SIBLING = 'sibling:' + CSV_NAME",
            html,
            "Expected HDB_SIBLING to be re-assigned inside loadSpectrum body "
            "so the key reflects the current CSV_NAME at call time",
        )
        self.assertIn(
            "HDB_LINK    = 'link:'    + CSV_NAME",
            html,
            "Expected HDB_LINK to be re-assigned inside loadSpectrum body "
            "so the key reflects the current CSV_NAME at call time",
        )


    def test_uploader_flag_writes_single_html_to_dist(self):
        """--uploader emits dist/LCR_viewer.html with no spectrum baked in."""
        import subprocess, os, tempfile, shutil
        here = os.path.dirname(os.path.abspath(blv.__file__))
        dist = os.path.join(here, "dist")
        if os.path.isdir(dist):
            shutil.rmtree(dist)
        try:
            r = subprocess.run(
                ["python3", "build_lcr_viewer.py", "--uploader"],
                cwd=here, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            out = os.path.join(dist, "LCR_viewer.html")
            self.assertTrue(os.path.isfile(out), "dist/LCR_viewer.html not written")
            body = open(out).read()
            # Build stamp contains "-uploader-" and is present in the head section.
            self.assertRegex(body[:5000], r"-uploader-",
                             "build stamp marker missing in HTML head")
            self.assertNotIn("__MZ__", body, "unfilled __MZ__ placeholder")
            self.assertIn("loadSpectrum([], [],", body,
                          "uploader build should start with empty spectrum")
        finally:
            if os.path.isdir(dist):
                shutil.rmtree(dist)


class TestSavePostedCsv(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.name = "LCR_mz123_test.csv"
        self.csv_written = [self.name]

    def tearDown(self):
        for n in os.listdir(self.out):
            os.unlink(os.path.join(self.out, n))
        os.rmdir(self.out)

    def test_writes_allowed_name(self):
        body = "m/z,intensity_processed\n100.0,42.0\n"
        path = blv.save_posted_csv(self.out, self.csv_written, self.name, body)
        self.assertEqual(path, os.path.join(self.out, self.name))
        with open(path) as fh:
            self.assertEqual(fh.read(), body)

    def test_rejects_unknown_name(self):
        with self.assertRaises(ValueError):
            blv.save_posted_csv(self.out, self.csv_written, "other.csv", "x")

    def test_rejects_path_traversal(self):
        # even a crafted name fails the csv_written membership check
        with self.assertRaises(ValueError):
            blv.save_posted_csv(self.out, self.csv_written,
                                "../escape.csv", "x")
        self.assertEqual(os.listdir(self.out), [])


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
        files = sorted(os.listdir(out))
        # one viewer HTML + one sibling processed CSV, sharing a stem
        self.assertEqual(len(files), 2)
        html = [f for f in files if f.endswith(".html")]
        csv = [f for f in files if f.endswith(".csv")]
        self.assertEqual(len(html), 1)
        self.assertEqual(len(csv), 1)
        self.assertTrue(html[0].startswith("LCR_mz200_"))
        self.assertEqual(os.path.splitext(html[0])[0],
                         os.path.splitext(csv[0])[0])
        with open(os.path.join(out, csv[0])) as f:
            self.assertTrue(f.readline().startswith("m/z,intensity_processed"))
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
        files = sorted(os.listdir(out))
        self.assertEqual(len(files), 2)          # viewer HTML + sibling CSV
        html = [f for f in files if f.endswith(".html")]
        self.assertEqual(len(html), 1)
        self.assertTrue(html[0].startswith("LCR_mz250_"))
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
            json.dump({"scale": 25, "method": "sg", "width_mz": 0.05,
                       "poly": 4, "show_overlay": True}, fh)
        eff = blv.load_preset(d)
        self.assertEqual(eff["scale"], 25)
        self.assertEqual(eff["method"], "sg")
        self.assertEqual(eff["width_mz"], 0.05)
        self.assertEqual(eff["show_overlay"], True)
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)

    def test_partial_keys_merge_over_defaults(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "preset.json"), "w") as fh:
            json.dump({"width_mz": 0.08, "bogus": 1}, fh)
        eff = blv.load_preset(d)
        self.assertEqual(eff["width_mz"], 0.08)               # overridden
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


class TestParseArgs(unittest.TestCase):
    def test_serve_flag_detected_and_stripped(self):
        serve, src, out, uploader = blv.parse_args(["--serve", "/data", "/out"], "/here")
        self.assertTrue(serve)
        self.assertEqual(src, "/data")
        self.assertEqual(out, "/out")
        self.assertFalse(uploader)

    def test_serve_flag_anywhere(self):
        serve, src, out, uploader = blv.parse_args(["/data", "--serve"], "/here")
        self.assertTrue(serve)
        self.assertEqual(src, "/data")
        self.assertFalse(uploader)

    def test_no_serve_flag(self):
        serve, src, out, uploader = blv.parse_args(["/data"], "/here")
        self.assertFalse(serve)
        self.assertEqual(src, "/data")
        self.assertFalse(uploader)

    def test_uploader_flag_sets_uploader_mode(self):
        serve, src, out, uploader = blv.parse_args(["--uploader"], "/here")
        self.assertFalse(serve)
        self.assertIsNone(src)
        self.assertEqual(out, os.path.join("/here", "dist"))
        self.assertTrue(uploader)

    def test_uploader_flag_custom_dist(self):
        serve, src, out, uploader = blv.parse_args(["--uploader", "/custom/dist"], "/here")
        self.assertTrue(uploader)
        self.assertEqual(out, "/custom/dist")

    def test_default_output_from_input_folder_name(self):
        d = tempfile.mkdtemp()
        sub = os.path.join(d, "PF4_polyP")
        os.makedirs(sub)
        _, src, out, _ = blv.parse_args([sub], "/repo")
        # dataset subfolder takes the input folder's name
        self.assertEqual(out, os.path.join("/repo", "output", "LCR", "PF4_polyP"))
        os.rmdir(sub)
        os.rmdir(d)

    def test_default_output_from_single_file_parent(self):
        d = tempfile.mkdtemp()
        sub = os.path.join(d, "polyP")
        os.makedirs(sub)
        f = os.path.join(sub, "run_250.xy")
        open(f, "w").close()
        _, src, out, _ = blv.parse_args([f], "/repo")
        # a single input file -> dataset is its parent folder's name
        self.assertEqual(out, os.path.join("/repo", "output", "LCR", "polyP"))
        os.unlink(f)
        os.rmdir(sub)
        os.rmdir(d)

    def test_explicit_output_dir_overrides_default(self):
        _, src, out, _ = blv.parse_args(["/data/PF4_polyP", "/custom/out"], "/repo")
        self.assertEqual(out, "/custom/out")


class TestSavePostedPreset(unittest.TestCase):
    def test_keeps_only_preset_keys_and_writes(self):
        d = tempfile.mkdtemp()
        blv.save_posted_preset(d, {"scale": 5, "width_mz": 0.07,
                                   "method": "sg", "bogus": 1})
        with open(os.path.join(d, "preset.json")) as fh:
            saved = json.load(fh)
        self.assertEqual(saved["scale"], 5)
        self.assertEqual(saved["width_mz"], 0.07)
        self.assertEqual(saved["method"], "sg")
        self.assertNotIn("bogus", saved)                 # unknown key dropped
        # round-trips through load_preset
        self.assertEqual(blv.load_preset(d)["width_mz"], 0.07)
        os.unlink(os.path.join(d, "preset.json"))
        os.rmdir(d)


class TestServedSavePreset(unittest.TestCase):
    def test_viewer_supports_served_and_standalone_save(self):
        html = blv.build_html([100.0, 100.2], [5.0, 9.0], 123.45,
                              "/*plotly*/", "LCR_mz123_x.html", blv.PRESET, "")
        self.assertIn("location.protocol", html)   # served-mode branch
        self.assertIn("/preset", html)             # POST endpoint
        self.assertIn("showSaveFilePicker", html)  # standalone fallback kept


class TestProcessSpectrum(unittest.TestCase):
    # one peak cluster (parent envelope) and one small charge-reduced cluster
    MZ = [200.0, 200.2, 200.4, 200.6, 260.0, 260.2, 260.4]
    IT = [40.0, 90.0, 50.0, 10.0, 4.0, 6.0, 3.0]

    def test_grid_is_finer_than_raw(self):
        gmz, git, bounds = blv.build_grid(self.MZ, self.IT)
        # interpolation onto a fine grid yields far more points than raw
        self.assertGreater(len(gmz), len(self.MZ))
        self.assertEqual(len(gmz), len(git))
        # two raw clusters -> two grid segments
        self.assertEqual(len(bounds), 2)

    def test_process_returns_paired_arrays(self):
        px, py = blv.process_spectrum(self.MZ, self.IT, 230.0, blv.PRESET)
        self.assertEqual(len(px), len(py))
        self.assertGreater(len(px), 0)

    def test_charge_reduced_region_is_scaled(self):
        # with no smoothing, a grid point above the threshold is x scale
        preset = dict(blv.PRESET, method="none", scale=10)
        px, py = blv.process_spectrum(self.MZ, self.IT, 230.0, preset)
        gmz, git, _ = blv.build_grid(self.MZ, self.IT)
        for i, x in enumerate(gmz):
            if x >= 230.0:
                self.assertAlmostEqual(py[i], git[i] * 10, delta=1e-6)
            else:
                self.assertAlmostEqual(py[i], git[i], delta=1e-6)

    def test_smoothing_changes_the_curve(self):
        raw = dict(blv.PRESET, method="none")
        smooth = dict(blv.PRESET, method="avg", width_mz=0.04)
        _, py_raw = blv.process_spectrum(self.MZ, self.IT, 230.0, raw)
        _, py_sm = blv.process_spectrum(self.MZ, self.IT, 230.0, smooth)
        self.assertNotEqual(py_raw, py_sm)

    def test_scale_off_skips_charge_reduced_scaling(self):
        # MS1 mode: scale_on=False means no point is multiplied even above thr.
        preset = dict(blv.PRESET, method="none", scale=10, scale_on=False)
        px, py = blv.process_spectrum(self.MZ, self.IT, 230.0, preset)
        gmz, git, _ = blv.build_grid(self.MZ, self.IT)
        for i in range(len(gmz)):
            self.assertAlmostEqual(py[i], git[i], delta=1e-6)


class TestBuildCsv(unittest.TestCase):
    def test_header_and_drops_zero_rows(self):
        csv = blv.build_csv([100.0, 100.5, 101.0], [0.0, 7.5, 0.0])
        lines = csv.strip().split("\n")
        self.assertEqual(lines[0], "m/z,intensity_processed")
        # only the positive-intensity point survives
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[1], "100.5,7.5")


if __name__ == "__main__":
    unittest.main()
