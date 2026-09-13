"""Single entry point for all LLM text-generation calls used by the routers.

Safe-by-default: when `config.USE_REAL_LLM` is False (the default), every
function here returns a realistic-looking canned Korean response and never
touches the network. When it is True, we call the Anthropic API and, if that
call fails for any reason (missing/invalid key, network error, rate limit,
malformed response), we log a warning and gracefully fall back to the same
mock response instead of letting the request crash with a 500.
"""

from __future__ import annotations

import json
import logging
import re

from app import config

logger = logging.getLogger(__name__)

_anthropic_client = None
_anthropic_init_warned = False
_gemini_client = None
_gemini_init_warned = False


def _get_anthropic_client():
    """Lazily create (and cache) the Anthropic client. Raises on any failure."""
    global _anthropic_client, _anthropic_init_warned

    if _anthropic_client is not None:
        return _anthropic_client

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")

    try:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    except Exception as exc:  # pragma: no cover - defensive, e.g. package missing
        if not _anthropic_init_warned:
            logger.warning("Anthropic 클라이언트 초기화에 실패했습니다: %s", exc)
            _anthropic_init_warned = True
        raise

    return _anthropic_client


def _call_claude(prompt: str, max_tokens: int = 1024) -> str:
    """Make a single real Claude call and return the concatenated text output."""
    client = _get_anthropic_client()
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )


def _get_gemini_client():
    """Lazily create (and cache) the Gemini client. Raises on any failure."""
    global _gemini_client, _gemini_init_warned

    if _gemini_client is not None:
        return _gemini_client

    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")

    try:
        from google import genai

        _gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
    except Exception as exc:  # pragma: no cover - defensive, e.g. package missing
        if not _gemini_init_warned:
            logger.warning("Gemini 클라이언트 초기화에 실패했습니다: %s", exc)
            _gemini_init_warned = True
        raise

    return _gemini_client


def _call_gemini(prompt: str, max_tokens: int = 1024) -> str:
    """Make a single real Gemini call and return the text output."""
    client = _get_gemini_client()
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
    )
    return response.text or ""


def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    """Dispatch to whichever provider USE_REAL_LLM/LLM_PROVIDER selects."""
    if config.LLM_PROVIDER == "gemini":
        return _call_gemini(prompt, max_tokens)
    return _call_claude(prompt, max_tokens)


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response (handles code fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("모델 응답에서 JSON 객체를 찾을 수 없습니다.")
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# 1) 뉴스 리라이팅 (초보자 / 일반 / 분석용 + 중요도 이유 + 핵심 용어)
# ---------------------------------------------------------------------------


def _mock_rewrite_news(title: str, raw_content: str) -> dict:
    return {
        "beginner": (
            f"'{title}' 소식을 쉽게 풀어보면, 마치 우리 동네 가게 매출이 오르내리듯 "
            "회사나 시장 전체에 영향을 줄 수 있는 소식이에요. 어려운 용어에 얽매이기보다 "
            "'오늘 어떤 일이 일어났는지'부터 파악해보세요."
        ),
        "normal": (
            f"{title} 관련 핵심 내용을 요약하면, 시장 참여자들이 주목할 만한 변화가 발생했으며 "
            "관련 지표와 후속 발표를 함께 확인할 필요가 있습니다."
        ),
        "analyst": (
            f"투자 관점에서 '{title}'은(는) 관련 업종의 수급과 실적 전망에 영향을 줄 수 있는 이벤트입니다. "
            "단기 변동성뿐 아니라 중장기 추세 전환 가능성까지 함께 점검해야 합니다."
        ),
        "importanceReason": (
            "이 뉴스가 기업 실적, 금리, 환율, 수급 중 어떤 요소와 연결되는지 확인해야 합니다."
        ),
        "detectedTerms": ["실적", "수급", "환율"],
    }


def _build_rewrite_prompt(title: str, raw_content: str) -> str:
    return f"""당신은 초보 투자자를 돕는 금융 뉴스 편집자입니다.
아래 뉴스를 세 가지 눈높이로 다시 작성하고, 이 뉴스가 왜 중요한지, 그리고 기사에 등장하는
핵심 금융 용어를 함께 알려주세요.

[뉴스 제목]
{title}

[뉴스 본문]
{raw_content}

다음 JSON 형식으로만 응답하세요. 코드블록이나 다른 설명 없이 순수 JSON만 출력하세요.
{{
  "beginner": "초보자를 위한 쉬운 비유와 용어 설명을 포함한 재구성 (3~5문장)",
  "normal": "일반 투자자를 위한 표준 요약 (2~4문장)",
  "analyst": "투자 관점의 분석을 포함한 심화 해설 (3~5문장)",
  "importanceReason": "이 뉴스가 왜 중요한지에 대한 한두 문장 설명",
  "detectedTerms": ["기사에 등장한 핵심 금융 용어", "..."]
}}"""


# The backend calls /ai/news/rewrite 3 times per article — once per reading
# level — but a single call here already generates all 3 levels at once and
# the router just picks one, throwing the other 2 away. On a rate/quota
# limited free-tier key that wastes 2 of every 3 calls, so cache the full
# per-article result and reuse it across the 3 level requests instead of
# hitting the LLM 3 times for the same article.
_rewrite_cache: dict[str, dict] = {}


def rewrite_news(title: str, raw_content: str) -> dict:
    """Rewrite a news article at 3 reading levels plus an importance reason.

    Returns a dict with keys: beginner, normal, analyst, importanceReason,
    detectedTerms.
    """
    mock = _mock_rewrite_news(title, raw_content)
    if not config.USE_REAL_LLM:
        return mock

    cache_key = f"{title}::{hash(raw_content)}"
    cached = _rewrite_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        raw = _call_llm(_build_rewrite_prompt(title, raw_content), max_tokens=1500)
        data = _extract_json(raw)
        result = {
            "beginner": data.get("beginner", mock["beginner"]),
            "normal": data.get("normal", mock["normal"]),
            "analyst": data.get("analyst", mock["analyst"]),
            "importanceReason": data.get("importanceReason", mock["importanceReason"]),
            "detectedTerms": data.get("detectedTerms", mock["detectedTerms"]),
        }
        _rewrite_cache[cache_key] = result
        return result
    except Exception as exc:
        logger.warning("뉴스 리라이팅 LLM 호출 실패, 목업 응답으로 대체합니다: %s", exc)
        return mock


# ---------------------------------------------------------------------------
# 2) 용어 설명 (정의 / 이 뉴스에서의 의미 / 시장 영향)
# ---------------------------------------------------------------------------


def _mock_explain_term(term: str, context: str | None) -> dict:
    result: dict = {
        "definition": (
            f"'{term}'은(는) 금융 뉴스에서 자주 등장하는 용어로, 일반적으로 시장 참여자들의 "
            "심리나 자금 흐름과 관련된 개념입니다."
        ),
        "contextExplanation": None,
        "marketImpact": None,
    }
    if context:
        result["contextExplanation"] = (
            f"이번 기사에서 '{term}'은(는) 해당 맥락에서 시장 참여자들의 기대감이나 반응을 "
            "설명하는 근거로 사용되었습니다."
        )
        result["marketImpact"] = (
            f"'{term}'과(와) 관련된 지표가 추가로 확인될 경우 관련 종목이나 업종의 단기 "
            "변동성이 커질 수 있습니다."
        )
    return result


def _build_term_prompt(term: str, context: str | None) -> str:
    context_block = context if context else "(제공된 기사 맥락 없음)"
    return f"""당신은 초보 투자자에게 금융 용어를 쉽게 설명하는 도우미입니다.
아래 용어를 '정의 / 이 뉴스에서의 의미 / 시장 영향' 3단 구조로 설명하세요.
기사 맥락이 없으면 contextExplanation과 marketImpact는 null로 응답하세요.

[용어]
{term}

[기사 맥락]
{context_block}

다음 JSON 형식으로만 응답하세요. 코드블록이나 다른 설명 없이 순수 JSON만 출력하세요.
{{
  "definition": "용어의 일반적인 정의 (1~2문장)",
  "contextExplanation": "이 뉴스 맥락에서의 의미 (없으면 null)",
  "marketImpact": "시장에 미치는 영향 (없으면 null)"
}}"""


def explain_term(term: str, context: str | None) -> dict:
    """Explain a financial term, optionally grounded in a news context.

    Returns a dict with keys: definition, contextExplanation, marketImpact.
    """
    mock = _mock_explain_term(term, context)
    if not config.USE_REAL_LLM:
        return mock

    try:
        raw = _call_llm(_build_term_prompt(term, context), max_tokens=700)
        data = _extract_json(raw)
        return {
            "definition": data.get("definition", mock["definition"]),
            "contextExplanation": data.get("contextExplanation", mock["contextExplanation"]),
            "marketImpact": data.get("marketImpact", mock["marketImpact"]),
        }
    except Exception as exc:
        logger.warning("용어 설명 LLM 호출 실패, 목업 응답으로 대체합니다: %s", exc)
        return mock


# ---------------------------------------------------------------------------
# 3) 판단 피드백 (정확했는지 + 이유 목록)
# ---------------------------------------------------------------------------


def _mock_generate_feedback(
    news_summary: str,
    user_choice: str,
    actual_direction: str,
    actual_change_percent: float | None,
) -> dict:
    is_aligned = user_choice.strip().upper() == actual_direction.strip().upper()
    change_text = (
        f" (실제 변동률 {actual_change_percent:+.2f}%)" if actual_change_percent is not None else ""
    )

    if is_aligned:
        feedback_text = (
            f"사용자의 예측({user_choice})이 실제 결과({actual_direction}){change_text}와 일치했습니다. "
            "뉴스의 핵심 요인과 시장 반응을 잘 연결한 판단입니다."
        )
        reasons = [
            "뉴스에서 언급된 핵심 이슈가 실제 가격 변동의 주요 원인과 일치합니다.",
            "시장 참여자들의 일반적인 반응 방향과 예측이 같은 방향을 가리켰습니다.",
        ]
    else:
        feedback_text = (
            f"사용자의 예측({user_choice})이 실제 결과({actual_direction}){change_text}와 달랐습니다. "
            "뉴스 내용과 실제 시장 반응 사이의 차이를 점검해보세요."
        )
        reasons = [
            "뉴스의 단기 재료와 실제 가격 반영 시점이 어긋났을 수 있습니다.",
            "다른 거시 지표(금리, 환율 등)가 더 크게 작용했을 가능성이 있습니다.",
        ]
    reasons.append("다음에는 관련 종목의 거래량과 업종 지수도 함께 비교해보세요.")

    return {
        "isAligned": is_aligned,
        "feedbackText": feedback_text,
        "reasons": reasons,
    }


def _build_feedback_prompt(
    news_summary: str,
    user_choice: str,
    actual_direction: str,
    actual_change_percent: float | None,
) -> str:
    change_text = f"{actual_change_percent}%" if actual_change_percent is not None else "정보 없음"
    return f"""당신은 초보 투자자의 판단을 코칭하는 금융 튜터입니다.
아래 정보를 바탕으로 사용자의 예측이 실제 결과와 맞았는지 평가하고, 그 이유를 짧게 알려주세요.

[뉴스 요약]
{news_summary}

[사용자 예측]
{user_choice}

[실제 결과 방향]
{actual_direction}

[실제 변동률]
{change_text}

다음 JSON 형식으로만 응답하세요. 코드블록이나 다른 설명 없이 순수 JSON만 출력하세요.
{{
  "isAligned": true 또는 false,
  "feedbackText": "판단이 정확했는지/틀렸는지에 대한 종합 피드백 (2~3문장)",
  "reasons": ["왜 정확한(혹은 부정확한) 판단인지에 대한 짧은 이유", "..."]
}}
reasons는 2개에서 4개 사이로 작성하세요."""


def generate_feedback(
    news_summary: str,
    user_choice: str,
    actual_direction: str,
    actual_change_percent: float | None,
) -> dict:
    """Compare a user's prediction against the actual market outcome.

    Returns a dict with keys: isAligned, feedbackText, reasons.
    """
    mock = _mock_generate_feedback(news_summary, user_choice, actual_direction, actual_change_percent)
    if not config.USE_REAL_LLM:
        return mock

    try:
        prompt = _build_feedback_prompt(news_summary, user_choice, actual_direction, actual_change_percent)
        raw = _call_llm(prompt, max_tokens=700)
        data = _extract_json(raw)
        return {
            "isAligned": bool(data.get("isAligned", mock["isAligned"])),
            "feedbackText": data.get("feedbackText", mock["feedbackText"]),
            "reasons": data.get("reasons", mock["reasons"]),
        }
    except Exception as exc:
        logger.warning("피드백 생성 LLM 호출 실패, 목업 응답으로 대체합니다: %s", exc)
        return mock
