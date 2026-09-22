import json
import tempfile
import unittest
from pathlib import Path

from ml.data import chronological_split, read_jsonl


class MlDataTest(unittest.TestCase):
    def test_split_keeps_time_order(self):
        rows = [
            {"title": "a", "body": "", "label": "NEGATIVE", "published_at": "2026-01-01"},
            {"title": "b", "body": "", "label": "NEUTRAL", "published_at": "2026-01-02"},
            {"title": "c", "body": "", "label": "POSITIVE", "published_at": "2026-01-03"},
            {"title": "d", "body": "", "label": "POSITIVE", "published_at": "2026-01-04"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            train, valid, test = chronological_split(read_jsonl(path), 0.5, 0.25)
        self.assertEqual([row.title for row in train], ["a", "b"])
        self.assertEqual([row.title for row in valid], ["c"])
        self.assertEqual([row.title for row in test], ["d"])


if __name__ == "__main__":
    unittest.main()
