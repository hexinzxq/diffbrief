"""The page and its endpoint, over a real socket."""
import json
import threading
import unittest
import urllib.request

from diffbrief.server import serve

from .test_cli import RepoCase, git


class ServerTests(RepoCase):
    def setUp(self) -> None:
        super().setUp()
        (self.repo / "app.py").write_text("x = 1\nconsole.log(x);\n")
        git("add", ".", cwd=self.repo)
        self.httpd = serve(self.repo, None, True, "127.0.0.1", 0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def get(self, path: str) -> tuple[int, bytes]:
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as response:
            return response.status, response.read()

    def test_the_page_is_served_at_the_root(self) -> None:
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"diffbrief", body)
        self.assertIn("viewport".encode(), body)

    def test_the_report_endpoint_matches_the_cli(self) -> None:
        status, body = self.get("/api/report")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["files"], 1)
        self.assertIn("debug-statement", [finding["rule"] for finding in data["findings"]])
        self.assertIn("totals", data)

    def test_an_unknown_path_is_404_json(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/nope")
        self.assertEqual(caught.exception.code, 404)
        self.assertIn(b"not found", caught.exception.read())


if __name__ == "__main__":
    unittest.main()
