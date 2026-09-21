import unittest

from app.services.llm_client import _mock_market_impact


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


if __name__ == "__main__":
    unittest.main()
