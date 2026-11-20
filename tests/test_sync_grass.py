import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import sync_grass


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.previous_directory = os.getcwd()
        os.chdir(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("commit", "-q", "--allow-empty", "-m", "initial")
        self.environment = patch.dict(os.environ, {
            "GITLAB_TOKEN": "test-token",
            "GITLAB_EMAILS": " TEST@example.com ",
            "GITHUB_STEP_SUMMARY": str(Path.cwd() / "summary.md"),
        })
        self.environment.start()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.stdout = self.output.__enter__()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.output.__exit__(None, None, None)
        self.environment.stop()
        os.chdir(self.previous_directory)
        # Git objects can be read-only on Windows; leave cleanup to TemporaryDirectory
        # which handles their permissions.
        self.directory.cleanup()

    def git(self, *arguments):
        return subprocess.check_output(["git", *arguments], stderr=subprocess.STDOUT).decode().strip()

    def commit(self, sha="a", date="2026-11-16T21:58:03+09:00", email="test@example.com"):
        return {"id": sha * 40, "authored_date": date, "author_email": email}

    def api(self, commits=None, projects=None):
        if commits is None:
            commits = [self.commit()]
        if projects is None:
            projects = [{"id": 1}, {"id": 2}]

        def request(path, **params):
            if path == "projects":
                return projects
            self.assertEqual(params.get("all"), "true")
            return commits
        return patch.object(sync_grass, "api_get_all", side_effect=request)

    def test_dates_deduplication_and_repeat_run(self):
        with self.api(commits=[self.commit(), self.commit(email="other@example.com", sha="b")]):
            sync_grass.main()
            sync_grass.main()
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "2")
        self.assertEqual(sync_grass.load_state(), {"a" * 40})
        self.assertEqual(self.git("show", "-s", "--format=%aI|%cI"),
                         "2026-11-16T21:58:03+09:00|2026-11-16T21:58:03+09:00")
        self.assertIn("이번에 생성한 커밋 | 0", Path("summary.md").read_text(encoding="utf-8"))

    def test_interrupted_run_retries_only_uncommitted_sha(self):
        real_run = subprocess.run
        attempts = 0

        def interrupt(arguments, **kwargs):
            nonlocal attempts
            if arguments[:2] == ["git", "commit"]:
                attempts += 1
                if attempts == 2:
                    raise subprocess.CalledProcessError(1, arguments)
            return real_run(arguments, **kwargs)

        with self.api(commits=[self.commit(), self.commit(sha="b")]):
            with patch.object(sync_grass.subprocess, "run", side_effect=interrupt):
                with self.assertRaises(subprocess.CalledProcessError):
                    sync_grass.main()
            self.assertEqual(sync_grass.load_state(), {"a" * 40})
            sync_grass.main()
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "3")
        self.assertEqual(sync_grass.load_state(), {"a" * 40, "b" * 40})

    def test_partial_access_failure_is_identified_and_other_project_syncs(self):
        def request(path, **params):
            if path == "projects":
                return [{"id": 1}, {"id": 2}]
            if path.startswith("projects/1/"):
                raise urllib.error.HTTPError("https://example.com", 403, "Forbidden", {}, None)
            return [self.commit()]
        with patch.object(sync_grass, "api_get_all", side_effect=request):
            sync_grass.main()
        self.assertEqual(sync_grass.load_state(), {"a" * 40})
        self.assertIn("프로젝트 ID 1: HTTP 403", self.stdout.getvalue())
        self.assertIn("프로젝트 ID `1`: HTTP 403", Path("summary.md").read_text(encoding="utf-8"))

    def test_no_projects_fails_without_creating_commits(self):
        with self.api(projects=[]), self.assertRaises(SystemExit):
            sync_grass.main()
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")

    def test_all_inaccessible_fails(self):
        def request(path, **params):
            if path == "projects":
                return [{"id": 1}]
            raise urllib.error.HTTPError("https://example.com", 404, "Not Found", {}, None)
        with patch.object(sync_grass, "api_get_all", side_effect=request), self.assertRaises(SystemExit):
            sync_grass.main()
        self.assertEqual(self.git("rev-list", "--count", "HEAD"), "1")

    def test_server_error_is_not_reported_as_success(self):
        def request(path, **params):
            if path == "projects":
                return [{"id": 1}]
            raise urllib.error.HTTPError("https://example.com", 500, "Server error", {}, None)
        with patch.object(sync_grass, "api_get_all", side_effect=request), self.assertRaises(urllib.error.HTTPError):
            sync_grass.main()

    def test_pagination_includes_second_page(self):
        with patch.object(sync_grass, "api_get", side_effect=[list(range(100)), [100]]):
            self.assertEqual(sync_grass.api_get_all("projects"), list(range(101)))


if __name__ == "__main__":
    unittest.main()
