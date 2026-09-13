"""Run the 10-article mini quality eval against a live finsight-ai server.

Calls /ai/news/rewrite (x3 levels), /ai/terms/explain, and /ai/feedback/judgement
(x6 UP/NEUTRAL/DOWN combinations) for each article in mini_eval_articles.json,
and dumps everything to mini_eval_results.json for manual/LLM-judge scoring.

This is a preliminary, small-N (N=10) check — not a substitute for the full
golden-set eval, just enough to get real numbers instead of no numbers.

Usage:
    python3 scripts/mini_eval_run.py --base-url http://localhost:8001
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

LEVELS = ["beginner", "normal", "analyst"]
CHOICES = ["UP", "NEUTRAL", "DOWN"]


def post(base_url: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def split_sentences(text: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]


JARGON_TERMS = [
    "실적", "영업이익", "밸류에이션", "할인율", "리레이팅", "선반영", "캐리트레이드",
    "환헤지", "코스피", "코스닥", "금통위", "기준금리", "환율", "수급",
    "변동성", "전망치", "공시", "매출", "PBR", "PER", "컨센서스", "듀레이션",
]


def readability_stats(text: str) -> dict:
    sentences = split_sentences(text)
    char_count = len(text)
    avg_len = char_count / len(sentences) if sentences else 0.0
    jargon = sum(text.count(t) for t in JARGON_TERMS)
    return {
        "char_count": char_count,
        "sentence_count": len(sentences),
        "avg_sentence_len": round(avg_len, 1),
        "jargon_count": jargon,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    args = parser.parse_args()

    scripts_dir = Path(__file__).parent
    articles = json.loads((scripts_dir / "mini_eval_articles.json").read_text(encoding="utf-8"))

    results = []
    for art in articles:
        print(f"[{art['id']}/10] {art['title'][:30]}...")
        entry = {"id": art["id"], "topic": art["topic"], "title": art["title"], "body": art["body"]}

        # 1) rewrite at 3 levels
        rewrites = {}
        for level in LEVELS:
            resp = post(args.base_url, "/ai/news/rewrite", {
                "title": art["title"], "body": art["body"], "level": level,
            })
            rewrites[level] = {
                "summary": resp["summary"],
                "importance_reason": resp["importance_reason"],
                "detected_terms": resp["detected_terms"],
                **readability_stats(resp["summary"]),
            }
        entry["rewrites"] = rewrites

        # 2) term explanation, grounded in this article's body
        term_resp = post(args.base_url, "/ai/terms/explain", {
            "term": art["term"], "article_context": art["body"],
        })
        entry["term_explain"] = {"term": art["term"], **term_resp}

        # 3) feedback consistency: does isAligned match user_choice vs market_result?
        fb_resp = post(args.base_url, "/ai/feedback/judgement", {
            "news_id": art["id"],
            "user_choice": art["user_choice"],
            "user_reason": art["title"],
            "market_result": art["market_result"],
        })
        expected_aligned = art["user_choice"] == art["market_result"]
        entry["feedback"] = {
            "user_choice": art["user_choice"],
            "market_result": art["market_result"],
            "expected_aligned": expected_aligned,
            **fb_resp,
        }

        results.append(entry)

    out_path = scripts_dir / "mini_eval_results.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(results)} article results to {out_path}")


if __name__ == "__main__":
    main()
