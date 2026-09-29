import unittest

from app.services.llm_client import (
    _mock_explain_term,
    _mock_generate_feedback,
    _mock_market_impact,
    _mock_rewrite_news,
    _clean_article_text,
    _split_sentences,
)


class MarketImpactFallbackTest(unittest.TestCase):
    def test_sentence_split_keeps_decimal_values_intact(self):
        sentences = _split_sentences("해외직접투자가 32.3% 증가했다. 수출액은 4.48% 늘었다.")

        self.assertEqual(
            sentences,
            ["해외직접투자가 32.3% 증가했다.", "수출액은 4.48% 늘었다."],
        )

    def test_detected_terms_does_not_invent_market_impact(self):
        result = _mock_rewrite_news("정책 발표", "새로운 정책 세부안이 공개됐다.")

        self.assertNotIn("시장 영향", result["detectedTerms"])

    def test_positive_result_has_target_and_evidence(self):
        result = _mock_market_impact(
            "반도체 수출 회복세, 실적 기대감 확대",
            "반도체 수출이 증가했고 흑자 전환이 확인됐다.",
            "005930",
        )

        self.assertEqual(result["direction"], "POSITIVE")
        self.assertIn("관련 종목 005930", result["targets"])
        self.assertTrue(result["evidence"])
        self.assertEqual(result["basis"], "RULE_BASED_FALLBACK")

    def test_conflicting_signal_stays_neutral(self):
        result = _mock_market_impact(
            "회복과 하락이 함께 나타남",
            "시장에는 회복과 하락이 동시에 나타났다.",
            None,
        )

        self.assertEqual(result["direction"], "NEUTRAL")
        self.assertLess(result["confidence"], 0.5)
        self.assertTrue(result["caveats"])

    def test_no_directional_evidence_is_cautious(self):
        result = _mock_market_impact("정책 발표", "새로운 정책 세부안이 공개됐다.", None)

        self.assertEqual(result["direction"], "NEUTRAL")
        self.assertEqual(result["confidence"], 0.35)
        self.assertIn("단정할 수 있는 근거", result["evidence"][0])

    def test_conflicting_article_signals_are_neutral(self):
        result = _mock_market_impact(
            "수출 증가에도 비용 부담 확대",
            "수출이 증가했지만 원자재 비용 부담이 확대됐다.",
            None,
        )
        self.assertEqual(result["direction"], "NEUTRAL")
        self.assertLessEqual(result["confidence"], 0.3)

    def test_rewrite_fallback_preserves_article_facts_and_levels(self):
        result = _mock_rewrite_news(
            "반도체 수출 증가",
            "반도체 수출액이 증가했다. HBM 수요가 확대됐다.",
        )
        for level in ("beginner", "normal", "analyst"):
            self.assertIn("반도체", result[level])
        self.assertIn("HBM", result["detectedTerms"])
        self.assertNotEqual(result["beginner"], result["analyst"])

    def test_rewrite_fallback_removes_search_chrome_and_internal_label(self):
        result = _mock_rewrite_news(
            "원화값 강세에도 순항",
            "원화값 강세에도 순항. Google 검색에서 매일경제 기사를 더 자주 볼 수 있습니다. AI 부품 수요가 늘었습니다.",
        )

        self.assertNotIn("Google 검색", result["beginner"])
        self.assertNotIn("NEUTRAL", result["beginner"])
        self.assertNotIn("원화값 강세에도 순항", result["beginner"])
        self.assertIn("AI", result["detectedTerms"])
        self.assertIn("수요가 늘었습니다", result["beginner"])

    def test_rewrite_fallback_removes_byline_caption_and_copyright(self):
        result = _mock_rewrite_news(
            "헬릭스 데이터센터 투자",
            "홍길동 기자. 사진=연합뉴스. 삼성 계열사가 헬릭스에 투자했다. Copyright FinSight.",
        )
        for level in ("beginner", "normal", "analyst"):
            self.assertNotIn("기자", result[level])
            self.assertNotIn("연합뉴스", result[level])
            self.assertNotIn("Copyright", result[level])
        self.assertNotIn("삼성 계열사가 헬릭스에 투자했다.", result["beginner"])

    def test_rewrite_fallback_removes_bracketed_photo_caption_and_preserves_article(self):
        raw = "[촬영 정회인 기자.] 재판매 및 DB 금지.] (서울=연합뉴스) 정회인 기자 = 한국 증시의 추가 상승을 위해 제도 개선이 필요하다."
        result = _mock_rewrite_news("AI 투자 늘어난다", raw)

        for level in ("beginner", "normal", "analyst"):
            self.assertNotIn("촬영", result[level])
            self.assertNotIn("정회인 기자", result[level])
            self.assertNotIn("재판매 및 DB 금지", result[level])
        self.assertIn("한국 증시의 추가 상승", result["normal"])

    def test_title_tags_are_not_article_noise(self):
        cleaned = _clean_article_text("[단독] 수출 전망", "[단독] 수출이 증가했다.")

        self.assertIn("[단독] 수출이 증가했다.", cleaned)

    def test_rewrite_fallback_has_distinct_level_structures(self):
        result = _mock_rewrite_news(
            "헬릭스 데이터센터 투자",
            "삼성 계열사가 헬릭스에 투자했다. 데이터센터 사업 협력을 검토한다.",
        )
        self.assertIn("쉽게 말하면", result["beginner"])
        self.assertIn("확인할 점은", result["normal"])
        self.assertIn("투자·이벤트 구조", result["analyst"])
        self.assertIn("위험 요인", result["analyst"])

    def test_beginner_uses_haeyo_and_explains_ai_infrastructure(self):
        result = _mock_rewrite_news(
            "헬릭스 데이터센터 투자",
            "삼성 계열사가 헬릭스에 투자했다. 헬릭스는 인공지능 인프라를 만든다.",
        )
        self.assertIn("했어요", result["beginner"])
        self.assertIn("인공지능 인프라는", result["beginner"])
        self.assertNotIn("투자했다.", result["beginner"])

    def test_importance_reason_uses_article_evidence_and_check_variable(self):
        result = _mock_rewrite_news(
            "반도체 수출 증가",
            "반도체 수출액이 증가했다. HBM 수요가 확대됐다.",
        )
        self.assertIn("반도체 수출액이 증가했다", result["importanceReason"])
        self.assertIn("수출입 금액과 관련 기업의 매출을", result["importanceReason"])

    def test_importance_reason_admits_insufficient_evidence(self):
        result = _mock_rewrite_news("정책 발표", "새로운 정책 세부안이 공개됐다.")
        self.assertIn("구체적인 근거를 확인하지 못했습니다", result["importanceReason"])

    def test_term_fallback_is_grounded_in_context(self):
        result = _mock_explain_term("기준금리", "한국은행이 기준금리를 동결했다.")
        self.assertIn("한국은행이 기준금리를 동결했다", result["contextExplanation"])
        self.assertIn("기준", result["definition"])

    def test_feedback_alignment_is_not_llm_dependent(self):
        result = _mock_generate_feedback("금리 동결", "UP", "DOWN", None)
        self.assertFalse(result["isAligned"])


if __name__ == "__main__":
    unittest.main()
