import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest import mock
import urllib.error


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "main.py"
SPEC = importlib.util.spec_from_file_location("llm_gateway_main", MODULE_PATH)
gateway = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gateway)


class _Response:
    def __init__(self, body: bytes = b"{}"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://llm-api.amd.com/test",
        code,
        "failure",
        {},
        io.BytesIO(body.encode("utf-8")),
    )


class ValidationAuthenticationTests(unittest.TestCase):
    def setUp(self):
        gateway._model_metadata_cache.clear()
        gateway._model_metadata_cache["claude-test"] = {
            "id": "claude-test",
            "owned_by": "Anthropic",
            "capabilities": {"chat": True},
        }
        self.env = mock.patch.dict(
            os.environ,
            {"AMD_LLM_API_KEY": "super-secret-key", "AMD_LLM_USER_NTID": "ctung"},
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_personal_auth_rejection_retries_once_with_user_header(self):
        for status in (401, 403):
            with self.subTest(status=status):
                seen_headers = []

                def urlopen(request, timeout):
                    seen_headers.append(dict(request.header_items()))
                    if len(seen_headers) == 1:
                        raise _http_error(status, "authentication rejected")
                    return _Response()

                with mock.patch("urllib.request.urlopen", side_effect=urlopen):
                    result = gateway.validate_model("claude-test", "personal")

                self.assertEqual(2, len(seen_headers))
                self.assertNotIn("User", seen_headers[0])
                self.assertEqual("ctung", seen_headers[1]["User"])
                self.assertEqual("success", result["status"])
                self.assertEqual("application_likely", result["key_type"])
                self.assertIn("confirm", result["authentication_diagnosis"].lower())

    def test_failed_application_probe_stops_after_one_retry_and_redacts_key(self):
        calls = []

        def urlopen(request, timeout):
            calls.append(dict(request.header_items()))
            raise _http_error(403, "rejected super-secret-key")

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            result = gateway.validate_model("claude-test", "personal")

        self.assertEqual(2, len(calls))
        self.assertEqual("failed", result["app_key_probe"])
        self.assertNotIn("super-secret-key", json.dumps(result))

    def test_non_auth_error_does_not_retry(self):
        with mock.patch("urllib.request.urlopen", side_effect=_http_error(429, "rate limited")) as call:
            result = gateway.validate_model("claude-test", "personal")

        self.assertEqual(1, call.call_count)
        self.assertEqual(429, result["http_code"])

    def test_missing_user_400_retries_but_negated_message_does_not(self):
        for body, expected_calls in (
            ("The user header is required", 2),
            ("The user header is not required for this key", 1),
            ("Unrelated bad request", 1),
        ):
            with self.subTest(body=body):
                calls = []

                def urlopen(request, timeout):
                    calls.append(dict(request.header_items()))
                    if len(calls) == 1:
                        raise _http_error(400, body)
                    return _Response()

                with mock.patch("urllib.request.urlopen", side_effect=urlopen):
                    gateway.validate_model("claude-test", "personal")

                self.assertEqual(expected_calls, len(calls))

    def test_auth_error_does_not_retry_without_available_ntid(self):
        with mock.patch.dict(os.environ, {"AMD_LLM_USER_NTID": ""}, clear=False), \
                mock.patch("urllib.request.urlopen", side_effect=_http_error(401, "rejected")) as call:
            result = gateway.validate_model("claude-test", "personal")

        self.assertEqual(1, call.call_count)
        self.assertEqual("needs_input", result["status"])
        self.assertEqual("needs_ntid", result["app_key_probe"])
        self.assertEqual(401, result["http_code"])

    def test_application_key_sends_explicit_ntid(self):
        seen_headers = []

        def urlopen(request, timeout):
            seen_headers.append(dict(request.header_items()))
            return _Response()

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            result = gateway.validate_model("claude-test", "application", ntid="abhirams")

        self.assertEqual("abhirams", seen_headers[0]["User"])
        self.assertEqual("application", result["key_type"])

    def test_list_models_auth_error_requests_ntid_instead_of_success_null(self):
        with mock.patch.dict(os.environ, {"AMD_LLM_USER_NTID": ""}, clear=False), \
                mock.patch("urllib.request.urlopen", side_effect=_http_error(401, "rejected")):
            result = gateway.list_models(key_type="personal")

        self.assertEqual("needs_input", result["status"])
        self.assertEqual("needs_ntid", result["app_key_probe"])
        self.assertEqual(401, result["http_code"])
        self.assertIsNone(result["data"])

    def test_list_models_personal_rejection_can_detect_application_key(self):
        calls = []
        payload = b'[{"id":"claude-test","owned_by":"Anthropic","capabilities":{"chat":true}}]'

        def urlopen(request, timeout):
            calls.append(dict(request.header_items()))
            if len(calls) == 1:
                raise _http_error(401, "rejected")
            return _Response(payload)

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            result = gateway.list_models(key_type="personal", ntid="ctung")

        self.assertEqual(2, len(calls))
        self.assertNotIn("User", calls[0])
        self.assertEqual("ctung", calls[1]["User"])
        self.assertEqual("application_likely", result["key_type"])

    def test_usage_example_asks_for_key_type(self):
        result = gateway.get_usage_example("claude-test")
        self.assertEqual("needs_input", result["status"])
        self.assertIn("personal or application", result["question"])

    def test_application_example_includes_user_header_and_valid_python(self):
        result = gateway.get_usage_example("claude-test", "python", "application")
        code = result["data"]["code"]
        self.assertIn('"user": authenticated_user_ntid', code)
        self.assertIn("app's identity context", code)
        compile(code, "<generated-example>", "exec")

    def test_application_rerank_javascript_includes_user_header(self):
        gateway._model_metadata_cache["test-rerank"] = {
            "id": "test-rerank",
            "owned_by": "OnPremLLM",
            "capabilities": {"Rerank": True},
        }
        result = gateway.get_usage_example("test-rerank", "javascript", "application")
        code = result["data"]["code"]
        self.assertIn('"user": authenticatedUserNtid', code)
        self.assertIn("const authenticatedUserNtid", code)


if __name__ == "__main__":
    unittest.main()
