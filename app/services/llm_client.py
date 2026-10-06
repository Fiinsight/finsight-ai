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
import threading

from app import config

logger = logging.getLogger(__name__)

_anthropic_client = None
_anthropic_init_warned = False
_gemini_client = None
_gemini_init_warned = False
_real_llm_calls = 0
_real_llm_calls_lock = threading.Lock()


def _get_anthropic_client():
    """Lazily create (and cache) the Anthropic client. Raises on any failure."""
    global _anthropic_client, _anthropic_init_warned

    if _anthropic_client is not None:
        return _anthropic_client

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다.")

    try:
        import anthropic

        _anthropic_client = anthropic.Anthropic(
            api_key=config.ANTHROPIC_API_KEY,
            timeout=config.LLM_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
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
        from google.genai import types

        _gemini_client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(
                timeout=int(config.LLM_REQUEST_TIMEOUT_SECONDS * 1000)
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive, e.g. package missing
        if not _gemini_init_warned:
            logger.warning("Gemini 클라이언트 초기화에 실패했습니다: %s", exc)
            _gemini_init_warned = True
        raise

    return _gemini_client


def _call_gemini(prompt: str, max_tokens: int = 1024) -> str:
    """Make a single real Gemini call and return the text output."""
    client = _get_gemini_client()
    from google.genai import types

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=max_tokens),
    )
    return response.text or ""


def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    """Dispatch to whichever provider USE_REAL_LLM/LLM_PROVIDER selects."""
    global _real_llm_calls
    with _real_llm_calls_lock:
        if _real_llm_calls >= config.MAX_REAL_LLM_CALLS_PER_PROCESS:
            raise RuntimeError("프로세스의 실제 LLM 호출 상한에 도달했습니다.")
        _real_llm_calls += 1
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
# 0) 뉴스 시장 영향 분석 (대상 / 방향 / 근거 / 불확실성)
# ---------------------------------------------------------------------------


_IMPACT_POSITIVE_KEYWORDS = (
    "상승", "급등", "강세", "호조", "개선", "성장", "흑자", "회복", "증가", "상향", "돌파", "확대",
)
_IMPACT_NEGATIVE_KEYWORDS = (
    "하락", "급락", "약세", "부진", "우려", "적자", "감소", "하향", "둔화", "축소", "침체", "리스크", "부담", "비용",
)
_IMPACT_TARGET_KEYWORDS = {
    "반도체": "반도체 업종",
    "수출": "수출 기업",
    "환율": "환율 민감 기업 및 국내 시장",
    "금리": "금리 민감 업종",
    "코스피": "코스피 시장",
    "코스닥": "코스닥 시장",
    "채권": "채권 시장",
    "은행": "은행 업종",
    "자동차": "자동차 업종",
    "원자재": "원자재 관련 업종",
}


def _topic_direction(text: str) -> str | None:
    rate_topic = any(term in text for term in ("금리", "국채", "채권", "수익률"))
    if rate_topic:
        rises = any(term in text for term in ("금리 상승", "금리 급등", "금리 인상", "국채금리 상승", "국채 금리 상승", "수익률 상승", "수익률 급등"))
        falls = any(term in text for term in ("금리 하락", "금리 급락", "금리 인하", "국채금리 하락", "국채 금리 하락", "수익률 하락", "수익률 급락"))
        if rises and not falls:
            return "NEGATIVE"
        if falls and not rises:
            return "POSITIVE"
    if "환율" in text and not any(term in text for term in ("수출", "수입")):
        return "NEUTRAL"
    return None


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?。！？])(?!\d)\s*", text.strip()) if part.strip()]


def _article_sentences(title: str, body: str) -> list[str]:
    """Return source sentences, keeping the title available as evidence."""
    return _split_sentences(". ".join(part.strip() for part in (title, body) if part.strip()))


def _matching_sentences(sentences: list[str], keywords: tuple[str, ...], limit: int = 2) -> list[str]:
    return [sentence for sentence in sentences if any(keyword in sentence for keyword in keywords)][:limit]


def _detected_terms(text: str) -> list[str]:
    terms = (
        "기준금리", "금리", "환율", "원달러", "수출", "수입", "반도체", "HBM", "PF",
        "프로젝트파이낸싱", "연체율", "물가", "인플레이션", "영업이익", "매출", "수급",
        "변동성", "밸류에이션", "설비투자", "재고 조정", "공모주", "수요예측", "국채금리", "AI", "원화",
    )
    matches: list[tuple[int, str]] = []
    occupied: set[int] = set()
    for term in sorted(terms, key=len, reverse=True):
        for match in re.finditer(re.escape(term), text):
            positions = set(range(match.start(), match.end()))
            if not positions & occupied:
                occupied.update(positions)
                matches.append((match.start(), term))
    return list(dict.fromkeys(term for _, term in sorted(matches)))[:6]


def _mock_market_impact(title: str, body: str, related_symbol: str | None) -> dict:
    """Produce a cautious, explainable result without a network or paid model call."""
    source_text = ". ".join(part.rstrip(".!?。！？") for part in (title.strip(), body.strip()) if part)
    positive_hits = sum(source_text.count(keyword) for keyword in _IMPACT_POSITIVE_KEYWORDS)
    negative_hits = sum(source_text.count(keyword) for keyword in _IMPACT_NEGATIVE_KEYWORDS)
    score = positive_hits - negative_hits
    topic_direction = _topic_direction(source_text)

    if topic_direction is not None:
        direction = topic_direction
        confidence = 0.7 if topic_direction != "NEUTRAL" else 0.35
    elif positive_hits and negative_hits:
        direction = "NEUTRAL"
        confidence = 0.3
    elif score > 0:
        direction = "POSITIVE"
        confidence = min(0.85, 0.55 + score * 0.05)
    elif score < 0:
        direction = "NEGATIVE"
        confidence = min(0.85, 0.55 + abs(score) * 0.05)
    else:
        direction = "NEUTRAL"
        confidence = 0.35

    sentences = _split_sentences(source_text)
    evidence_keywords = _IMPACT_POSITIVE_KEYWORDS if score > 0 else _IMPACT_NEGATIVE_KEYWORDS
    evidence = [
        sentence for sentence in sentences
        if any(keyword in sentence for keyword in evidence_keywords)
    ][:2]
    if not evidence:
        evidence = ["본문에서 시장 방향을 단정할 수 있는 근거가 충분히 확인되지 않았습니다."]

    targets = [label for keyword, label in _IMPACT_TARGET_KEYWORDS.items() if keyword in source_text]
    if related_symbol:
        targets.insert(0, f"관련 종목 {related_symbol}")
    targets = list(dict.fromkeys(targets))[:4]
    if not targets:
        targets = ["관련 시장·업종(종목 정보 미제공)"]

    caveats = [
        "이 결과는 본문 키워드 기반의 비용 없는 fallback 분석이며 투자 판단이 아닙니다.",
        "실제 가격 반응은 발표 시점, 기대치, 수급과 다른 거시 변수에 따라 달라질 수 있습니다.",
    ]
    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "targets": targets,
        "evidence": evidence,
        "caveats": caveats,
        "basis": "RULE_BASED_FALLBACK",
    }


def _build_market_impact_prompt(title: str, body: str, related_symbol: str | None) -> str:
    symbol_text = related_symbol or "없음"
    return f"""당신은 금융 뉴스의 시장 영향을 분석하는 보수적인 리서치 도우미입니다.
기사에 없는 사실을 추측하지 말고, 본문에서 직접 확인 가능한 근거만 사용하세요.
영향 방향은 시장·업종·관련 종목 중 무엇을 기준으로 하는지 targets에 명시하세요.
근거가 부족하거나 방향이 충돌하면 NEUTRAL을 선택하고 confidence를 낮게 주세요.

[관련 종목 코드]
{symbol_text}

[뉴스 제목]
{title}

[뉴스 본문]
{body}

다음 JSON만 반환하세요.
{{
  "direction": "POSITIVE|NEUTRAL|NEGATIVE",
  "confidence": 0.0에서 1.0 사이의 숫자,
  "targets": ["영향 대상"],
  "evidence": ["본문에서 그대로 확인 가능한 근거를 요약한 문장"],
  "caveats": ["판단의 한계 또는 추가 확인사항"],
  "basis": "LLM"
}}
"""


def analyze_market_impact(title: str, body: str, related_symbol: str | None = None) -> dict:
    """Analyze direction with explicit targets and evidence, safely by default."""
    mock = _mock_market_impact(title, body, related_symbol)
    if not config.USE_REAL_LLM:
        return mock

    try:
        raw = _call_llm(_build_market_impact_prompt(title, body, related_symbol), max_tokens=900)
        data = _extract_json(raw)
        direction = str(data.get("direction", "NEUTRAL")).upper()
        if direction not in {"POSITIVE", "NEUTRAL", "NEGATIVE"}:
            direction = "NEUTRAL"
        confidence = float(data.get("confidence", mock["confidence"]))
        result = {
            "direction": direction,
            "confidence": round(max(0.0, min(1.0, confidence)), 2),
            "targets": [str(item) for item in data.get("targets", mock["targets"])][:4],
            "evidence": [str(item) for item in data.get("evidence", mock["evidence"])][:3],
            "caveats": [str(item) for item in data.get("caveats", mock["caveats"])][:3],
            "basis": "LLM",
        }
        # A model must not invent an evidence-free direction. Keep the
        # deterministic, article-grounded result when its cited evidence is
        # missing or unrelated to the supplied article.
        source_text = f"{title} {body}"
        if not result["evidence"] or not any(
            any(token in source_text for token in str(item).split()) for item in result["evidence"]
        ):
            return mock
        return result
    except Exception as exc:
        logger.warning("시장 영향 분석 LLM 호출 실패, fallback 응답으로 대체합니다: %s", exc)
        return mock


# ---------------------------------------------------------------------------
# 1) 뉴스 리라이팅 (초보자 / 일반 / 분석용 + 중요도 이유 + 핵심 용어)
# ---------------------------------------------------------------------------


_ARTICLE_NOISE_MARKERS = (
    "Google 검색에서",
    "검색에서 매일경제",
    "검색에서 한국경제",
    "기사를 더 자주 볼 수 있습니다",
    "원문 보기",
    "관련기사",
    "개인정보처리방침",
    "쿠키 설정",
)


def _clean_article_text(title: str, raw_content: str) -> str:
    """Remove publisher chrome and title duplication before any rewrite."""
    title_text = " ".join(title.split()).strip(" \t\n\r\"“”'‘’")
    title_key = re.sub(r"[^0-9a-zA-Z가-힣]", "", title_text).lower()
    title_prefix = re.split(r"[…,:：]", title_text, maxsplit=1)[0].strip()
    title_prefix_key = re.sub(r"[^0-9a-zA-Z가-힣]", "", title_prefix).lower()
    content = raw_content.replace("\r", "\n")
    content = re.sub(r"\[[^\]]{0,500}(?:자료사진|사진 제공|재판매|DB 금지)[^\]]{0,500}\]", " ", content)
    photo_credit = re.match(r"^(.{0,700}?)20\d{2}\.\d{1,2}\.\d{1,2}\s+[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\s*", content, re.S)
    if photo_credit and any(marker in photo_credit[1] for marker in ("사진", "딜링룸", "촬영")) and content[photo_credit.end():].strip():
        content = content[photo_credit.end():]
    content = re.sub(r"\([^()\n]{1,40}=연합뉴스\)\s*[가-힣·]{1,12}\s*기자\s*=\s*", "", content)
    content = re.sub(r"사진\s*=\s*(?:AFP|AP|EPA|로이터|연합뉴스)(?:/[^\s]+)?\s*", "", content)
    content = re.sub(r"[\w.+-]+@[\w.-]+", "", content)
    sentences = _split_sentences(content)
    cleaned: list[str] = []
    for sentence in sentences:
        item = " ".join(sentence.split()).strip()
        if not item or any(marker in item for marker in _ARTICLE_NOISE_MARKERS):
            continue
        item_key = re.sub(r"[^0-9a-zA-Z가-힣]", "", item).lower()
        if title_key and item_key == title_key:
            continue
        if len(title_prefix_key) >= 8 and title_prefix_key in item_key:
            continue
        cleaned.append(item)
    return " ".join(cleaned).strip() or title_text


def _beginner_topic_hint(terms: list[str]) -> str:
    hints = {
        "환율": "환율은 수출로 버는 돈과 해외에서 사오는 원재료 비용에 영향을 줄 수 있어요.",
        "원화": "원화 가치가 바뀌면 수출기업의 매출과 원재료 비용도 달라질 수 있어요.",
        "수출": "수출이 늘면 관련 기업의 매출과 이익 전망이 달라질 수 있어요.",
        "반도체": "반도체 수요와 가격은 관련 기업의 실적 기대에 영향을 줄 수 있어요.",
        "AI": "AI 관련 투자가 늘면 관련 부품과 장비를 만드는 기업의 수요가 달라질 수 있어요.",
        "금리": "금리는 기업의 이자 비용과 투자자들이 주식을 평가하는 방식에 영향을 줘요.",
        "실적": "실적은 기업이 실제로 얼마나 벌었는지 보여주는 중요한 자료예요.",
    }
    for term in terms:
        if term in hints:
            return hints[term]
    return "이런 경제 변화는 관련 기업의 매출·비용·실적 기대에 영향을 줄 수 있어요."


def _beginner_direction_hint(direction: str) -> str:
    return {
        "POSITIVE": "관련 기업에 긍정적인 신호로 해석될 수 있지만, 실제 주가가 오를지는 추가 확인이 필요해요.",
        "NEGATIVE": "관련 기업에 부담이 될 수 있지만, 실제 주가가 내릴지는 추가 확인이 필요해요.",
        "NEUTRAL": "기사 내용만으로 주가가 오를지 내릴지를 한쪽으로 단정하기는 어려워요.",
    }[direction]


def _with_particle(word: str, pair: str) -> str:
    """Use the consonant/vowel particle for a Hangul ending; neutral slash for other scripts."""
    code = ord(word[-1]) if word else 0
    if 0xAC00 <= code <= 0xD7A3:
        return word + (pair.split('/')[0] if (code - 0xAC00) % 28 else pair.split('/')[1])
    return word + '(' + pair + ')'


def _select_article_facts(title: str, content: str, limit: int) -> list[str]:
    sentences = _split_sentences(content)
    keywords = _detected_terms(title) + re.findall(r'[가-힣A-Za-z]{3,}', title)
    ranked = sorted(enumerate(sentences), key=lambda item: (
        -(3 * sum(keyword in item[1] for keyword in keywords) + bool(re.search(r'\d', item[1]))), item[0]))
    return [sentence for _, sentence in sorted(ranked[:limit])]


def _reading_summary(title: str, body: str, level: str) -> str:
    sentences = _select_article_facts(title, body, {'beginner': 2, 'normal': 3, 'analyst': 4}[level])
    if level == 'beginner':
        replacements = [('전년 동기', '지난해 같은 기간'), ('전 거래일', '직전 거래일'), ('전장 대비', '직전 거래일과 비교해'),
                        ('상승했다', '올랐어요'), ('하락했다', '내렸어요'), ('밝혔다', '밝혔어요'), ('설명했다', '설명했어요'), ('전망했다', '전망했어요'), ('증가했다', '늘었어요'), ('감소했다', '줄었어요'), ('기록했다', '기록했어요')]
        for original, plain in replacements:
            sentences = [sentence.replace(original, plain) for sentence in sentences]
    result = '\n\n'.join(sentences)
    return result if len(result) <= 600 else result[:600].rstrip() + '…'


def _mock_rewrite_news(title: str, raw_content: str) -> dict:
    cleaned = _clean_article_text(title, raw_content)
    terms = _detected_terms(f"{title} {cleaned}")
    subject = ', '.join(terms[:3]) or '기사의 핵심 지표'
    reasons = {
        'beginner': _beginner_topic_hint(terms) + ' 실제 영향은 다음 발표와 비교해 확인해요.',
        'normal': f"{subject}의 변화가 관련 매출·비용에 어떻게 연결되는지 후속 지표를 확인하세요.",
        'analyst': f"확인할 변수: {subject}. 기사 수치의 기준 시점과 전망의 가정을 비교하고, 전망이 실현되지 않을 가능성도 확인하세요."
    }
    return {
        'beginner': _reading_summary(title, cleaned, 'beginner') + '\n\n' + _beginner_topic_hint(terms),
        'normal': _reading_summary(title, cleaned, 'normal') + f"\n\n확인할 지표: {subject}. 발표된 사실과 전망을 구분하세요.",
        'analyst': _reading_summary(title, cleaned, 'analyst') + f"\n\n{_with_particle(subject, '과/와')} 연결된 수치의 비교 기준과 전망 근거를 확인하세요. 실제 가격 반응과 기사 전망은 다를 수 있습니다.",
        'importanceReason': reasons['normal'], 'importanceReasons': reasons, 'detectedTerms': terms,
    }


def _build_rewrite_prompt(title: str, raw_content: str) -> str:
    return f"""당신은 초보 투자자를 돕는 금융 뉴스 편집자입니다.
아래 뉴스를 세 가지 눈높이로 다시 작성하고, 이 뉴스가 왜 중요한지, 그리고 기사에 등장하는
핵심 금융 용어를 함께 알려주세요.
원문에 없는 숫자·기업명·원인·전망을 추가하지 말고, 불확실한 내용은 불확실하다고 표현하세요.
beginner는 쉬운 말과 짧은 문장을 우선하고, analyst도 원문 근거가 없는 투자 의견을 만들지 마세요.

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
    cleaned_content = _clean_article_text(title, raw_content)
    mock = _mock_rewrite_news(title, cleaned_content)
    if not config.USE_REAL_LLM:
        return mock

    cache_key = f"{title}::{hash(cleaned_content)}"
    cached = _rewrite_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        raw = _call_llm(_build_rewrite_prompt(title, cleaned_content), max_tokens=1500)
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


TERM_DEFINITIONS = {
    '기준금리': '중앙은행이 정하는 정책금리로 대출·예금 등 시중금리의 기준입니다.',
    '금리': '돈을 빌리거나 맡길 때 원금에 대해 적용되는 이자의 비율입니다.',
    '국채금리': '정부가 발행한 채권을 보유할 때 기대하는 수익률입니다. 채권 가격과 반대로 움직입니다.',
    '환율': '한 나라의 통화와 다른 나라 통화를 바꾸는 비율입니다.',
    '원달러': '1달러를 사기 위해 필요한 원화의 금액입니다.',
    '원달러 환율': '1달러를 사기 위해 필요한 원화의 금액입니다.',
    '원화': '대한민국에서 사용하는 통화입니다.',
    '수출': '국내에서 만든 상품이나 서비스를 해외에 판매하는 활동입니다.',
    '수입': '해외에서 만든 상품이나 서비스를 국내로 들여오는 활동입니다.',
    '반도체': '전기 흐름을 제어해 연산·기억 등의 기능을 수행하는 전자 부품의 핵심 재료입니다.',
    'HBM': '여러 메모리 칩을 쌓아 빠르게 데이터를 처리하는 고대역폭 메모리입니다.',
    'AI': '데이터를 바탕으로 인식·예측·생성 등의 작업을 수행하는 인공지능 기술입니다.',
    'PF': '사업에서 나올 미래 수익을 바탕으로 자금을 조달하는 방식입니다.',
    '프로젝트파이낸싱': '사업에서 나올 미래 수익을 바탕으로 자금을 조달하는 방식입니다.',
    'PF(프로젝트파이낸싱)': '사업에서 나올 미래 수익을 바탕으로 자금을 조달하는 방식입니다.',
    '연체율': '대출 잔액 중 약속한 기한까지 갚지 못한 대출이 차지하는 비율입니다.',
    '물가': '여러 상품과 서비스의 가격을 종합한 수준입니다.',
    '인플레이션': '물가가 지속적으로 올라 화폐의 구매력이 떨어지는 현상입니다.',
    '영업이익': '매출에서 매출원가와 판매관리비 등 본업의 비용을 뺀 이익입니다.',
    '매출': '상품이나 서비스를 판매해 얻은 금액입니다. 비용을 뺀 이익과는 다릅니다.',
    '수급': '시장에 들어오는 매수 수요와 매도 공급의 흐름입니다.',
    '변동성': '자산 가격이 얼마나 크고 빠르게 오르내리는지를 나타냅니다.',
    '밸류에이션': '기업의 현재 주가를 실적이나 자산 등 가치 기준과 비교하는 평가입니다.',
    '설비투자': '생산 능력을 유지하거나 늘리기 위해 공장·기계 등에 자금을 쓰는 활동입니다.',
    '재고 조정': '판매 상황에 맞춰 보유 재고와 생산량을 조절하는 과정입니다.',
    '공모주': '기업이 상장 등의 과정에서 일반 투자자에게 공개적으로 모집하는 주식입니다.',
    '수요예측': '기관투자자가 공모주 가격과 청약 수요를 제시하는 절차입니다.',
}


def _mock_explain_term(term: str, context: str | None) -> dict:
    definition = TERM_DEFINITIONS.get(term, '등록된 기본 설명이 없는 용어입니다.')
    result = {'definition': definition, 'contextExplanation': None, 'marketImpact': None}
    if not context:
        return result
    title, separator, body = context.partition('\n')
    cleaned = _clean_article_text(title if separator else '', body if separator else context)
    related = [sentence for sentence in _split_sentences(cleaned) if term in sentence and sentence != title]
    result['contextExplanation'] = (f"이 기사에서는 {_with_particle(term, '을/를')} 이해할 때 다음 사실을 함께 확인해요: “{related[0][:100]}” {definition}"
                                    if related else '본문에서 이 용어의 구체적인 쓰임을 확인할 수 없습니다.')
    if term in ('금리', '기준금리', '국채금리'):
        impact = '금리가 변하면 기업의 이자 비용과 채권·주식의 가치 평가 기준이 달라질 수 있어요.'
    elif term in ('환율', '원달러', '원달러 환율', '원화', '수출', '수입'):
        impact = '환율과 교역 변화는 수출 매출이나 수입 비용에 영향을 줄 수 있어요. 기업별 영향은 다릅니다.'
    elif term in ('매출', '영업이익', '설비투자', '재고 조정'):
        impact = '매출·비용·투자의 변화는 기업의 이익 전망을 바꿀 수 있어요. 실제 실적과 예상치를 비교하세요.'
    elif term in ('수급', '변동성', '밸류에이션', '공모주', '수요예측'):
        impact = '매수·매도 수요와 가치 평가가 달라지면 가격 변동 폭도 달라질 수 있어요.'
    elif term in ('물가', '인플레이션'):
        impact = '물가 변화는 소비자의 구매력과 기업 비용, 금리 정책에 영향을 줄 수 있어요.'
    elif term in ('PF', '프로젝트파이낸싱', 'PF(프로젝트파이낸싱)', '연체율'):
        impact = '사업의 상환 가능성이 낮아지면 자금 조달과 금융기관의 손실 위험에 영향을 줄 수 있어요.'
    else:
        impact = f"{term} 관련 수요와 공급의 변화가 실제 매출·비용에 연결되는지 추가 확인이 필요해요."
    result['marketImpact'] = impact + ' 기사만으로 주가 방향을 단정하지 않습니다.'
    return result


def _build_term_prompt(term: str, context: str | None) -> str:
    context_block = context if context else "(제공된 기사 맥락 없음)"
    return f"""당신은 초보 투자자에게 금융 용어를 쉽게 설명하는 도우미입니다.
아래 용어를 '정의 / 이 뉴스에서의 의미 / 시장 영향' 3단 구조로 설명하세요.
기사 맥락이 없으면 contextExplanation과 marketImpact는 null로 응답하세요.
contextExplanation은 반드시 아래 기사에 실제로 포함된 문장이나 사실에 근거하세요.
기사에 없는 기업·수치·인과관계를 추가하지 말고, 시장 영향은 가능성으로만 표현하세요.

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
isAligned는 반드시 사용자 예측과 실제 결과의 방향이 같은지 비교한 값이어야 합니다.
수익을 보장하거나 사용자를 과도하게 칭찬하지 말고, 제공된 뉴스 요약에서 확인되지 않는 원인은 가능성으로 표현하세요.

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
            # Alignment is deterministic business logic, not a model opinion.
            "isAligned": mock["isAligned"],
            "feedbackText": data.get("feedbackText", mock["feedbackText"]),
            "reasons": data.get("reasons", mock["reasons"]),
        }
    except Exception as exc:
        logger.warning("피드백 생성 LLM 호출 실패, 목업 응답으로 대체합니다: %s", exc)
        return mock
