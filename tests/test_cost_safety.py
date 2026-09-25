import unittest
from unittest.mock import patch

from app import config
from app.main import health
from app.services import llm_client, vector_store


class CostSafetyTest(unittest.TestCase):
    def test_llm_disabled_never_dispatches_to_provider(self):
        with patch.object(config, "USE_REAL_LLM", False), patch.object(
            llm_client, "_call_llm", side_effect=AssertionError("unexpected provider call")
        ) as provider_call:
            result = llm_client.rewrite_news("반도체 수출 증가", "수출이 증가했다.")
        self.assertTrue(result["beginner"])
        provider_call.assert_not_called()

    def test_provider_timeout_returns_fallback(self):
        with (
            patch.object(config, "USE_REAL_LLM", True),
            patch.object(llm_client, "_rewrite_cache", {}),
            patch.object(
                llm_client, "_call_llm", side_effect=TimeoutError("request timeout")
            ) as provider_call,
        ):
            result = llm_client.rewrite_news("수출 회복", "수출이 개선됐다.")
        self.assertTrue(result["beginner"])
        provider_call.assert_called_once()

    def test_llm_opt_in_does_not_implicitly_enable_paid_embeddings(self):
        with (
            patch.object(config, "USE_REAL_LLM", True),
            patch.object(config, "USE_REAL_EMBEDDINGS", False),
            patch.object(config, "OPENAI_API_KEY", "test-key"),
            patch.object(vector_store, "_real_embed", side_effect=AssertionError("paid call")),
        ):
            actual = vector_store.embed("local test")
            expected = vector_store._fake_embed("local test")
        self.assertEqual(actual, expected)

    def test_embeddings_require_separate_opt_in_and_key(self):
        with (
            patch.object(config, "USE_REAL_EMBEDDINGS", True),
            patch.object(config, "OPENAI_API_KEY", "test-key"),
            patch.object(vector_store, "_real_embed", return_value=[0.25]) as real_embed,
        ):
            self.assertEqual(vector_store.embed("test"), [0.25])
        real_embed.assert_called_once_with("test")

    def test_health_reports_fallback_without_secrets(self):
        with (
            patch.object(config, "USE_REAL_LLM", False),
            patch.object(config, "LLM_PROVIDER", "gemini"),
            patch.object(config, "GEMINI_API_KEY", "configured-secret"),
        ):
            result = health()
        self.assertFalse(result["llmEnabled"])
        self.assertTrue(result["llmFallback"])
        self.assertEqual(result["llmMode"], "fallback")
        self.assertEqual(result["llmProvider"], "disabled")
        self.assertNotIn("configured-secret", str(result))


if __name__ == "__main__":
    unittest.main()
