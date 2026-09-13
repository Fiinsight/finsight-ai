"""Heuristic (rule-based) quality check for the beginner/normal/analyst rewrite levels.

No LLM call involved here (free, deterministic) — this only measures whether
the 3 levels are actually differentiated in a readability sense: shorter
sentences and fewer finance jargon words for "beginner" than "analyst".

This is a text-statistics proxy for readability, not a judgment of factual
accuracy or writing quality — it can't tell you whether a summary correctly
reflects the source article. Treat it as a smoke test for "did the level
differentiation regress", not a full quality score.

Usage:
    python3 scripts/check_level_quality.py
    python3 scripts/check_level_quality.py --title "..." --body "..."
    python3 scripts/check_level_quality.py --base-url http://localhost:8001
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request

DEFAULT_TITLE = "반도체 수출 회복세, 대형주 실적 기대감 확대"
DEFAULT_BODY = (
    "산업통상자원부가 발표한 이달 수출 잠정치에 따르면 반도체 수출액이 전년 동월 대비 "
    "두 자릿수 증가율을 기록했다. HBM 수요 확대와 서버용 메모리 가격 상승이 실적 개선을 "
    "이끌었다는 분석이다. 증권가에서는 삼성전자와 SK하이닉스의 4분기 영업이익 전망치를 "
    "잇달아 상향 조정하고 있다."
)

# Common Korean finance/investing jargon — a beginner-level summary should
# lean on these far less than an analyst-level one.
JARGON_TERMS = [
    "실적", "영업이익", "밸류에이션", "할인율", "리레이팅", "선반영", "캐리트레이드",
    "환헤지", "코스피", "코스닥", "금통위", "기준금리", "환율", "수급",
    "변동성", "전망치", "공시", "매출", "PBR", "PER", "컨센서스", "듀레이션",
]

LEVELS = ["beginner", "normal", "analyst"]


def fetch_rewrite(base_url: str, title: str, body: str, level: str) -> str:
    payload = json.dumps({"title": title, "body": body, "level": level}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/ai/news/rewrite",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["summary"]


def split_sentences(text: str) -> list[str]:
    # Korean sentences here reliably end in "다.", "요.", "!", "?" — good enough
    # for this heuristic without pulling in a real NLP sentence splitter.
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def count_jargon(text: str) -> int:
    return sum(text.count(term) for term in JARGON_TERMS)


def analyze(text: str) -> dict:
    sentences = split_sentences(text)
    char_count = len(text)
    avg_sentence_len = char_count / len(sentences) if sentences else 0.0
    jargon_count = count_jargon(text)
    # Illustrative composite score, not a validated metric: longer average
    # sentences and more jargon both push "difficulty" up.
    difficulty_score = round(avg_sentence_len * 0.5 + jargon_count * 3, 1)
    return {
        "char_count": char_count,
        "sentence_count": len(sentences),
        "avg_sentence_len": round(avg_sentence_len, 1),
        "jargon_count": jargon_count,
        "difficulty_score": difficulty_score,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--body", default=DEFAULT_BODY)
    parser.add_argument("--base-url", default="http://localhost:8001")
    args = parser.parse_args()

    results = {}
    for level in LEVELS:
        summary = fetch_rewrite(args.base_url, args.title, args.body, level)
        results[level] = {"summary": summary, **analyze(summary)}

    print(f"기사: {args.title}\n")
    header = f"{'레벨':<10}{'글자수':>8}{'문장수':>8}{'평균문장길이':>14}{'전문용어':>10}{'난이도점수':>10}"
    print(header)
    print("-" * len(header))
    for level in LEVELS:
        r = results[level]
        print(
            f"{level:<10}{r['char_count']:>8}{r['sentence_count']:>8}"
            f"{r['avg_sentence_len']:>14}{r['jargon_count']:>10}{r['difficulty_score']:>10}"
        )

    print()
    beginner_score = results["beginner"]["difficulty_score"]
    normal_score = results["normal"]["difficulty_score"]
    analyst_score = results["analyst"]["difficulty_score"]

    ordered_correctly = beginner_score <= normal_score <= analyst_score
    print(
        "판정: "
        + ("PASS — beginner ≤ normal ≤ analyst 순서로 난이도가 올라감" if ordered_correctly
           else "FAIL — 난이도 순서가 기대와 다름 (beginner가 더 어렵거나 순서가 뒤집힘)")
    )
    print(
        "\n※ 참고: 이건 문장 길이·전문용어 개수만 보는 규칙 기반 지표라, "
        "'내용이 원문과 맞는지'는 못 잽니다 — 레벨 구분이 문자 그대로 작동하는지 보는 스모크 테스트입니다."
    )


if __name__ == "__main__":
    main()
