import json
import threading
import unittest
from urllib.request import urlopen

from duacincin.server import GeminiHandler, ThreadedServer


class ApiDocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadedServer(("127.0.0.1", 0), GeminiHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_openapi_json_exists(self):
        with urlopen(f"http://127.0.0.1:{self.port}/openapi.json") as resp:
            self.assertEqual(resp.status, 200)
            payload = json.loads(resp.read().decode("utf-8"))
            self.assertIn("openapi", payload)
            self.assertIn("/v1/chat/completions", payload["paths"])

    def test_swagger_docs_page_exists(self):
        with urlopen(f"http://127.0.0.1:{self.port}/docs") as resp:
            self.assertEqual(resp.status, 200)
            html = resp.read().decode("utf-8")
            self.assertIn("Swagger UI", html)
            self.assertIn("/openapi.json", html)


if __name__ == "__main__":
    unittest.main()
