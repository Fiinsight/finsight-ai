"""Tests never inherit real generation switches, budgets or SDK calls from .env."""
import pytest
from app import config
from app.services import llm_client


@pytest.fixture(autouse=True)
def no_live_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'USE_REAL_LLM', False)
    monkeypatch.setattr(config, 'REWRITE_WITH_LLM', False)
    monkeypatch.setattr(config, 'DOCENT_WITH_LLM', False)
    monkeypatch.setattr(config, 'USE_REAL_EMBEDDINGS', False)
    monkeypatch.setattr(config, 'LLM_PROVIDER', 'gemini')
    monkeypatch.setattr(config, 'REWRITE_LEDGER_PATH', str(tmp_path / 'rewrite.db'))
    monkeypatch.setattr(llm_client, '_real_llm_calls', 0)
    monkeypatch.setattr(llm_client, '_rewrite_llm_calls', 0)
    monkeypatch.setattr(llm_client, '_last_rewrite_started', None)
    def blocked(*args, **kwargs):
        raise AssertionError('Live provider is forbidden in pytest; mock it explicitly')
    monkeypatch.setattr(llm_client, '_call_gemini', blocked)
    monkeypatch.setattr(llm_client, '_call_claude', blocked)
