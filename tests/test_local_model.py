import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError


module_path = Path(__file__).resolve().parents[1] / "assistant_local" / "local_model.py"
spec = importlib.util.spec_from_file_location("local_model", module_path)
local_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local_model)


class FakeModelHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.server.request_data = json.loads(self.rfile.read(length))
        if getattr(self.server, "redirect", False):
            self.send_response(302)
            self.send_header("Location", "http://example.com/")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(getattr(
            self.server, "response_data", {"message": {"role": "assistant", "content": "Hello"}}
        )).encode())

    def log_message(self, *args):
        pass


class LocalModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeModelHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_local_chat_returns_message_from_fake_service(self):
        url = "http://127.0.0.1:%s" % self.server.server_port
        messages = [{"role": "user", "content": "Hola"}]
        result = local_model.chat(url, "test-model", messages, [], timeout=2)
        self.assertEqual(result["content"], "Hello")
        self.assertEqual(self.server.request_data["messages"], messages)
        self.assertFalse(self.server.request_data["stream"])

    def test_remote_host_or_embedded_credentials_are_rejected(self):
        for url in ("http://example.com:11434", "http://user:pass@127.0.0.1:11434",
                    "http://127.0.0.1:11434/other", "https://127.0.0.1:11434"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_model.chat(url, "test-model", [], [], timeout=2)

    def test_invalid_timeout_is_rejected(self):
        for timeout in (0, -1, float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                local_model.chat("http://127.0.0.1:11434", "test-model", [], [], timeout=timeout)

    def test_redirect_to_remote_service_is_rejected(self):
        self.server.redirect = True
        try:
            url = "http://127.0.0.1:%s" % self.server.server_port
            with self.assertRaises(HTTPError):
                local_model.chat(url, "test-model", [], [], timeout=2)
        finally:
            self.server.redirect = False

    def test_malformed_model_messages_are_rejected(self):
        url = "http://127.0.0.1:%s" % self.server.server_port
        for response in ({"message": {"role": "user", "content": "bad"}},
                         {"message": {"role": "assistant", "content": 17}},
                         {"message": {"role": "assistant", "tool_calls": "bad"}},
                         {"message": {"role": "assistant", "tool_calls": [
                             {"function": {"name": "x", "arguments": "bad"}}
                         ]}}):
            self.server.response_data = response
            with self.subTest(response=response), self.assertRaises(ValueError):
                local_model.chat(url, "test-model", [], [], timeout=2)
        del self.server.response_data

    def test_untrusted_extra_fields_in_tool_calls_are_removed(self):
        self.server.response_data = {"message": {"role": "assistant", "tool_calls": [{
            "unexpected": "discard", "function": {
                "name": "test.echo", "arguments": {"value": "ok"}, "extra": "discard"
            }
        }]}}
        try:
            url = "http://127.0.0.1:%s" % self.server.server_port
            result = local_model.chat(url, "test-model", [], [], timeout=2)
            self.assertEqual(result["tool_calls"], [{"function": {
                "name": "test.echo", "arguments": {"value": "ok"}
            }}])
        finally:
            del self.server.response_data


if __name__ == "__main__":
    unittest.main()
