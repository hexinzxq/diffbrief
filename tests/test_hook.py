"""The hook is the reason the tool exists; check what it writes and what it refuses."""
import os
import unittest
from pathlib import Path

from tests.test_cli import RepoCase, git, run


class InstallHookTests(RepoCase):
    def hook(self) -> Path:
        base = self.repo.resolve()  # the CLI resolves its root; /var -> /private/var
        raw = Path(git("rev-parse", "--git-path", "hooks", cwd=base).strip())
        # git prints this relative to the repository, not to wherever the test
        # process happens to stand.
        return (raw if raw.is_absolute() else base / raw) / "pre-push"

    def test_installing_writes_an_executable_hook_that_runs_diffbrief(self) -> None:
        code, out = run("-C", str(self.repo), "--install-hook")
        self.assertEqual(code, 0)
        path = self.hook()
        self.assertTrue(path.exists())
        self.assertTrue(os.access(path, os.X_OK))
        text = path.read_text()
        self.assertIn("Installed by `diffbrief --install-hook`", text)
        self.assertIn("exec diffbrief --committed", text)
        self.assertIn("installed", out)

    def test_installing_twice_is_not_an_error_and_does_not_rewrite(self) -> None:
        run("-C", str(self.repo), "--install-hook")
        path = self.hook()
        before = path.read_text()
        code, out = run("-C", str(self.repo), "--install-hook")
        self.assertEqual(code, 0)
        self.assertIn("already there", out)
        self.assertEqual(path.read_text(), before)

    def test_a_hook_somebody_else_wrote_is_left_alone(self) -> None:
        path = self.hook()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\necho mine\n")
        code, out = run("-C", str(self.repo), "--install-hook")
        self.assertEqual(code, 2)
        self.assertIn("already exists and was not written by diffbrief", out)
        self.assertEqual(path.read_text(), "#!/bin/sh\necho mine\n")

    def test_the_hook_actually_stops_a_push_with_a_fail(self) -> None:
        remote = Path(self.tmp.name) / "remote.git"
        git("init", "--bare", "-q", str(remote), cwd=self.repo)
        git("remote", "add", "origin", str(remote), cwd=self.repo)
        run("-C", str(self.repo), "--install-hook")
        # Put a diffbrief on PATH that blocks, so the hook runs without an install.
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "diffbrief"
        fake.write_text("#!/bin/sh\nexit 1\n")
        fake.chmod(0o755)
        env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        done = __import__("subprocess").run(["git", "push", "origin", "main"],
                                            cwd=self.repo, capture_output=True,
                                            text=True, env=env)
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(git("ls-remote", "origin", "main", cwd=self.repo).strip(), "")


if __name__ == "__main__":
    unittest.main()
