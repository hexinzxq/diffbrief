"""The parser is the only place that reads git's own text."""
import unittest

from diffbrief.diff import base_label, parse, read_diff
from tests.test_cli import RepoCase, git

TWO_FILES = '''diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 import os
-x = 1
+x = 2
 print(x)
+y = 3
diff --git a/notes/new.txt b/notes/new.txt
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/notes/new.txt
@@ -0,0 +1,2 @@
+hello
+world
'''


class PathTests(RepoCase):
    def test_a_non_ascii_path_is_not_octal_escaped(self) -> None:
        name = "üñí çode.py"
        (self.repo / name).write_text('console.log("x")\n')
        git("add", "-A", cwd=self.repo)
        files = read_diff(self.repo, staged=True)
        self.assertEqual([file.path for file in files], [name])


    def test_a_first_push_is_read_against_the_empty_tree(self) -> None:
        # origin exists but origin/HEAD is not set (`git remote add origin …`),
        # and this branch was never pushed: comparing against HEAD would be
        # HEAD...HEAD, i.e. nothing, and the hook would pass the branch unseen.
        git("remote", "add", "origin", str(self.repo / "nowhere.git"), cwd=self.repo)
        git("checkout", "-q", "-b", "feature", cwd=self.repo)
        (self.repo / "leak.py").write_text('PASSWORD = "hunter2hunter2"\n')
        git("add", "-A", cwd=self.repo)
        git("commit", "-qm", "add config", cwd=self.repo)
        files = read_diff(self.repo, committed=True)
        self.assertIn("leak.py", [file.path for file in files])

    def test_the_label_says_there_is_no_remote_copy(self) -> None:
        git("remote", "add", "origin", str(self.repo / "nowhere.git"), cwd=self.repo)
        git("checkout", "-q", "-b", "feature", cwd=self.repo)
        self.assertIn("no copy yet", base_label(self.repo, None, committed=True))

    def test_a_branch_with_an_upstream_keeps_using_it(self) -> None:
        git("remote", "add", "origin", str(self.repo / "nowhere.git"), cwd=self.repo)
        git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=self.repo)
        git("branch", "--set-upstream-to=origin/main", "main", cwd=self.repo)
        self.assertEqual(base_label(self.repo, None, committed=True), "@{upstream}")

class ParseTests(unittest.TestCase):
    def test_two_files_are_two_entries(self) -> None:
        files = parse(TWO_FILES)
        self.assertEqual([file.path for file in files], ["src/app.py", "notes/new.txt"])
        self.assertTrue(files[1].new)
        self.assertFalse(files[0].binary)

    def test_line_numbers_follow_the_new_file(self) -> None:
        files = parse(TWO_FILES)
        added = files[0].added()
        self.assertEqual([line.new_no for line in added], [2, 4])
        self.assertEqual([line.text for line in added], ["x = 2", "y = 3"])
        removed = files[0].removed()
        self.assertEqual([line.old_no for line in removed], [2])

    def test_a_deleted_image_is_binary_and_removal_is_known(self) -> None:
        text = '''diff --git a/logo.png b/logo.png
deleted file mode 100644
Binary files a/logo.png and /dev/null differ
'''
        files = parse(text)
        self.assertTrue(files[0].binary)
        self.assertTrue(files[0].deleted)

    def test_a_rename_keeps_the_new_path(self) -> None:
        text = '''diff --git a/old name.py b/new name.py
similarity index 100%
rename from old name.py
rename to new name.py
'''
        files = parse(text)
        self.assertEqual(files[0].path, "new name.py")

    def test_a_context_line_advances_both_counters(self) -> None:
        text = '''diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -10,2 +20,3 @@ def f():
 keep
+added
 also
'''
        lines = parse(text)[0].hunks[0].lines
        self.assertEqual([(line.kind, line.new_no, line.old_no) for line in lines],
                         [(" ", 20, 10), ("+", 21, None), (" ", 22, 11)])


if __name__ == "__main__":
    unittest.main()
