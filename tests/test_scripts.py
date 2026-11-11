"""Run check.py, board.py and act.py against the fake Bugsink. Standard library only.

  python3 -m unittest discover -s tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mock_bugsink as mock  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent.parent / "skills/bugsink-triage/scripts"
FIRST = "aaaaaaaa-0000-0000-0000-000000000001"


class ScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.url = mock.serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        mock.reset()

    def run_script(self, name, *args, token=mock.TOKEN, extra_env=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("BUGSINK_")}
        env.update(BUGSINK_URL=self.url, BUGSINK_TRIAGE_TOKEN=token, **(extra_env or {}))
        if name != "act.py":
            env["BUGSINK_TOKEN"] = token
        return subprocess.run([sys.executable, str(SCRIPTS / name), *args], capture_output=True, text=True, env=env, timeout=60)

    def test_check_lists_open_issues_only(self):
        r = self.run_script("check.py", "--all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DEMO-WEB-1", r.stdout)
        self.assertIn("DEMO-API-1", r.stdout)
        self.assertNotIn("DEMO-WEB-2", r.stdout)  # resolved
        self.assertIn("MUTED", r.stdout)
        self.assertIn("Total: 2", r.stdout)
        self.assertIn("component=checkout", r.stdout)
        self.assertNotIn("secret.tag", r.stdout)  # not in the tag list
        self.assertNotIn(mock.TOKEN, r.stdout + r.stderr)

    def test_check_project_filter_and_custom_tags(self):
        r = self.run_script("check.py", "--all", "--project", "demo-web", extra_env={"BUGSINK_TAGS": "secret.tag"})
        self.assertIn("Total: 1", r.stdout)
        self.assertIn("secret.tag=hidden", r.stdout)
        self.assertIn("src/cart.js:42", r.stdout)

    def test_check_window_excludes_old_issues(self):
        r = self.run_script("check.py", "--since", "2030-01-02T08:30:00Z")
        self.assertIn("DEMO-WEB-1", r.stdout)
        self.assertNotIn("DEMO-API-1", r.stdout)

    def test_unknown_project_and_bad_token(self):
        self.assertNotEqual(self.run_script("check.py", "--project", "nope").returncode, 0)
        bad = self.run_script("check.py", "--all", token="wrong-token")
        self.assertNotEqual(bad.returncode, 0)
        self.assertNotIn("wrong-token", bad.stdout + bad.stderr)

    def test_missing_url_is_explained(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("BUGSINK_")}
        env["BUGSINK_TOKEN"] = mock.TOKEN
        r = subprocess.run([sys.executable, str(SCRIPTS / "check.py")], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("BUGSINK_URL", r.stderr)

    def test_board_builds_page_with_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d, "v.json")
            v.write_text(json.dumps({
                "DEMO-WEB-1": {"verdict": "bug", "group": "cart totals", "cause": "cart is undefined", "action": "guard it"},
                "_work": [{"code": "W1", "name": "Cart fix", "state": "landing", "size": "S", "fixes": ["DEMO-WEB-1"]}],
                "_meta": {"subtitle": "demo"}}))
            out = Path(d, "board.html")
            r = self.run_script("board.py", "--verdicts", str(v), "--out", str(out), extra_env={"BUGSINK_BOARD_DIR": d})
            self.assertEqual(r.returncode, 0, r.stderr)
            page = out.read_text()
            self.assertIn("cart is undefined", page)
            self.assertIn('"verdict": "untriaged"', page)  # DEMO-API-1 has no entry
            self.assertNotIn("__DATA__", page)
            self.assertNotIn(mock.TOKEN, page)

    def test_act_dry_run_sends_nothing_then_resolves(self):
        mock.Handler.posts.clear()
        r = self.run_script("act.py", "resolve", FIRST, "--comment", "fixed in v2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Nothing sent", r.stdout)
        self.assertEqual(mock.Handler.posts, [])
        r = self.run_script("act.py", "resolve", FIRST, "--comment", "fixed in v2", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(mock.Handler.posts[0], ("/issue-comments/", {"issue": FIRST, "comment": "fixed in v2"}))
        self.assertEqual(mock.Handler.posts[1][0], f"/issues/{FIRST}/resolve/")
        self.assertIn("is_resolved=True", r.stdout)

    def test_act_mute_until_body_and_no_delete(self):
        mock.Handler.posts.clear()
        r = self.run_script("act.py", "mute-until", "bbbbbbbb-0000-0000-0000-000000000001",
                            "--period", "hour", "--count", "1", "--threshold", "10", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(mock.Handler.posts[0][1], {"period_name": "hour", "nr_of_periods": 1, "gte_threshold": 10})
        self.assertNotEqual(self.run_script("act.py", "delete", FIRST, "--yes").returncode, 0)

    def test_act_needs_write_token(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("BUGSINK_")}
        env.update(BUGSINK_URL=self.url, BUGSINK_TOKEN=mock.TOKEN)  # read token only
        r = subprocess.run([sys.executable, str(SCRIPTS / "act.py"), "reopen", FIRST, "--yes"],
                           capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("BUGSINK_TRIAGE_TOKEN", r.stderr)


if __name__ == "__main__":
    unittest.main()
