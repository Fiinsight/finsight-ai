"""Optional DB access for explicit offline maintenance; never loads or prints .env."""
import os
from contextlib import contextmanager


@contextmanager
def database(*, readonly=True):
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise RuntimeError("Install requirements-ml.txt for offline DB scripts") from None
    url = os.getenv("DB_URL", "").removeprefix("jdbc:")
    if not url:
        raise RuntimeError("DB_URL must be exported for offline maintenance")
    try:
        connection = psycopg.connect(url, user=os.getenv("DB_USERNAME"), password=os.getenv("DB_PASSWORD"), row_factory=dict_row, connect_timeout=5)
    except Exception:
        raise RuntimeError("Offline database connection failed; credentials were not logged") from None
    with connection:
        connection.read_only = readonly
        yield connection


def cleaned_input(title, body):
    from app.services.llm_client import _clean_article_text, _split_sentences
    cleaned = _clean_article_text(title, body or "")
    lead = next(iter(_split_sentences(cleaned)), "")
    return cleaned, lead
