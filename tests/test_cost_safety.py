import tempfile
import unittest
from unittest.mock import patch

from app import config
from app.main import health
from app.services import llm_client, vector_store
from app.services.ml_sentiment import predict_sentiment


class CostSafetyTest(unittest.TestCase):
    def test_rule_fallback_respects_rate_context(self):
        result = predict_sentiment("美 금리 급등에 국고채 금리 상승", "국채 금리가 올랐다.")
        self.assertEqual(result["label"], "NEGATIVE")

    def test_llm_disabled_never_dispatches_to_provider(self):
        with patch.object(config, "USE_REAL_LLM", False), patch.object(
            llm_client, "_call_llm", side_effect=AssertionError("unexpected provider call")
        ) as provider_call:
            result = llm_client.rewrite_news("반도체 수출 증가", "수출이 증가했다.")
        self.assertTrue(result["beginner"])
        provider_call.assert_not_called()

    def test_feedback_default_flag_never_dispatches_to_any_provider(self):
        with patch.object(config, "USE_REAL_LLM", False), patch.object(config, "FEEDBACK_WITH_LLM", False), patch.object(llm_client, "_call_llm", side_effect=AssertionError("paid call")) as paid, patch.object(llm_client, "_call_gemini", side_effect=AssertionError("real call")) as gemini:
            result = llm_client.generate_feedback("매출이 증가했다.", "UP", "UP", 1.2)
        self.assertEqual(result["mode"], "RULE")
        paid.assert_not_called(); gemini.assert_not_called()

    def test_provider_timeout_returns_fallback(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(config, "REWRITE_WITH_LLM", True),
            patch.object(config, "REWRITE_LEDGER_PATH", directory + "/budget.sqlite3"),
            patch.object(
                llm_client, "_call_gemini", side_effect=TimeoutError("request timeout")
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

    def test_real_llm_process_cap_stops_unbounded_calls(self):
        with (
            patch.object(config, "MAX_REAL_LLM_CALLS_PER_PROCESS", 1),
            patch.object(config, "LLM_PROVIDER", "gemini"),
            patch.object(llm_client, "_real_llm_calls", 0),
            patch.object(llm_client, "_call_gemini", return_value="ok"),
        ):
            self.assertEqual(llm_client._call_llm("first"), "ok")
            with self.assertRaises(RuntimeError):
                llm_client._call_llm("second")


if __name__ == "__main__":
    unittest.main()


def test_ollama_api_requests_and_other_features_never_dispatch_to_paid_providers(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    with (
        patch.object(config,'LLM_PROVIDER','ollama'),
        patch.object(config,'REWRITE_WITH_LLM',True),
        patch.object(config,'USE_REAL_LLM',True),
        patch.object(config,'REWRITE_LEDGER_PATH',str(tmp_path/'unused.db')),
        patch.object(llm_client,'_call_claude',side_effect=AssertionError('paid Claude call')) as claude,
        patch.object(llm_client,'_call_gemini',side_effect=AssertionError('paid Gemini call')) as gemini,
        patch('http.client.HTTPConnection',side_effect=AssertionError('real-time Ollama call')) as local,
    ):
        response=TestClient(app).post('/ai/news/rewrite',json={'title':'수출 증가','body':'수출액은 전년보다 12.5% 늘었다.','local_batch':True})
        assert response.status_code==200 and response.json()['mode']=='EXCERPT'
        assert not (tmp_path/'unused.db').exists()
        try: llm_client._call_llm('another feature')
        except RuntimeError: pass
        else: raise AssertionError('Ollama must be batch-only')
        claude.assert_not_called();gemini.assert_not_called();local.assert_not_called()


def test_local_batch_rejects_paid_provider_and_non_loopback_url_without_any_network(tmp_path):
    with (
        patch.object(config,'REWRITE_WITH_LLM',True),
        patch.object(config,'REWRITE_LEDGER_PATH',str(tmp_path/'budget.db')),
        patch.object(config,'LLM_PROVIDER','gemini'),
        patch.object(llm_client,'_call_gemini',side_effect=AssertionError('paid call')) as paid,
        patch('http.client.HTTPConnection',side_effect=AssertionError('external request')) as http,
    ):
        assert llm_client.rewrite_news('수출','수출액은 전년보다 늘었다.',local_batch=True)['mode']=='EXCERPT'
        paid.assert_not_called();http.assert_not_called()
        with patch.object(config,'LLM_PROVIDER','ollama'),patch.object(config,'OLLAMA_MODEL','fixture'),patch.object(config,'OLLAMA_BASE_URL','http://external.test'):
            assert llm_client.rewrite_news('수출','수출액은 전년보다 늘었다.','external',local_batch=True)['mode']=='EXCERPT'
        paid.assert_not_called();http.assert_not_called()


def test_disabled_rewrite_flag_blocks_local_batch_even_when_ollama_selected():
    with patch.object(config,'LLM_PROVIDER','ollama'),patch.object(config,'REWRITE_WITH_LLM',False),patch('http.client.HTTPConnection') as http:
        assert llm_client.rewrite_news('수출','수출액은 전년보다 늘었다.',local_batch=True)['mode']=='EXCERPT'
        http.assert_not_called()
