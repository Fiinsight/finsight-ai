"""The manual EXCERPT path is prepared and tested with mock DBs, never applied here."""
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import llm_client
from scripts import rewrite_news_batch as batch


def article():
    return {'id': 1, 'title': '실적 발표', 'url': 'https://fixture.test/news',
            'raw_content': '삼성전자(005930)가 영업이익 12조1000억원을 기록했다고 밝혔다.',
            'published_at': datetime.now(timezone.utc), 'rewrite_mode': 'EXCERPT',
            **{key: 'old' for key in batch.EXCERPT_COLUMNS}, 'rewrite_retry_pending': True}


def result():
    return llm_client.rewrite_news(article()['title'], article()['raw_content'], allow_llm=False)


def test_excerpt_dry_run_is_read_only_recent_and_does_not_generate(monkeypatch, capsys):
    calls = []
    @contextmanager
    def database(**kwargs):
        assert kwargs == {}
        def execute(sql, params):
            assert "published_at>=%s" in sql and "rewrite_mode='EXCERPT'" in sql
            assert 'coalesce(rewrite_mode' not in sql
            assert 6.99 < (datetime.now(timezone.utc) - params[0]).total_seconds() / 86400 < 7.01
            calls.append(sql)
            return SimpleNamespace(fetchall=lambda: [article()])
        yield SimpleNamespace(execute=execute)
    monkeypatch.setattr(batch, 'database', database)
    generate = Mock(side_effect=AssertionError('dry run must not generate'))
    monkeypatch.setattr(batch.llm_client, 'rewrite_news', generate)
    monkeypatch.setattr('sys.argv', ['batch', '--excerpt', '--since', '2000-01-01T00:00:00+00:00', '--limit', '1000'])
    batch.main()
    assert len(calls) == 1 and '"apply": false' in capsys.readouterr().out
    generate.assert_not_called()


def test_excerpt_apply_bypasses_paid_providers_and_persists_summaries_and_reasons(monkeypatch, capsys):
    calls = []
    @contextmanager
    def database(**kwargs):
        calls.append(kwargs)
        def execute(sql, params):
            if not kwargs:
                return SimpleNamespace(fetchall=lambda: [article()])
            assert "rewrite_mode='EXCERPT'" in sql
            assert 'raw_content IS NOT DISTINCT FROM' in sql and 'published_at IS NOT DISTINCT FROM' in sql
            for key in batch.EXCERPT_COLUMNS:
                assert key + '=%s' in sql and key + ' IS NOT DISTINCT FROM %s' in sql
            assert not any('005930' in str(value) for value in (params[0], params[4]))
            assert '요인을 확인해요' in params[4]
            return SimpleNamespace(rowcount=1)
        yield SimpleNamespace(execute=execute)
    monkeypatch.setattr(batch, 'database', database)
    monkeypatch.setattr(batch.config, 'REWRITE_WITH_LLM', False)
    monkeypatch.setattr(batch.llm_client, '_real_llm_calls', 99999)
    monkeypatch.setattr(batch.llm_client, '_call_gemini', Mock(side_effect=AssertionError('paid call')))
    monkeypatch.setattr(batch.llm_client, '_call_ollama', Mock(side_effect=AssertionError('local LLM call')))
    monkeypatch.setattr(batch.rewrite_budget, 'peek', Mock(side_effect=AssertionError('old rewrite ledger')))
    monkeypatch.setattr('sys.argv', ['batch', '--excerpt', '--since', '2000-01-01T00:00:00+00:00', '--apply'])
    batch.main()
    assert calls == [{}, {'readonly': False}]
    assert '"stored": 1' in capsys.readouterr().out


@pytest.mark.parametrize('mode', ['REWRITTEN', None])
def test_excerpt_persistence_rejects_other_modes(mode):
    database = Mock()
    payload = result() | {'mode': mode}
    assert batch.persist_excerpt(database, article(), payload) == 0
    database.execute.assert_not_called()


def test_excerpt_persistence_rejects_empty_results():
    database = Mock()
    assert batch.persist_excerpt(database, article(), result() | {'beginner': ''}) == 0
    database.execute.assert_not_called()


def test_identical_excerpt_is_an_idempotent_no_op():
    payload = result()
    row = article() | {**{'rewritten_' + level: payload[level] for level in ('beginner', 'normal', 'analyst')},
                       'importance_reason': payload['importanceReason'],
                       **{'importance_reason_' + level: payload['importanceReasons'][level] for level in ('beginner', 'normal', 'analyst')},
                       'rewrite_retry_pending': False}
    database = Mock()
    assert batch.persist_excerpt(database, row, payload) == 0
    database.execute.assert_not_called()


def test_concurrent_change_is_not_reported_as_saved():
    database = Mock()
    database.execute.return_value.rowcount = 0
    assert batch.persist_excerpt(database, article(), result()) == 0


def test_future_or_naive_since_is_rejected_before_database_access(monkeypatch):
    database = Mock(side_effect=AssertionError('invalid CLI must not connect'))
    monkeypatch.setattr(batch, 'database', database)
    for value in ('2099-01-01T00:00:00+00:00', '2026-11-02T00:00:00'):
        monkeypatch.setattr('sys.argv', ['batch', '--excerpt', '--since', value])
        with pytest.raises(SystemExit):
            batch.main()
    database.assert_not_called()


@pytest.mark.parametrize('mode', ['REWRITTEN', None])
def test_preexisting_non_excerpt_rows_are_never_written(mode):
    database = Mock()
    assert batch.persist_excerpt(database, article() | {'rewrite_mode': mode}, result()) == 0
    database.execute.assert_not_called()
