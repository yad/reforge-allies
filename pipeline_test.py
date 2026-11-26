import ctypes
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import clean_hd
import execution_log
import extract_mpq
import extract_races
import merge_races


ROOT = Path(__file__).resolve().parent


class ExecutionLogTests(unittest.TestCase):
    def test_pipeline_resets_once_and_keeps_repeated_script_invocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "Logs"
            logs.mkdir()
            (logs / "stale").mkdir()
            (logs / "stale/old.log").write_text("previous pipeline")
            with patch.object(execution_log, "LOG_DIR", logs), \
                    patch.dict(os.environ, {execution_log.PIPELINE_ENV: "1"}), \
                    patch("sys.stdout", new_callable=io.StringIO) as console:
                execution_log.reset_logs()
                execution_log.run_logged(lambda: print("coa"), "extract_mpq.py")
                execution_log.run_logged(lambda: print("hd"), "extract_mpq.py")
                execution_log.run_logged(lambda: print("merged"), "merge_races.py")
                self.assertEqual(console.getvalue(), "coa\nhd\nmerged\n")
                self.assertEqual({p.name for p in logs.iterdir()},
                                 {"extract_mpq.log", "merge_races.log"})
                text = (logs / "extract_mpq.log").read_text(encoding="utf-8")
                self.assertIn("coa\n", text)
                self.assertIn("hd\n", text)
                self.assertEqual(text.count("=== extract_mpq.py ==="), 2)
                execution_log.reset_logs()
                self.assertEqual(list(logs.iterdir()), [])

    def test_standalone_keeps_console_output_and_records_uncaught_errors(self):
        def fail():
            print("sortie accentuée")
            print("warning", file=sys.stderr)
            raise ValueError("execution failed")

        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp) / "Logs"
            with patch.object(execution_log, "LOG_DIR", logs), \
                    patch.dict(os.environ, {execution_log.PIPELINE_ENV: "0"}), \
                    patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                    patch("sys.stderr", new_callable=io.StringIO) as stderr:
                execution_log.run_logged(lambda: print("old output"), "old.py")
                with self.assertRaisesRegex(ValueError, "execution failed"):
                    execution_log.run_logged(fail, "failure.py")
                self.assertEqual({p.name for p in logs.iterdir()}, {"failure.log"})
                text = (logs / "failure.log").read_text(encoding="utf-8")
                self.assertIn("sortie accentuée\n", text)
                self.assertIn("warning\n", text)
                self.assertIn("ValueError: execution failed", text)
                self.assertEqual(text.count("Traceback"), 1)
                self.assertEqual(stdout.getvalue(), "old output\nsortie accentuée\n")
                self.assertEqual(stderr.getvalue(), "warning\n")

    def test_system_exit_message_and_status_are_not_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(execution_log, "LOG_DIR", Path(tmp) / "Logs"), \
                patch.dict(os.environ, {execution_log.PIPELINE_ENV: "0"}):
            for code in ("invalid configuration", 2, 0):
                with self.subTest(code=code), self.assertRaises(SystemExit) as exc:
                    execution_log.run_logged(lambda: sys.exit(code), "exit.py")
                self.assertEqual(exc.exception.code, code)
                text = (Path(tmp) / "Logs/exit.log").read_text(encoding="utf-8")
                if code == 0:
                    self.assertNotIn("[exit]", text)
                else:
                    self.assertIn(f"[exit] {code if isinstance(code, int) else 1}", text)
                    if isinstance(code, str):
                        self.assertIn(code, text)

    def test_cli_entry_points_log_help_and_tracebacks_from_another_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = ("clean_hd.py", "extract_mpq.py", "extract_races.py", "merge_races.py")
            for name in (*scripts, "execution_log.py", "race_assets.py", "race_images.py"):
                shutil.copy2(ROOT / name, root / name)
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            env = dict(os.environ, REFORGE_PIPELINE_LOGS="1", PYTHONIOENCODING="utf-8")

            def run(script, *args):
                return subprocess.run([sys.executable, str(root / script), *args],
                                      cwd=elsewhere, env=env, capture_output=True,
                                      text=True, encoding="utf-8", timeout=30)

            self.assertEqual(run("execution_log.py").returncode, 0)
            for script in (*scripts, "extract_mpq.py"):
                result = run(script, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
                self.assertIn(result.stdout, (root / "Logs" / (Path(script).stem + ".log"))
                              .read_text(encoding="utf-8"))
            failed = run("merge_races.py", "--config", "missing-config.json")
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(failed.stderr.count("Traceback"), 1)
            text = (root / "Logs/merge_races.log").read_text(encoding="utf-8")
            self.assertIn("usage:", text)
            self.assertIn("FileNotFoundError", text)
            self.assertEqual(text.count("Traceback"), 1)


class MPQExtractionTests(unittest.TestCase):
    @staticmethod
    def _archive_with_entries(entries):
        entries = list(entries)
        dll, error = Mock(), [18]
        dll.SFileOpenArchive.return_value = True
        dll.SFileOpenFileEx.return_value = True

        def advance(_handle, data):
            if not entries:
                error[0] = 18
                return False
            data._obj.cFileName, data._obj.dwFileSize = entries.pop(0)
            return True

        dll.SFileFindFirstFile.side_effect = lambda handle, pattern, data, listfile: advance(handle, data)
        dll.SFileFindNextFile.side_effect = advance
        return dll, error

    def test_native_boolean_result_ignores_undefined_high_bytes(self):
        result = [0x100]
        native_next = ctypes.CFUNCTYPE(
            ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(extract_mpq.SFILE_FIND_DATA)
        )(lambda *_: result[0])
        dll = Mock(SFileFindNextFile=native_next)
        with patch.object(extract_mpq.sys, "platform", "win32"), \
                patch.object(extract_mpq.os.path, "isfile", return_value=True), \
                patch.object(ctypes, "WinDLL", return_value=dll, create=True):
            bound = extract_mpq.load_storm()
        data = extract_mpq.SFILE_FIND_DATA()
        self.assertFalse(bound.SFileFindNextFile(None, ctypes.byref(data)))
        result[0] = 0x101
        self.assertTrue(bound.SFileFindNextFile(None, ctypes.byref(data)))

    def test_multiple_profiles_stop_after_the_first_failure(self):
        with patch("sys.argv", ["extract_mpq.py"]), patch.object(extract_mpq, "load_storm"), \
                patch.object(extract_mpq, "run_profile", side_effect=[False, True]) as run, \
                self.assertRaises(SystemExit) as exc:
            extract_mpq.main()
        self.assertEqual(exc.exception.code, 1)
        self.assertEqual(run.call_count, 1)

    def test_unknown_profile_is_rejected_before_loading_native_library(self):
        with patch("sys.argv", ["extract_mpq.py", "unknown"]), \
                patch.object(extract_mpq, "load_storm") as load, \
                patch("sys.stderr", new_callable=io.StringIO), \
                self.assertRaises(SystemExit) as exc:
            extract_mpq.main()
        self.assertEqual(exc.exception.code, 2)
        load.assert_not_called()

    def test_legacy_caches_do_not_bypass_file_retries(self):
        for prefix in ("", "v2:"):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as tmp:
                archive, out = Path(tmp) / "old.mpq", Path(tmp) / "out"
                archive.write_bytes(b"mpq")
                out.mkdir()
                stat = archive.stat()
                (out / extract_mpq.MARKER).write_text(
                    f"{prefix}{stat.st_size}:{stat.st_mtime_ns}\ndata.bin", encoding="utf-8")
                dll = Mock()
                dll.SFileOpenArchive.return_value = False
                with patch.object(ctypes, "get_last_error", return_value=5, create=True), \
                        self.assertRaises(OSError):
                    extract_mpq.extract_archive(dll, str(archive), str(out), False)
                dll.SFileOpenArchive.assert_called_once()

    def test_complete_archive_is_extracted_and_then_reused_from_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "good.mpq", Path(tmp) / "out"
            archive.write_bytes(b"mpq")
            dll = Mock()
            dll.SFileOpenArchive.return_value = True
            dll.SFileOpenFileEx.return_value = True

            def first(_archive, _pattern, data, _listfile):
                data._obj.cFileName = b"folder\\data.bin"
                data._obj.dwFileSize = 3
                return 1

            def read(_handle, buffer, _size, count, _overlapped):
                ctypes.memmove(buffer, b"abc", 3)
                count._obj.value = 3
                return True

            dll.SFileFindFirstFile.side_effect = first
            dll.SFileReadFile.side_effect = read
            dll.SFileFindNextFile.return_value = False
            expected = [os.path.join("folder", "data.bin")]
            with patch.object(ctypes, "get_last_error", return_value=18, create=True):
                self.assertEqual(extract_mpq.extract_archive(dll, str(archive), str(out), False),
                                 (expected, 1, 0, False))
                self.assertEqual((out / "folder/data.bin").read_bytes(), b"abc")
                self.assertEqual(extract_mpq.extract_archive(dll, str(archive), str(out), False),
                                 (expected, 0, 0, True))
            dll.SFileOpenArchive.assert_called_once()

    def test_failed_files_are_retried_then_reported_without_blocking_healthy_files(self):
        for bad in (br"Interface\\FrameXML\\QuestFrame.lua", br"interface\\framexml\\questframe.lua",
                    br"World of Warcraft.app\Contents\Resources\Error Reporter.app"
                    br"\Contents\Resources\English.lproj\MainMenu.nib\keyedobjects.nib", b"broken.blp"):
            with self.subTest(entry=bad), tempfile.TemporaryDirectory() as tmp:
                archive, out = Path(tmp) / "source.mpq", Path(tmp) / "out"
                archive.write_bytes(b"mpq")
                healthy = [br"Interface\FrameXML\QuestFrame.lua", b"data.bin"]
                dll, error = self._archive_with_entries([(name, 2) for name in [bad, *healthy]])
                state = {}

                def open_file(_archive, name, _scope, _handle):
                    state.update(name=name, reads=0)
                    return True

                def read(_handle, buffer, _size, count, _overlapped):
                    state["reads"] += 1
                    if state["name"] == bad and state["reads"] > 1:
                        error[0] = 1392
                        return False
                    payload = (b"xx" if state["name"] == bad else b"ok") if state["reads"] == 1 else b""
                    ctypes.memmove(buffer, payload, len(payload))
                    count._obj.value = len(payload)
                    return True

                dll.SFileOpenFileEx.side_effect = open_file
                dll.SFileReadFile.side_effect = read
                expected = [os.path.join("Interface", "FrameXML", "QuestFrame.lua"), "data.bin"]
                with patch.object(ctypes, "get_last_error", side_effect=lambda: error[0], create=True), \
                        patch.object(extract_mpq, "CHUNK", 2), \
                        patch("sys.stdout", new_callable=io.StringIO) as console:
                    self.assertEqual(extract_mpq.extract_archive(dll, str(archive), str(out), False),
                                     (expected, 2, 1, False))
                self.assertEqual([call.args[1] for call in dll.SFileOpenFileEx.call_args_list],
                                 [bad, bad, bad, *healthy])
                self.assertEqual(dll.SFileCloseFile.call_count, 5)
                self.assertIn("[anomalie]", console.getvalue())
                self.assertIn("3/3", console.getvalue())
                self.assertIn(repr(bad), console.getvalue())
                self.assertIn(str(archive), console.getvalue())
                self.assertFalse((out / extract_mpq.MARKER).exists())
                self.assertEqual((out / expected[0]).read_bytes(), b"ok")
                self.assertEqual((out / "data.bin").read_bytes(), b"ok")
                if bad == b"broken.blp":
                    self.assertFalse((out / "broken.blp").exists())
                dll.SFileFindClose.assert_called_once()
                dll.SFileCloseArchive.assert_called_once()

    def test_transient_read_failure_restarts_the_file_and_then_caches_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "source.mpq", Path(tmp) / "out"
            archive.write_bytes(b"mpq")
            dll, error = self._archive_with_entries([(b"data.bin", 4)])
            chunks = [b"old", None, b"new", b"!"]

            def read(_handle, buffer, _size, count, _overlapped):
                payload = chunks.pop(0)
                if payload is None:
                    error[0] = 1392
                    return False
                ctypes.memmove(buffer, payload, len(payload))
                count._obj.value = len(payload)
                return True

            dll.SFileReadFile.side_effect = read
            with patch.object(ctypes, "get_last_error", side_effect=lambda: error[0], create=True), \
                    patch.object(extract_mpq, "CHUNK", 3), \
                    patch("sys.stdout", new_callable=io.StringIO) as console:
                self.assertEqual(extract_mpq.extract_archive(dll, str(archive), str(out), False),
                                 (["data.bin"], 1, 0, False))
            self.assertEqual((out / "data.bin").read_bytes(), b"new!")
            self.assertEqual(dll.SFileOpenFileEx.call_count, 2)
            self.assertEqual(dll.SFileCloseFile.call_count, 2)
            self.assertIn("[retry]", console.getvalue())
            self.assertNotIn("[anomalie]", console.getvalue())
            self.assertTrue((out / extract_mpq.MARKER).exists())

    def test_truncated_files_are_retried_and_removed_after_three_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "source.mpq", Path(tmp) / "out"
            archive.write_bytes(b"mpq")
            dll, error = self._archive_with_entries([(b"data.bin", 3)])

            def read(_handle, buffer, _size, count, _overlapped):
                ctypes.memmove(buffer, b"ab", 2)
                count._obj.value = 2
                return True

            dll.SFileReadFile.side_effect = read
            with patch.object(ctypes, "get_last_error", side_effect=lambda: error[0], create=True), \
                    patch("sys.stdout", new_callable=io.StringIO) as console:
                self.assertEqual(extract_mpq.extract_archive(dll, str(archive), str(out), False),
                                 ([], 0, 1, False))
            self.assertEqual(dll.SFileOpenFileEx.call_count, 3)
            self.assertEqual(dll.SFileCloseFile.call_count, 3)
            self.assertFalse((out / "data.bin").exists())
            self.assertFalse((out / extract_mpq.MARKER).exists())
            self.assertIn("[anomalie]", console.getvalue())

    def test_source_open_failure_is_retried_three_times_without_caching(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "source.mpq", Path(tmp) / "out"
            archive.write_bytes(b"mpq")
            dll, error = self._archive_with_entries([(b"data.bin", 3)])
            dll.SFileOpenFileEx.return_value = False
            error[0] = 1392
            with patch.object(ctypes, "get_last_error", side_effect=lambda: error[0], create=True), \
                    patch("sys.stdout", new_callable=io.StringIO) as console:
                self.assertEqual(extract_mpq.extract_archive(dll, str(archive), str(out), False),
                                 ([], 0, 1, False))
            self.assertEqual(dll.SFileOpenFileEx.call_count, 3)
            dll.SFileReadFile.assert_not_called()
            dll.SFileCloseFile.assert_not_called()
            self.assertFalse((out / extract_mpq.MARKER).exists())
            self.assertIn("[anomalie]", console.getvalue())

    def test_normalized_alias_cannot_overwrite_a_successful_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "source.mpq", Path(tmp) / "out"
            archive.write_bytes(b"mpq")
            names = [br"Interface\FrameXML\QuestFrame.lua", br"Interface\\FrameXML\\QuestFrame.lua"]
            dll, error = self._archive_with_entries([(name, 3) for name in names])

            def read(_handle, buffer, _size, count, _overlapped):
                ctypes.memmove(buffer, b"abc", 3)
                count._obj.value = 3
                return True

            dll.SFileReadFile.side_effect = read
            relative = os.path.join("Interface", "FrameXML", "QuestFrame.lua")
            with patch.object(ctypes, "get_last_error", side_effect=lambda: error[0], create=True):
                self.assertEqual(extract_mpq.extract_archive(dll, str(archive), str(out), False),
                                 ([relative], 1, 0, False))
            dll.SFileOpenFileEx.assert_called_once()
            self.assertEqual((out / relative).read_bytes(), b"abc")

    def test_local_write_errors_remain_fatal_instead_of_skipping_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "source.mpq", Path(tmp) / "out"
            archive.write_bytes(b"mpq")
            dll, _ = self._archive_with_entries([(b"data.bin", 3)])
            with patch("builtins.open", side_effect=PermissionError("destination not writable")), \
                    self.assertRaises(PermissionError):
                extract_mpq.extract_archive(dll, str(archive), str(out), False)
            dll.SFileOpenFileEx.assert_called_once()
            dll.SFileCloseFile.assert_called_once()
            dll.SFileFindClose.assert_called_once()
            dll.SFileCloseArchive.assert_called_once()
            self.assertFalse((out / extract_mpq.MARKER).exists())

    def test_profile_merges_healthy_files_with_an_explicit_anomaly_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data, out, patchs = root / "Data", root / "merged", root / "patchs"
            data.mkdir()
            (data / "common.mpq").write_bytes(b"mpq")
            dll, error = self._archive_with_entries([(b"broken.blp", 3), (b"healthy.blp", 3)])

            def open_file(_archive, name, _scope, _handle):
                error[0] = 1392
                return name == b"healthy.blp"

            def read(_handle, buffer, _size, count, _overlapped):
                ctypes.memmove(buffer, b"abc", 3)
                count._obj.value = 3
                return True

            dll.SFileOpenFileEx.side_effect = open_file
            dll.SFileReadFile.side_effect = read
            args = SimpleNamespace(data_dir=str(data), dest_root=None, patchs_dir=str(patchs),
                                   out_dir=str(out), list=False, ignore=[], ignore_file=[],
                                   force=False, workers=1, copy=True, find=None)
            with patch.object(extract_mpq, "CWD", str(root)), \
                    patch.object(ctypes, "get_last_error", side_effect=lambda: error[0], create=True), \
                    patch("sys.stdout", new_callable=io.StringIO) as console:
                self.assertTrue(extract_mpq.run_profile(dll, "hd", args))
            self.assertEqual((out / "healthy.blp").read_bytes(), b"abc")
            self.assertFalse((out / "broken.blp").exists())
            self.assertFalse((patchs / "01_common" / extract_mpq.MARKER).exists())
            self.assertIn("[anomalie] Profil hd : 1 fichiers", console.getvalue())
            self.assertIn("fusion potentiellement incomplète", console.getvalue())

    def test_read_errors_and_truncation_are_not_successful_extractions(self):
        for ok, error, expected, exception in ((False, 23, 3, OSError),
                                                (False, 1392, 3, OSError),
                                                (False, 38, 4, extract_mpq.MPQFileError),
                                                (False, 38, 3, None),
                                                (True, 0, 3, None)):
            with self.subTest(ok=ok, error=error, expected=expected), tempfile.TemporaryDirectory() as tmp:
                dll = Mock()
                dll.SFileOpenFileEx.return_value = True

                def read(_handle, buffer, _size, count, _overlapped):
                    ctypes.memmove(buffer, b"abc", 3)
                    count._obj.value = 3
                    return ok

                dll.SFileReadFile.side_effect = read
                dest = Path(tmp) / "data.bin"
                with patch.object(ctypes, "get_last_error", return_value=error, create=True), \
                        patch.object(ctypes, "string_at", side_effect=AssertionError("unnecessary buffer copy")):
                    if exception:
                        with self.assertRaises(exception):
                            extract_mpq.extract_file(dll, None, b"data.bin", str(dest), set(), expected)
                    else:
                        self.assertTrue(extract_mpq.extract_file(
                            dll, None, b"data.bin", str(dest), set(), expected))
                        self.assertEqual(dest.read_bytes(), b"abc")
                dll.SFileCloseFile.assert_called_once()

    def test_failed_archive_open_preserves_existing_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "bad.mpq", Path(tmp) / "out"
            archive.write_bytes(b"bad")
            out.mkdir()
            (out / "keep.txt").write_text("previous data")
            dll = Mock()
            dll.SFileOpenArchive.return_value = False
            with patch.object(ctypes, "get_last_error", return_value=5, create=True), \
                    self.assertRaises(OSError):
                extract_mpq.extract_archive(dll, str(archive), str(out), False)
            self.assertEqual((out / "keep.txt").read_text(), "previous data")
            self.assertFalse((out / extract_mpq.MARKER).exists())

    def test_failed_enumeration_is_not_cached_and_closes_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive, out = Path(tmp) / "bad.mpq", Path(tmp) / "out"
            archive.write_bytes(b"bad")
            dll = Mock()
            dll.SFileOpenArchive.return_value = True

            def first(_archive, _pattern, data, _listfile):
                data._obj.cFileName = b"data.bin"
                data._obj.dwFileSize = 3
                return 1

            dll.SFileFindFirstFile.side_effect = first
            dll.SFileFindNextFile.return_value = False
            with patch.object(ctypes, "get_last_error", return_value=23, create=True), \
                    patch.object(extract_mpq, "extract_file"), self.assertRaises(OSError):
                extract_mpq.extract_archive(dll, str(archive), str(out), False)
            self.assertFalse((out / extract_mpq.MARKER).exists())
            dll.SFileFindClose.assert_called_once()
            dll.SFileCloseArchive.assert_called_once()

    def test_cache_detects_same_size_changes_within_one_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patch.mpq"
            path.write_bytes(b"old")
            os.utime(path, ns=(1700000000100000000, 1700000000100000000))
            before = extract_mpq.signature(path)
            path.write_bytes(b"new")
            os.utime(path, ns=(1700000000900000000, 1700000000900000000))
            self.assertNotEqual(extract_mpq.signature(path), before)

    def test_archive_paths_cannot_write_outside_the_extraction(self):
        for name in (br"..\escape.bin", br"folder\\..\escape.bin", br"\absolute.bin",
                     br"\\server\share\file.bin", br"C:\escape.bin"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive, out = Path(tmp) / "bad.mpq", Path(tmp) / "out"
                archive.write_bytes(b"bad")
                dll, _ = self._archive_with_entries([(name, 3)])
                with patch.object(extract_mpq, "extract_file") as extract, \
                        self.assertRaisesRegex(ValueError, "Chemin"):
                    extract_mpq.extract_archive(dll, str(archive), str(out), False)
                extract.assert_not_called()
                self.assertFalse((out / extract_mpq.MARKER).exists())
                dll.SFileFindClose.assert_called_once()
                dll.SFileCloseArchive.assert_called_once()


class PipelineIOTests(unittest.TestCase):
    def test_resource_index_accepts_merged_and_layered_hd_outputs(self):
        for layout in ("merged", "layered"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                hd = root / "01-HD"
                source = hd if layout == "merged" else hd / "patch-A.mpq"
                texture = source / "Textures/Example.blp"
                texture.parent.mkdir(parents=True)
                texture.write_bytes(b"texture")
                (root / "base").mkdir()
                (root / "races").mkdir()
                idx, unavailable = merge_races.index_pipeline_assets(
                    root, {"base": "base", "races_dir": "races"})
                self.assertIn("textures/example.blp", idx)
                self.assertEqual(unavailable, [])

    def test_scaled_background_uses_merged_hd_source_without_altering_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "01-HD/Interface/Glues/Models/ui_human_zoom"
            source.mkdir(parents=True)
            data = bytearray(400)
            data[:4] = b"MD20"
            struct.pack_into("<I", data, 4, 264)
            struct.pack_into("<II", data, 272, 1, 280)
            for offset in (316, 348):
                struct.pack_into("<3f", data, offset, 4, 8, 12)
            model = source / "ui_human_zoom.m2"
            model.write_bytes(data)
            (source / "ui_human_zoom00.skin").write_bytes(b"skin")
            out = root / "out"
            self.assertTrue(merge_races.make_scaled_zoom_background(
                root, out, [], "Human", "Custom", .5))
            target = out / "Interface/Glues/Models/ui_custom_zoom"
            scaled = (target / "ui_custom_zoom.m2").read_bytes()
            for offset in (316, 348):
                self.assertEqual(struct.unpack_from("<3f", scaled, offset), (2, 4, 6))
            self.assertEqual((target / "ui_custom_zoom00.skin").read_bytes(), b"skin")
            self.assertEqual(model.read_bytes(), data)

    def test_numbered_layers_keep_numeric_priority_and_support_explicit_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("99_patch-Z", "100_patch-Z-2"):
                (root / name).mkdir()
            self.assertEqual([p.name for p in clean_hd.find_mpq_dirs(root, [])],
                             ["99_patch-Z", "100_patch-Z-2"])
            self.assertEqual([p.name for p in clean_hd.find_mpq_dirs(root, ["Z-2", "Z"])],
                             ["100_patch-Z-2", "99_patch-Z"])

    def test_dbc_report_reads_only_the_header(self):
        header = b"WDBC" + struct.pack("<4I", 1, 1, 4, 1)
        sizes = []

        class Reader(io.BytesIO):
            def read(self, size=-1):
                sizes.append(size)
                return super().read(size)

        with patch.object(Path, "open", return_value=Reader(header + b"\0" * 5)), \
                patch.object(Path, "stat", return_value=SimpleNamespace(st_size=25)):
            self.assertEqual(clean_hd.dbc_info(Path("table.dbc")), (1, 1))
        self.assertEqual(sizes, [20])

    def test_exact_case_lookup_avoids_directory_scans_and_keeps_case_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Assets").mkdir()
            target = root / "Assets/File.dbc"
            target.write_bytes(b"data")
            with patch.object(Path, "iterdir", side_effect=AssertionError("unnecessary directory scan")):
                self.assertEqual(merge_races.ci_find(root, "Assets/File.dbc"), target)
            self.assertTrue(merge_races.ci_find(root, "assets/file.dbc").samefile(target))
            self.assertIsNone(merge_races.ci_find(root, "../outside"))

    def test_cleaning_and_extraction_reject_overlapping_output_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            keep = source / "keep.txt"
            keep.write_text("data")
            with patch("sys.argv", ["clean_hd.py", "--src", str(source), "--dst", str(root)]), \
                    self.assertRaisesRegex(ValueError, "non imbriqu"):
                clean_hd.main()
            args = SimpleNamespace(data_dir=str(source), dest_root=None, patchs_dir=str(source / "patchs"),
                                   out_dir=str(root / "out"), list=False)
            with patch("sys.stdout", new_callable=io.StringIO), \
                    self.assertRaisesRegex(ValueError, "non imbriqu"):
                extract_mpq.run_profile(None, "hd", args)
            self.assertEqual(keep.read_text(), "data")

    def test_race_extraction_cannot_replace_its_own_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "53-Ogre"
            shutil.copytree(ROOT / "03-Races/53-Ogre/DBFilesClient", source / "DBFilesClient")
            keep = source / "keep.txt"
            keep.write_text("data")
            argv = ["extract_races.py", "--src", str(source), "--dst", str(root),
                    "--portraits-src", str(ROOT / "Icons")]
            with patch("sys.argv", argv), patch("sys.stdout", new_callable=io.StringIO), \
                    self.assertRaisesRegex(ValueError, "non imbriqu"):
                extract_races.main()
            self.assertEqual(keep.read_text(), "data")

    def test_merge_refuses_to_delete_any_configured_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("base", "races", "library", "glue"):
                (root / name).mkdir()
                (root / name / "keep.txt").write_text("data")
            for output in ("races", "library", "glue"):
                cfg = {"base": "base", "races_dir": "races", "output": output,
                       "glue_source": "glue", "asset_roots": ["library"]}
                path = root / "config.json"
                path.write_text(json.dumps(cfg))
                with self.subTest(output=output), patch("sys.argv", ["merge_races.py", "--config", str(path)]), \
                        self.assertRaisesRegex(ValueError, "non imbriqu"):
                    merge_races.main()
                self.assertEqual((root / output / "keep.txt").read_text(), "data")


if __name__ == "__main__":
    execution_log.run_logged(unittest.main, __file__)
