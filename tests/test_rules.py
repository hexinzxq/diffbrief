"""Every rule must fire on the shape it claims and stay quiet otherwise."""
import unittest

from diffbrief.diff import FileDiff, Hunk, Line, parse
from diffbrief.rules import look


def added_file(path: str, *texts: str, removed: int = 0) -> FileDiff:
    hunk = Hunk(1, 1 + removed, 1, 1 + len(texts), "")
    hunk.lines = [Line("+", text, index + 1, None) for index, text in enumerate(texts)]
    hunk.lines[:0] = [Line("-", f"gone {i}", None, i + 1) for i in range(removed)]
    file = FileDiff(path=path)
    file.hunks.append(hunk)
    return file


def rules(findings: list) -> list[str]:
    """Rule ids, minus the file-level `tests-missing` (it has its own tests).

    Every fixture here is a lone non-test file, so `tests-missing` would ride
    along on all of them and drown the rule under test.
    """
    return [finding.rule for finding in findings if finding.rule != "tests-missing"]


def all_rules(findings: list) -> list[str]:
    return [finding.rule for finding in findings]


class SecretTests(unittest.TestCase):
    def test_a_named_key_assignment_is_a_fail(self) -> None:
        findings = look([added_file("config.py", 'API_KEY = "abcdefghijklmnop"')])
        self.assertEqual(rules(findings), ["secret-literal"])
        self.assertEqual(findings[0].severity, "fail")
        self.assertNotIn("abcdefghijklmnop", findings[0].evidence)  # masked

    def test_known_key_shapes_are_caught_too(self) -> None:
        for literal in ('token = "ghp_' + "a" * 30 + '"', 'x = "sk-' + "b" * 30 + '"',
                        'aws = "AKIA1234567890ABCDEF"'):
            with self.subTest(literal=literal):
                self.assertEqual(rules(look([added_file("a.py", literal)])), ["secret-literal"])

    def test_a_removed_secret_is_not_a_new_one(self) -> None:
        file = FileDiff(path="a.py")
        hunk = Hunk(1, 1, 1, 1, "")
        hunk.lines = [Line("-", 'API_KEY = "abcdefghijklmnop"', None, 1)]
        file.hunks.append(hunk)
        self.assertEqual(rules(look([file])), [])


class DebugTests(unittest.TestCase):
    def test_console_log_and_pdb_are_warnings(self) -> None:
        findings = look([added_file("a.js", "console.log(x);"), added_file("b.py", "pdb.set_trace()")])
        self.assertEqual(rules(findings), ["debug-statement", "debug-statement"])
        self.assertTrue(all(finding.severity == "warn" for finding in findings))

    def test_a_word_that_merely_contains_log_is_quiet(self) -> None:
        self.assertEqual(rules(look([added_file("a.js", "logger.info(x);")])), [])


class DebugStatementTests(unittest.TestCase):
    def test_debug_output_in_code_is_a_warn(self) -> None:
        findings = look([added_file("src/app.js", "console.log(state)")])
        self.assertIn("debug-statement", rules(findings))

    def test_a_console_log_quoted_in_a_reference_doc_is_not_stray_debug_output(self) -> None:
        # skillforge's vendored skill references show console.log as an example;
        # nobody left debug output behind in a markdown file.
        findings = look([added_file("docs/REFERENCE.md", "```js\nconsole.log(state)\n```")])
        self.assertNotIn("debug-statement", rules(findings))


class TodoTests(unittest.TestCase):
    def test_a_new_todo_is_a_note(self) -> None:
        findings = look([added_file("a.py", "# TODO: handle the empty case")])
        self.assertEqual(rules(findings), ["todo-added"])
        todo = [finding for finding in findings if finding.rule == "todo-added"][0]
        self.assertEqual(todo.severity, "note")

    def test_a_todo_inside_a_data_string_is_not_a_new_todo(self) -> None:
        # dsh-daily-lab keeps the tool's own description in a JSON file; the
        # word TODO there is content being quoted, not a marker being added.
        findings = look([added_file("state/week.json",
                                    '"angle": "抓 TODO / FIXME 这类标记"')])
        self.assertEqual(rules(findings), [])

    def test_a_comment_style_todo_in_any_language_still_counts(self) -> None:
        for line in ("# TODO: x", "// FIXME(y)", "<!-- XXX -->", "- TODO: y"):
            findings = look([added_file("a.md", line)])
            self.assertIn("todo-added", rules(findings), line)


class RenameTests(unittest.TestCase):
    def test_a_rename_with_no_line_changed_does_not_ask_for_a_test(self) -> None:
        # `git mv a.py b.py` moves no line; saying "source changed, no test did"
        # here is noise about a diff that is empty.
        files = parse("diff --git a/a.py b/b.py\nsimilarity index 100%\n"
                      "rename from a.py\nrename to b.py\n")
        self.assertEqual(files[0].changed(), 0)
        self.assertEqual(all_rules(look(files)), [])

    def test_a_rename_that_also_changes_lines_still_asks(self) -> None:
        files = parse("diff --git a/a.py b/b.py\nsimilarity index 90%\n"
                      "rename from a.py\nrename to b.py\n"
                      "--- a/a.py\n+++ b/b.py\n@@ -1 +1,2 @@\n x = 1\n+y = 2\n")
        self.assertIn("tests-missing", all_rules(look(files)))


    def test_a_template_value_is_not_a_leaked_key(self) -> None:
        # Every repo with an example config says CHANGE_ME / your-token-here;
        # failing on those teaches people to ignore the rule.
        for template in ("CHANGE_ME", "your-api-key-here", "example", "dummy",
                         "${API_KEY}", "<token>", "xxxxxxxx", "redacted"):
            with self.subTest(template=template):
                findings = look([added_file("config.example.py",
                                            f'API_KEY = "{template}zz"'
                                            if template in ("example", "dummy") else
                                            f'API_KEY = "{template}"')])
                self.assertEqual(rules(findings), [])

    def test_a_real_looking_value_still_fails(self) -> None:
        findings = look([added_file("config.py", 'API_KEY = "9f8e7d6c5b4a3210"')])
        self.assertIn("secret-literal", rules(findings))

    def test_a_template_config_is_not_asked_for_a_test(self) -> None:
        for name in ("config.example.py", "settings.sample.py", "conf.template.py"):
            with self.subTest(name=name):
                findings = look([added_file(name, "x = 1")])
                self.assertEqual(all_rules(findings).count("tests-missing"), 0)

    def test_an_ordinary_module_still_asks_for_a_test(self) -> None:
        findings = look([added_file("config.py", "x = 1")])
        self.assertIn("tests-missing", all_rules(findings))

    def test_a_module_named_tests_counts_as_the_test_file(self) -> None:
        # Django puts tests in app/tests.py; the rule used to call that "no test did"
        # and count the test module itself as one of the changed source files.
        files = [added_file("app/models.py", "y = 2"),
                 added_file("app/tests.py", "class T(TestCase): pass")]
        self.assertEqual(all_rules(look(files)).count("tests-missing"), 0)

    def test_conftest_also_counts(self) -> None:
        files = [added_file("app/models.py", "y = 2"),
                 added_file("conftest.py", "import pytest")]
        self.assertEqual(all_rules(look(files)).count("tests-missing"), 0)

    def test_a_bare_secret_in_a_config_file_is_caught(self) -> None:
        for path, line in (
            ("values.yaml", "  password: hunter2hunter2"),
            ("settings.ini", "password = anothersecret99"),
            ("application.properties", "spring.datasource.password=Sup3rS3cret"),
            ("app.toml", 'token = "abcdefgh12345"'),
        ):
            with self.subTest(path=path):
                self.assertIn("secret-literal", rules(look([added_file(path, line)])))

    def test_a_reference_in_a_config_file_is_not_a_secret(self) -> None:
        for line in ("password: ${DB_PASSWORD}", "api_key: {{ .Values.key }}",
                     "password: <your-password>", "token: CHANGE_ME_NOW"):
            with self.subTest(line=line):
                self.assertEqual(rules(look([added_file("values.yaml", line)])), [])

class ShapeTests(unittest.TestCase):
    def test_a_huge_deletion_is_flagged_but_a_lockfile_is_not(self) -> None:
        findings = look([added_file("src/big.py", "still here", removed=40),
                         added_file("package-lock.json", "x", removed=40)])
        self.assertEqual(rules(findings), ["large-deletion"])

    def test_lockfile_churn_is_a_note_not_a_deletion(self) -> None:
        file = added_file("yarn.lock", *[f"entry {i}" for i in range(210)])
        self.assertEqual(rules(look([file])), ["lockfile-churn"])

    def test_code_without_a_test_change_is_one_warning(self) -> None:
        findings = look([added_file("src/a.py", "x = 1"), added_file("src/b.py", "y = 2")])
        self.assertEqual(all_rules(findings), ["tests-missing"])
        self.assertEqual(findings[0].path, "src/a.py")  # the biggest changed file

    def test_a_test_change_satisfies_it(self) -> None:
        findings = look([added_file("src/a.py", "x = 1"),
                         added_file("tests/test_a.py", "def test_it(): pass")])
        self.assertEqual(all_rules(findings), [])

    def test_worst_findings_sort_first(self) -> None:
        findings = look([added_file("a.py", "# TODO x"),
                         added_file("b.py", 'API_KEY = "abcdefghijklmnop"')])
        # fail first, then the file-level warn, then the note
        self.assertEqual([finding.severity for finding in findings], ["fail", "warn", "note"])


class ParseThenLookTests(unittest.TestCase):
    def test_a_real_diff_text_feeds_the_rules(self) -> None:
        text = '''diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,1 +1,2 @@
 x = 1
+pdb.set_trace()
'''
        self.assertEqual(rules(look(parse(text))), ["debug-statement"])


if __name__ == "__main__":
    unittest.main()
