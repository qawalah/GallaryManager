"""The file manager: what travels with what, and nothing written over."""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks  # noqa: E402,F401
from app import server as SRV                    # noqa: E402
from core import filesops as F                   # noqa: E402
from core import settings as S                   # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="files-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.share = os.path.join(self.dir, "share")
        self.lib = os.path.join(self.share, "Photos")
        self.raw = os.path.join(self.share, "Photos Raw")
        self.prev = os.path.join(self.share, "Previews")
        self.spain = os.path.join(self.lib, "2022", "Spain")
        self.morocco = os.path.join(self.lib, "2022", "Morocco")
        for where in (self.spain, self.morocco,
                      os.path.join(self.raw, "2022", "Spain"),
                      os.path.join(self.prev, "2022", "Spain")):
            os.makedirs(where)
        shutil.copy(os.path.join(FIX, "rated.jpg"), os.path.join(self.spain, "a.JPG"))
        with open(os.path.join(self.spain, "a.xmp"), "w") as fh:
            fh.write("<x/>")
        with open(os.path.join(self.raw, "2022", "Spain", "a.RW2"), "wb") as fh:
            fh.write(b"raw")
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.prev, "2022", "Spain", "a.jpg"))
        S.save({"library": self.lib, "raw": self.raw, "previews": self.prev})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def bin(self):
        where = os.path.join(self.share, "#recycle")
        os.makedirs(where, exist_ok=True)
        return where


class Listing(Base):
    def test_a_folder_lists_folders_then_files(self):
        got = F.entries(os.path.join(self.lib, "2022"))
        self.assertEqual([f["name"] for f in got["folders"]], ["Morocco", "Spain"])
        self.assertTrue(got["crumbs"])
        self.assertTrue(any(r["path"] == self.raw for r in got["roots"]))

    def test_synology_and_dot_folders_are_out_of_the_way(self):
        os.makedirs(os.path.join(self.spain, "@eaDir"))
        self.assertEqual(F.entries(self.spain)["folders"], [])
        self.assertTrue(F.entries(self.spain, hidden=True)["folders"])

    def test_a_folder_that_is_not_there(self):
        with self.assertRaises(F.Refused):
            F.entries(os.path.join(self.lib, "nope"))


class WhatTravels(Base):
    def test_a_move_takes_the_raw_the_preview_and_the_sidecars(self):
        jobs = F.gather([os.path.join(self.spain, "a.JPG")], self.morocco)
        F.run(jobs, move=True)
        self.assertTrue(os.path.isfile(os.path.join(self.morocco, "a.JPG")))
        self.assertTrue(os.path.isfile(os.path.join(self.morocco, "a.xmp")))
        self.assertTrue(os.path.isfile(
            os.path.join(self.raw, "2022", "Morocco", "a.RW2")))
        self.assertTrue(os.path.isfile(
            os.path.join(self.prev, "2022", "Morocco", "a.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.spain, "a.JPG")))

    def test_and_leaves_them_when_it_is_told_to(self):
        jobs = F.gather([os.path.join(self.spain, "a.JPG")], self.morocco,
                        with_raw=False, with_previews=False)
        self.assertEqual(sorted(os.path.basename(j[0]) for j in jobs),
                         ["a.JPG", "a.xmp"])

    def test_a_copy_leaves_the_original(self):
        jobs = F.gather([os.path.join(self.spain, "a.JPG")], self.morocco)
        got = F.run(jobs, move=False)
        self.assertEqual(got["failed"], 0)
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "a.JPG")))
        self.assertTrue(os.path.isfile(os.path.join(self.morocco, "a.JPG")))

    def test_a_taken_name_is_never_written_over(self):
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.morocco, "a.JPG"))
        was = os.path.getsize(os.path.join(self.morocco, "a.JPG"))
        jobs = F.gather([os.path.join(self.spain, "a.JPG")], self.morocco,
                        with_raw=False, with_previews=False)
        got = F.run(jobs, move=False)
        self.assertEqual(got["renamed"], 1)
        self.assertEqual(os.path.getsize(os.path.join(self.morocco, "a.JPG")), was)
        self.assertTrue(os.path.isfile(os.path.join(self.morocco, "a_1.JPG")))

    def test_a_folder_cannot_be_moved_into_itself(self):
        with self.assertRaises(F.Refused):
            F.gather([self.spain], os.path.join(self.spain, "inner"))

    def test_a_whole_folder_moves(self):
        jobs = F.gather([self.spain], self.morocco)
        F.run(jobs, move=True)
        self.assertTrue(os.path.isfile(
            os.path.join(self.morocco, "Spain", "a.JPG")))

    def test_undo_puts_a_move_back_and_never_over_something_else(self):
        jobs = F.gather([os.path.join(self.spain, "a.JPG")], self.morocco)
        got = F.run(jobs, move=True)
        self.assertEqual(F.undo(got["moves"])["restored"], len(got["moves"]))
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "a.JPG")))
        # and again, with the name taken since
        got = F.run(F.gather([os.path.join(self.spain, "a.JPG")], self.morocco), True)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.spain, "a.JPG"))
        mine = os.path.getsize(os.path.join(self.spain, "a.JPG"))
        F.undo(got["moves"])
        self.assertEqual(os.path.getsize(os.path.join(self.spain, "a.JPG")), mine)


class SmallerThings(Base):
    def test_rename_takes_the_sidecar_with_it(self):
        F.rename(os.path.join(self.spain, "a.JPG"), "beach.JPG")
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "beach.JPG")))
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "beach.xmp")))

    def test_rename_refuses_a_taken_name_or_a_slash(self):
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.spain, "b.JPG"))
        for name in ("b.JPG", "", "up/down", "no:colons"):
            with self.assertRaises(F.Refused, msg=name):
                F.rename(os.path.join(self.spain, "a.JPG"), name)

    def test_a_new_folder_and_not_twice(self):
        F.make_folder(self.spain, "Edits")
        self.assertTrue(os.path.isdir(os.path.join(self.spain, "Edits")))
        with self.assertRaises(F.Refused):
            F.make_folder(self.spain, "Edits")

    def test_delete_goes_to_the_recycle_bin_with_its_raw(self):
        self.bin()
        got = F.delete([os.path.join(self.spain, "a.JPG")], with_raw=True,
                       with_previews=True)
        self.assertFalse(os.path.exists(os.path.join(self.spain, "a.JPG")))
        self.assertFalse(os.path.exists(os.path.join(self.raw, "2022", "Spain", "a.RW2")))
        self.assertEqual(F.undo(got["moves"])["restored"], len(got["moves"]))
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "a.JPG")))

    def test_delete_without_a_bin_is_refused(self):
        with self.assertRaises(F.Refused):
            F.delete([os.path.join(self.spain, "a.JPG")])
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "a.JPG")))


class WhatIsInHere(Base):
    def test_the_dashboard_counts_what_matters(self):
        from core import filesops as FF
        got = FF.status(self.spain)
        self.assertEqual(got["photos"], 1)
        self.assertEqual(got["with_raw"], 1)
        self.assertEqual(got["with_preview"], 1)
        self.assertIn("rated", got)
        self.assertFalse(got["capped"])

    def test_a_folder_that_is_not_there_says_so(self):
        from core import filesops as FF
        with self.assertRaises(FF.Refused):
            FF.status(os.path.join(self.lib, "nope"))


class DeletingFoldersToo(Base):
    def test_a_folder_and_several_files_at_once(self):
        self.bin()
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.spain, "b.JPG"))
        got = F.delete([self.morocco, os.path.join(self.spain, "a.JPG"),
                        os.path.join(self.spain, "b.JPG")],
                       with_raw=True, with_previews=True)
        self.assertFalse(os.path.exists(self.morocco))
        self.assertFalse(os.path.exists(os.path.join(self.spain, "a.JPG")))
        self.assertFalse(os.path.exists(os.path.join(self.spain, "b.JPG")))
        self.assertEqual(F.undo(got["moves"])["restored"], len(got["moves"]))
        self.assertTrue(os.path.isdir(self.morocco))


class NothingWrittenOver(Base):
    """A rename moves the sidecars too, and a sidecar renamed onto one that is
    already there replaces it on a NAS without a word."""

    def setUp(self):
        super().setUp()
        self.neg = os.path.join(self.spain, "x.RW2")
        with open(self.neg, "wb") as fh:
            fh.write(b"raw")
        with open(os.path.join(self.spain, "x.xmp"), "w") as fh:
            fh.write("<x stars='1'/>")
        with open(os.path.join(self.spain, "b.xmp"), "w") as fh:
            fh.write("<b stars='5'/>")

    def test_a_rename_onto_a_taken_sidecar_is_refused_and_touches_nothing(self):
        with self.assertRaises(F.Refused):
            F.rename(self.neg, "b.RW2")
        self.assertTrue(os.path.isfile(self.neg))
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "x.xmp")))
        with open(os.path.join(self.spain, "b.xmp")) as fh:
            self.assertIn("stars='5'", fh.read())

    def test_a_rename_hands_back_every_move_it_made(self):
        got = F.rename(self.neg, "y.RW2")
        self.assertEqual(sorted(os.path.basename(m[1]) for m in got["moves"]),
                         ["y.RW2", "y.xmp"])


class DeletingAllOrNothing(Base):
    def test_a_partner_on_a_share_without_a_bin_refuses_before_anything_moves(self):
        """The JPEG went into the bin and the RAW could not follow: a 409, no
        record, and the photograph missing from the library."""
        self.bin()
        other = os.path.join(self.dir, "other", "Raw")
        os.makedirs(os.path.join(other, "2022", "Spain"))
        with open(os.path.join(other, "2022", "Spain", "a.RW2"), "wb") as fh:
            fh.write(b"raw")
        S.save({"raw": other})
        with self.assertRaises(F.Refused):
            F.delete([os.path.join(self.spain, "a.JPG")], with_raw=True)
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "a.JPG")))
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "a.xmp")))

    def test_a_failure_part_way_hands_back_what_had_already_moved(self):
        from unittest import mock
        from core import moves as M
        self.bin()
        real, calls = M.shift, []

        def flaky(book, src, dst, **kw):
            calls.append(src)
            if len(calls) == 2:
                raise OSError(5, "Input/output error")
            return real(book, src, dst, **kw)

        with mock.patch.object(F.M, "shift", side_effect=flaky):
            with self.assertRaises(F.Partly) as got:
                F.delete([os.path.join(self.spain, "a.JPG")])
        self.assertEqual(len(got.exception.moves), 1)
        self.assertTrue(os.path.isfile(got.exception.moves[0][1]))


class FoldersCarryTheirMirrors(Base):
    def test_moving_a_shoot_moves_its_raw_and_previews_folders(self):
        jobs = F.gather([self.spain], self.morocco)
        self.assertEqual(len(jobs), 3, jobs)
        F.run(jobs, move=True)
        self.assertTrue(os.path.isfile(
            os.path.join(self.morocco, "Spain", "a.JPG")))
        self.assertTrue(os.path.isfile(
            os.path.join(self.raw, "2022", "Morocco", "Spain", "a.RW2")))
        self.assertTrue(os.path.isfile(
            os.path.join(self.prev, "2022", "Morocco", "Spain", "a.jpg")))
        self.assertFalse(os.path.exists(os.path.join(self.raw, "2022", "Spain")))

    def test_and_can_be_told_not_to(self):
        jobs = F.gather([self.spain], self.morocco, with_raw=False,
                        with_previews=False)
        self.assertEqual(len(jobs), 1)

    def test_a_folder_moved_out_of_its_tree_takes_nothing_with_it(self):
        elsewhere = os.path.join(self.dir, "elsewhere")
        os.makedirs(elsewhere)
        self.assertEqual(len(F.gather([self.spain], elsewhere)), 1)


class OverHttp(Base):
    def setUp(self):
        super().setUp()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        SRV.ALLOWED_ROOTS.clear()
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as f:
            return json.load(f)

    def post(self, obj):
        req = urllib.request.Request(self.base + "api/files",
                                     json.dumps(obj).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as f:
            return json.load(f)

    def test_listing_over_http(self):
        got = self.get("api/files?path=" + urllib.parse.quote(self.spain))
        self.assertEqual(sorted(f["name"] for f in got["files"]), ["a.JPG", "a.xmp"])

    def test_outside_the_allowed_folders_is_refused(self):
        SRV.ALLOWED_ROOTS.append(os.path.realpath(self.raw))
        with self.assertRaises(urllib.error.HTTPError) as got:
            self.get("api/files?path=" + urllib.parse.quote(self.spain))
        self.assertEqual(got.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as got:
            self.post({"do": "mkdir", "into": self.spain, "name": "x"})
        self.assertEqual(got.exception.code, 403)

    def test_a_copy_runs_in_the_background_and_says_when_it_is_done(self):
        import time
        started = self.post({"do": "copy", "paths": [os.path.join(self.spain, "a.JPG")],
                             "into": self.morocco})
        self.assertTrue(started["id"])
        for _ in range(100):
            state = self.get("api/files/progress?id=" + started["id"])
            if state["finished"]:
                break
            time.sleep(0.05)
        self.assertTrue(state["finished"])
        self.assertEqual(state["result"]["failed"], 0)
        self.assertTrue(os.path.isfile(os.path.join(self.morocco, "a.JPG")))

    def test_the_dashboard_over_http(self):
        got = self.get("api/folder-status?path=" + urllib.parse.quote(self.spain))
        self.assertEqual(got["photos"], 1)

    def test_a_download_comes_back_as_an_attachment(self):
        url = self.base + "api/download?path=" + urllib.parse.quote(
            os.path.join(self.spain, "a.JPG"))
        with urllib.request.urlopen(url) as f:
            self.assertIn("attachment", f.headers.get("Content-Disposition", ""))
            self.assertTrue(len(f.read()) > 100)

    def test_the_run_is_in_history(self):
        from core import runlog
        self.post({"do": "mkdir", "into": self.spain, "name": "Edits"})
        got = self.post({"do": "delete", "paths": [os.path.join(self.spain, "a.xmp")]}) \
            if os.path.isdir(os.path.join(self.share, "#recycle")) else None
        self.assertIsNone(got)             # no bin here, so nothing to log yet
        self.bin()
        self.post({"do": "delete", "paths": [os.path.join(self.spain, "a.xmp")]})
        self.assertTrue(any(r.get("task") == "files" for r in runlog.recent(10)))


    def wait(self, started):
        import time
        for _ in range(200):
            state = self.get("api/files/progress?id=" + started["id"])
            if state["finished"]:
                return state
            time.sleep(0.05)
        self.fail("the file job never finished")

    def test_a_delete_reaches_history_with_its_moves_so_it_can_be_put_back(self):
        from core import runlog
        from app import registry as R
        self.bin()
        self.post({"do": "delete", "paths": [os.path.join(self.spain, "a.JPG")]})
        last = runlog.recent(1)[0]
        self.assertTrue(last["moves"])
        p = R.get("undo").make_plan({"no": last["no"]})
        self.assertFalse(p.blocked, p.blocked)
        self.assertTrue(p.rows)

    def test_a_move_reaches_history_with_its_moves(self):
        from core import runlog
        started = self.post({"do": "move", "into": self.morocco,
                             "paths": [os.path.join(self.spain, "a.JPG")]})
        self.wait(started)
        last = runlog.recent(1)[0]
        self.assertEqual(last["action"], "move")
        self.assertTrue(last["moves"])

    def test_a_rename_reaches_history_with_its_moves(self):
        from core import runlog
        self.post({"do": "rename", "path": os.path.join(self.spain, "a.JPG"),
                   "name": "beach.JPG"})
        last = runlog.recent(1)[0]
        self.assertEqual(last["task"], "rename")
        self.assertEqual(len(last["moves"]), 2)

    def test_a_delete_that_stops_part_way_still_records_what_moved(self):
        from unittest import mock
        from core import moves as M
        from core import runlog
        self.bin()
        real, calls = M.shift, []

        def flaky(book, src, dst, **kw):
            calls.append(src)
            if len(calls) == 2:
                raise OSError(5, "Input/output error")
            return real(book, src, dst, **kw)

        with mock.patch.object(F.M, "shift", side_effect=flaky):
            with self.assertRaises(urllib.error.HTTPError) as got:
                self.post({"do": "delete",
                           "paths": [os.path.join(self.spain, "a.JPG")]})
        self.assertEqual(got.exception.code, 409)
        self.assertEqual(len(json.load(got.exception)["moves"]), 1)
        self.assertEqual(len(runlog.recent(1)[0]["moves"]), 1)


if __name__ == "__main__":
    unittest.main()
