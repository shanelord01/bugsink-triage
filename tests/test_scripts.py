"""Run check.py, board.py and act.py against the fake Bugsink. Standard library only.

  python3 -m unittest discover -s tests -v
"""
import datetime as dt
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

    def run_script(self, name, *args, token=mock.TOKEN, extra_env=None, no_url=False):
        env = {k: v for k, v in os.environ.items() if not k.startswith("BUGSINK_")}
        env.update(BUGSINK_TRIAGE_TOKEN=token, **(extra_env or {}))
        if not no_url:
            env["BUGSINK_URL"] = self.url
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

    def fake_gh(self, d, prs, merged_urls=()):
        """A stand-in gh CLI on PATH: `pr list` returns prs, `pr view` reports merged or open."""
        script = Path(d, "gh")
        script.write_text("#!/bin/sh\n"
                          "if [ \"$2\" = list ]; then cat <<'EOF'\n" + json.dumps(prs) + "\nEOF\n"
                          "elif [ \"$2\" = view ]; then\n"
                          "  case \"$3\" in " + "|".join(merged_urls or ["NONE"]) + ") S=MERGED;; *) S=OPEN;; esac\n"
                          "  echo \"{\\\"state\\\":\\\"$S\\\",\\\"isDraft\\\":false,\\\"statusCheckRollup\\\":[]}\"\n"
                          "fi\n")
        script.chmod(0o755)
        return {"PATH": f"{d}:{os.environ['PATH']}", "BUGSINK_BOARD_DIR": d}

    def test_board_links_issue_and_follows_github(self):
        pr = {"number": 7, "title": "Guard cart total (DEMO-WEB-1)", "url": "https://github.com/acme/web/pull/7",
              "body": "", "headRefName": "fix/cart"}
        other = {"number": 8, "title": "Unrelated", "url": "https://github.com/acme/web/pull/8", "body": "mentions DEMO-WEB-10", "headRefName": "x"}
        with tempfile.TemporaryDirectory() as d:
            env = self.fake_gh(d, [pr, other])
            Path(d, "verdicts.json").write_text(json.dumps({
                "DEMO-WEB-1": {"verdict": "bug", "cause": "cart is undefined"},
                "_work": [{"code": "W1", "name": "Cart fix", "state": "todo", "fixes": ["DEMO-WEB-1"],
                           "links": [{"label": "PR 7", "url": pr["url"]}]}],
                "_meta": {"repos": ["acme/web"], "needs": [{"text": "Merge old", "url": "https://github.com/acme/web/pull/3"}]}}))
            env["BUGSINK_BOARD_DIR"] = d
            r = self.run_script("board.py", extra_env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            cur = json.loads(Path(d, "current.json").read_text())
            one = next(i for i in cur["issues"] if i["id"] == "DEMO-WEB-1")
            self.assertTrue(one["url"].endswith("/issues/issue/aaaaaaaa-0000-0000-0000-000000000001/event/last/"))
            self.assertTrue(one["url"].startswith(self.url))
            self.assertEqual(one["prs"], [{"label": "web PR 7", "url": pr["url"]}])  # PR 8 mentions DEMO-WEB-10 only
            self.assertEqual(cur["work"][0]["state"], "landing")  # its PR is open
            texts = [n["text"] for n in cur["meta"]["needs"]]
            self.assertIn("Merge web PR 7: Guard cart total (DEMO-WEB-1)", texts)
            self.assertIn("Merge old", texts)
            self.assertIn("DEMO-WEB-1: cart is undefined.", one["comment"])
            # Now PR 7 and PR 3 merge: --prs-only lands the step and drops both lines, without Bugsink.
            env = self.fake_gh(d, [], merged_urls=[pr["url"], "https://github.com/acme/web/pull/3"])
            env["BUGSINK_BOARD_DIR"] = d
            r = self.run_script("board.py", "--prs-only", token="unused", extra_env=env, no_url=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), "changed")
            cur = json.loads(Path(d, "current.json").read_text())
            self.assertEqual(cur["work"][0]["state"], "landed")
            self.assertEqual(cur["meta"]["needs"], [])
            Path(d, "last-synced.json").write_text(json.dumps(cur))
            r = self.run_script("board.py", "--prs-only", token="unused", extra_env=env, no_url=True)
            self.assertEqual(r.stdout.strip(), "no change")

    def test_board_shows_pr_owner_and_config_defaults(self):
        pr = {"number": 7, "title": "Fix (DEMO-WEB-1)", "url": "https://github.com/acme/web/pull/7", "body": "", "headRefName": "x"}
        with tempfile.TemporaryDirectory() as d:
            env = self.fake_gh(d, [pr])
            Path(d, "bugsink-triage.config.json").write_text(json.dumps({
                "repos": ["acme/web"],
                "prSessions": {pr["url"]: {"id": "session-1", "name": "Checkout fix"}}}))
            r = self.run_script("board.py", extra_env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            cur = json.loads(Path(d, "current.json").read_text())
            need = next(n for n in cur["meta"]["needs"] if n["url"] == pr["url"])
            self.assertEqual(need["session"], {"id": "session-1", "name": "Checkout fix"})
            page = Path(d, "board.html").read_text()
            self.assertIn("collection('handoffs')", page)  # the page reads hand-offs
            self.assertNotIn("claude://", page)
            self.assertIn("sendToClaudeSession", page)  # Submit hands Claude a note
            self.assertIn("bugsink-triage-submit", page)

    def test_config_file_renames_env_and_reads_token_command(self):
        with tempfile.TemporaryDirectory() as d:
            tok = Path(d, "tok.sh")
            tok.write_text(f"#!/bin/sh\necho {mock.TOKEN}\n")
            tok.chmod(0o755)
            Path(d, "bugsink-triage.config.json").write_text(json.dumps({
                "_comment": "ignored", "urlEnv": "ACME_ERRORS_URL", "readTokenCommand": [str(tok)],
                "projects": ["demo-web"], "tags": ["secret.tag"]}))
            env = {k: v for k, v in os.environ.items() if not k.startswith("BUGSINK_")}
            env.update(BUGSINK_BOARD_DIR=d, ACME_ERRORS_URL=self.url)
            r = subprocess.run([sys.executable, str(SCRIPTS / "check.py"), "--all"], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Total: 1", r.stdout)            # projects default from the config
            self.assertIn("secret.tag=hidden", r.stdout)   # tags default from the config
            self.assertNotIn(mock.TOKEN, r.stdout + r.stderr)
            r = subprocess.run([sys.executable, str(SCRIPTS / "config.py"), "show"], capture_output=True, text=True, env=env)
            self.assertIn("read token    command in config", r.stdout)
            self.assertNotIn(mock.TOKEN, r.stdout)

    def test_config_init_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if not k.startswith("BUGSINK_")}
            env["BUGSINK_BOARD_DIR"] = d
            run = lambda: subprocess.run([sys.executable, str(SCRIPTS / "config.py"), "init"], capture_output=True, text=True, env=env)
            self.assertEqual(run().returncode, 0)
            self.assertTrue(Path(d, "bugsink-triage.config.json").exists())
            self.assertNotEqual(run().returncode, 0)

    def test_state_dir_from_config(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as state:
            cfg = Path(d, "c.json")
            cfg.write_text(json.dumps({"stateDir": state}))
            env = {k: v for k, v in os.environ.items() if not k.startswith("BUGSINK_")}
            env.update(BUGSINK_TRIAGE_CONFIG=str(cfg), BUGSINK_URL=self.url, BUGSINK_TOKEN=mock.TOKEN)
            r = subprocess.run([sys.executable, str(SCRIPTS / "board.py"), "--no-prs"], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(Path(state, "current.json").exists())

    def test_handoff_record_and_close_out(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "artifact-url.txt").write_text("https://claude.ai/artifact/example\n")
            Path(d, "bugsink-triage.config.json").write_text(json.dumps({"handoffDueHours": 6}))
            r = self.run_script("handoff.py", "new", "--to-id", "session-2", "--to-name", "Checkout fix",
                                "--task", "Guard the cart total", "--step", "W1", "--issues", "DEMO-WEB-1",
                                extra_env={"BUGSINK_BOARD_DIR": d})
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            doc = out["document"]
            self.assertEqual(out["doc_id"], "ho-guard-the-cart-total")
            self.assertEqual((doc["to"], doc["step"], doc["issues"], doc["status"]),
                             ({"id": "session-2", "name": "Checkout fix"}, "W1", ["DEMO-WEB-1"], "open"))
            asked = dt.datetime.strptime(doc["askedAt"], "%Y-%m-%dT%H:%M:%SZ")
            due = dt.datetime.strptime(doc["dueAt"], "%Y-%m-%dT%H:%M:%SZ")
            self.assertEqual(due - asked, dt.timedelta(hours=6))  # from handoffDueHours
            self.assertIn("handoffs/ho-guard-the-cart-total", out["close_out"])
            self.assertIn("https://claude.ai/artifact/example", out["close_out"])

    def test_board_without_gh_or_repos_still_builds(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_script("board.py", "--no-prs", extra_env={"BUGSINK_BOARD_DIR": d})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(Path(d, "current.json").exists())

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
