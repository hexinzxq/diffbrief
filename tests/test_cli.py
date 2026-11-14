"""The CLI is what a hook or a person runs; check its exit codes and words."""
import io
import contextlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from diffbrief.cli import main


def git(*args: str, cwd: Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr}")
    return done.stdout


def run(*argv: str) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue() + err.getvalue()


class RepoCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "app"
        self.repo.mkdir()
        git("init", "-b", "main", cwd=self.repo)
        git("config", "user.email", "t@example.com", cwd=self.repo)
        git("config", "user.name", "t", cwd=self.repo)
        (self.repo / "app.py").write_text("x = 1\n")
        git("add", ".", cwd=self.repo)
        git("commit", "-qm", "initial import", cwd=self.repo)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class ExitCodeTests(RepoCase):
    def test_a_clean_tree_is_exit_zero_and_says_so(self) -> None:
        code, out = run("-C", str(self.repo), "--staged")
        self.assertEqual(code, 0)
        self.assertIn("no changes against", out)

    def test_a_staged_secret_fails_the_run(self) -> None:
        (self.repo / "app.py").write_text('x = 1\nAPI_KEY = "abcdefghijklmnop"\n')
        git("add", ".", cwd=self.repo)
        code, out = run("-C", str(self.repo), "--staged")
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)
        self.assertIn("secret-literal", out)
        self.assertNotIn("abcdefghijklmnop", out)

    def test_json_is_the_same_report_in_one_object(self) -> None:
        (self.repo / "app.py").write_text("x = 1\nconsole.log(x);\n")
        git("add", ".", cwd=self.repo)
        code, out = run("-C", str(self.repo), "--staged", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["files"], 1)
        self.assertGreaterEqual(data["totals"]["warn"], 1)
        self.assertIn("debug-statement", [finding["rule"] for finding in data["findings"]])

    def test_a_directory_that_is_not_a_repository_is_a_sentence(self) -> None:
        outsider = Path(self.tmp.name) / "plain"
        outsider.mkdir()
        code, out = run("-C", str(outsider))
        self.assertEqual(code, 2)
        self.assertIn("not a git repository", out)
        self.assertNotIn("Traceback", out)

    def test_an_unpushed_commit_is_read_without_flags(self) -> None:
        # A repo with a remote: `HEAD` alone would show nothing, the upstream
        # range is what "about to push" means.
        remote = Path(self.tmp.name) / "remote.git"
        git("init", "-q", "--bare", str(remote), cwd=Path(self.tmp.name))
        git("remote", "add", "origin", str(remote), cwd=self.repo)
        git("push", "-qu", "origin", "main", cwd=self.repo)
        (self.repo / "app.py").write_text("x = 1\n# TODO later\n")
        git("add", ".", cwd=self.repo)
        git("commit", "-qm", "more", cwd=self.repo)
        code, out = run("-C", str(self.repo))
        self.assertEqual(code, 0)
        self.assertIn("todo-added", out)

    def test_the_module_entry_point_is_the_same_command(self) -> None:
        # README says `PYTHONPATH=src python -m diffbrief` works without an
        # install; a package without __main__ silently breaks that promise.
        done = subprocess.run([sys.executable, "-m", "diffbrief", "--help"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("unpushed diff", done.stdout)


if __name__ == "__main__":
    unittest.main()
