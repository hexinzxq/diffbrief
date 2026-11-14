"""The parser is the only place that reads git's own text."""
import unittest

from diffbrief.diff import parse

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
