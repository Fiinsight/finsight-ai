import pytest
from app.services.llm_client import _mock_rewrite_news, _reading_summary, _clean_article_text, _mock_explain_term

ARTICLE_232 = "코스피는 반도체 약세에 2.5% 급락했다. 외국인은 코스피200선물시장에서도 3천223억원 매도 우위다. 코스닥 시장에서도 외국인은 644억원 매도 우위다."

def test_232_keeps_lead_and_separates_evidence_figures_and_risk():
    beginner = _reading_summary("코스피·코스닥 급락", ARTICLE_232, "beginner")
    assert "코스피는 반도체 약세에 2.5% 급락했어요." in beginner
    assert "우위다" not in beginner
    analyst = _reading_summary("코스피·코스닥 급락", ARTICLE_232, "analyst")
    evidence, rest = analyst.split("\n\n수치·비교 기준\n")
    figures, risk = rest.split("\n\n리스크·확인할 점\n")
    assert figures not in evidence
    assert "매도 우위" in risk

@pytest.mark.parametrize("prefix", ["AFP연합뉴스 ", "2026.7.24 ", "2026.10.12 [공동취재] (서울=연합뉴스) 한지훈 채새롬 기자 = "])
def test_credit_prefixes(prefix):
    assert _clean_article_text("별도 제목", prefix + "반도체 수출이 12.5% 증가했다.") == "반도체 수출이 12.5% 증가했다."

def test_index_explanation_uses_known_definition_without_appending_it_to_context():
    result = _mock_explain_term("코스피", ARTICLE_232, "유가증권시장 지수입니다.")
    assert result["definition"] == "유가증권시장 지수입니다."
    assert "유가증권시장 지수입니다" not in result["contextExplanation"]
    assert "기본 설명이 없는" not in result["contextExplanation"]
    assert "개별 종목은 지수와 다르게" in result["marketImpact"]

def test_no_terms_means_no_placeholder_and_fx_has_no_company_template():
    empty = _mock_rewrite_news("행사 개최", "오늘 행사에는 여러 사람이 참석했습니다.")
    assert empty["importanceReason"] is None
    assert "핵심 지표" not in empty["normal"]
    fx = _mock_rewrite_news("환율 상승", "환율이 1350원으로 올랐다. 환율 변화를 확인했다. 반도체가 한 번 언급됐다.")
    assert "반도체" not in fx["importanceReason"]
    assert "매출·비용" not in fx["importanceReason"]
