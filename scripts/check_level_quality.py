"""Heuristic (rule-based) quality check for the beginner/normal/analyst rewrite levels.

No LLM call involved here (free, deterministic) — this only measures whether
the 3 levels are actually differentiated in a readability sense: shorter
sentences and fewer finance jargon words for "beginner" than "analyst".

The original length/jargon formula and beginner <= normal <= analyst condition
apply to the reading body. Section labels, verified glossary notes and explicit
absence notices are reported separately, rather than counted as article prose.
Missing source evidence, unsupported numbers and empty bodies also fail.

This is a text-statistics proxy for readability, not a judgment of factual
accuracy or writing quality — it can't tell you whether a summary correctly
reflects the source article. Treat it as a smoke test for "did the level
differentiation regress", not a full quality score.

Usage (existing API text-statistics mode remains available; saved --input mode is offline):
    python3 -m scripts.check_level_quality --input artifacts/rewrite-quality.jsonl
    python3 scripts/check_level_quality.py
    python3 scripts/check_level_quality.py --title "..." --body "..."
    python3 scripts/check_level_quality.py --base-url http://localhost:8001
"""

from __future__ import annotations

import argparse
import json
import html
from pathlib import Path
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
    payload = json.dumps({"title": title, "body": body, "level": level, "allow_llm": False}).encode("utf-8")
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


def reading_body(text: str) -> str:
    """Compare article prose in the same format; never remove unknown claims."""
    from app.services.llm_client import TERM_DEFINITIONS
    display_only = {'근거', '수치·비교 기준', '리스크·확인할 점', '추가 비교 수치 없음',
                    '기사에 별도로 언급된 위험 요인은 없습니다.', '추가 확인이 필요합니다.',
                    '기사에 별도로 언급된 위험 요인은 없습니다. 추가 확인이 필요합니다.'}
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line in display_only:
            continue
        glossary = re.fullmatch(r'([^()]+)\(([^()]+)\)[을를] 함께 살펴봐요\.', line)
        if glossary and glossary[1] in TERM_DEFINITIONS:
            definition = re.sub(r'(?:입니다|이에요|예요)[.!?。]*$', '', TERM_DEFINITIONS[glossary[1]]).rstrip('.!?。 ')
            if glossary[2] == definition:
                continue
        lines.append(re.sub(r'\[(?:사실|분석|전망)\]\s*', '', line))
    return ' '.join(' '.join(lines).split())


def assess(results: dict[str, str], source: str) -> dict:
    from app.services.llm_client import _numbers_in_source
    bodies = {level: reading_body(results[level]) for level in LEVELS}
    stats = {level: analyze(bodies[level]) for level in LEVELS}
    issues = []
    for level in LEVELS:
        if not bodies[level]:
            issues.append(f'{level}: 발췌 본문 없음')
        if not _numbers_in_source(bodies[level], source):
            issues.append(f'{level}: 원문에 없는 수치')
    scores = [stats[level]['difficulty_score'] for level in LEVELS]
    if not scores[0] <= scores[1] <= scores[2]:
        issues.append('난이도 순서가 기대와 다름')
    # Do not excuse omitted normal-level evidence when it fits the same 600-char contract.
    overhead = len(results['analyst']) - len(bodies['analyst'])
    if len(bodies['normal']) + overhead <= 600:
        source = ' '.join(source.split())
        for sentence in split_sentences(bodies['normal']):
            if sentence in source and sentence not in bodies['analyst']:
                issues.append('analyst: 일반 수준의 원문 근거 누락: ' + sentence)
    return {'stats': stats, 'rawStats': {level: analyze(results[level]) for level in LEVELS},
            'issues': issues, 'passed': not issues}


def cell(value):
    return html.escape(str(value)).replace('|','&#124;').replace('\n','<br>')


def report(rows):
    from app.services.llm_client import _clean_article_text, _mock_rewrite_news
    lines=['# 수준별 리라이팅 비교','', '제공된 저장 결과만 비교하며 모델을 호출하지 않습니다.', '', '| 원문 | 발췌 | 로컬 LLM |','|---|---|---|']
    for row in rows[:10]:
        title=row['title'];body=row.get('body',row.get('raw_content',''))
        excerpt=_mock_rewrite_news(title,_clean_article_text(title,body))
        excerpts='\n\n'.join(label+'\n'+excerpt[level] for level,label in [('beginner','초보자'),('normal','일반'),('analyst','분석')])
        generated='\n\n'.join(label+'\n'+row.get(level,'결과 없음') for level,label in [('beginner','초보자'),('normal','일반'),('analyst','분석')]) if row.get('mode')=='REWRITTEN' else 'EXCERPT: 저장된 LLM 리라이팅 없음'
        lines.append('| '+cell(title+'\n'+body)+' | '+cell(excerpts)+' | '+cell(generated)+' |')
    return '\n'.join(lines)+'\n'



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Saved batch JSONL; this mode never calls the API or a model")
    parser.add_argument("--output", default="artifacts/level-quality.md")
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--body", default=DEFAULT_BODY)
    parser.add_argument("--base-url", default="http://localhost:8001")
    args = parser.parse_args()
    if args.input:
        rows=[json.loads(line) for line in Path(args.input).read_text().splitlines() if line.strip()]
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(report(rows),encoding='utf-8')
        print(f'Compared {min(10,len(rows))} saved articles; no model calls')
        return

    summaries = {}
    for level in LEVELS:
        summaries[level] = fetch_rewrite(args.base_url, args.title, args.body, level)
    assessment = assess(summaries, args.body)
    results = assessment['stats']

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
    ordered_correctly = assessment['passed']
    print(
        "판정: "
        + ("PASS — beginner ≤ normal ≤ analyst 순서로 난이도가 올라감" if ordered_correctly
           else "FAIL — " + '; '.join(assessment['issues']))
    )
    print('표시 문구 포함 참고 점수:', ', '.join(f"{level}={assessment['rawStats'][level]['difficulty_score']}" for level in LEVELS))
    print(
        "\n※ 본문 통계에서 섹션 제목·검증된 용어 풀이·부재 안내를 분리했습니다. "
        "문장 길이·전문용어 개수는 규칙 기반 대용 지표이며, "
        "'내용이 원문과 맞는지'는 못 잽니다 — 레벨 구분이 문자 그대로 작동하는지 보는 스모크 테스트입니다."
    )
    if not assessment['passed']:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
