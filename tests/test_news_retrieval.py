import os
import unittest

from app.services.news_retrieval import search_news


class NewsRetrievalTest(unittest.TestCase):
    def test_unconfigured_index_is_free_and_safe(self):
        previous = os.environ.pop("ML_NEWS_INDEX_PATH", None)
        try:
            self.assertEqual(search_news("반도체", 3)["basis"], "INDEX_NOT_CONFIGURED")
        finally:
            if previous is not None:
                os.environ["ML_NEWS_INDEX_PATH"] = previous


if __name__ == "__main__":
    unittest.main()
