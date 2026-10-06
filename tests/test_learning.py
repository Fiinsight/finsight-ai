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

    def test_photo_captions_and_reporter_credit_do_not_replace_article_facts(self):
        body = '[연합뉴스 자료사진. 현대로템 제공. 재판매 및 DB 금지] (서울=연합뉴스) 황철환 기자 = DS증권은 목표주가를 22만6천원으로 낮췄다. 매출은 전년 동기 대비 12.5% 증가했다.'
        result = reading_aid(LearningRequest(title='목표가 조정', body=body, level='beginner'))
        self.assertIn('22만6천원', result.summary)
        self.assertIn('12.5%', result.summary)
        self.assertNotIn('자료사진', result.summary)
        self.assertNotIn('기자 =', result.summary)
        caption = '(서울=연합뉴스) 박동주 기자 = 딜링룸에서 직원들이 업무를 보고 있다. 2026.10.2 photo@yna.co.kr 실제 기사에서 수출이 12.5% 증가했다.'
        self.assertEqual(llm_client._clean_article_text('수출 증가', caption), '실제 기사에서 수출이 12.5% 증가했다.')
        self.assertEqual(llm_client._clean_article_text('미 증시', '사진=AFP 나스닥이 0.76% 올랐다.'), '나스닥이 0.76% 올랐다.')
