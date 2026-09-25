import unittest

from app.services.llm_client import _mock_market_impact, _mock_rewrite_news, _mock_explain_term, _mock_generate_feedback


class MarketImpactFallbackTest(unittest.TestCase):
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

    def test_term_fallback_is_grounded_in_context(self):
        result = _mock_explain_term("기준금리", "한국은행이 기준금리를 동결했다.")
        self.assertIn("한국은행이 기준금리를 동결했다", result["contextExplanation"])
        self.assertIn("기준", result["definition"])

    def test_feedback_alignment_is_not_llm_dependent(self):
        result = _mock_generate_feedback("금리 동결", "UP", "DOWN", None)
        self.assertFalse(result["isAligned"])


if __name__ == "__main__":
    unittest.main()
