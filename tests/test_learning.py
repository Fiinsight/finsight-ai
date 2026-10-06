import unittest
from unittest.mock import patch
from app.routers.learning import LearningRequest, reading_aid
from app.services import llm_client

class LearningTest(unittest.TestCase):
    def test_source_grounded_levels_are_bounded_and_never_call_paid_models(self):
        body = '수출은 전년 동기 대비 12.5% 증가했다. 매출은 상승했다. 이익은 하락했다. 다음 실적은 확인이 필요하다.'
        with patch.object(llm_client, '_call_llm', side_effect=AssertionError('paid call')):
            results = [reading_aid(LearningRequest(title='수출 증가', body=body, level=level)) for level in ['beginner','normal','analyst']]
        self.assertIn('지난해 같은 기간', results[0].summary)
        self.assertIn('12.5%', results[0].summary)
        self.assertNotEqual(results[0].summary, results[2].summary)
        self.assertTrue(all(r.mode == 'RULE_FALLBACK' and len(r.summary) <= 601 for r in results))
        self.assertNotIn('70,000', results[0].summary)
