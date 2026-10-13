"""Dry-run by default. No scheduler or request path invokes this script."""
import argparse
import json
from app.services.ml_sentiment import predict_sentiment
from scripts.news_batch import cleaned_input, database


def changes(rows, predictor=predict_sentiment):
    result = []
    for row in rows:
        _, lead = cleaned_input(row["title"], row.get("raw_content"))
        score = predictor(row["title"], lead)
        confidence = float(score["confidence"])
        label = score["label"] if confidence >= 0.6 else "NEUTRAL"
        if label not in {"POSITIVE", "NEGATIVE", "NEUTRAL"} or not 0 <= confidence <= 1:
            raise ValueError("Invalid sentiment score")
        if row.get("sentiment_hint") != label or row.get("sentiment_confidence") != confidence:
            result.append({"id": row["id"], "label": label, "confidence": confidence,
                           "previous_label": row.get("sentiment_hint"), "previous_confidence": row.get("sentiment_confidence")})
    return result


def apply_changes(connection, plan):
    updated = 0
    for row in plan:
        updated += connection.execute("""
            UPDATE news SET sentiment_hint=%s,sentiment_confidence=%s WHERE id=%s
              AND sentiment_hint IS NOT DISTINCT FROM %s AND sentiment_confidence IS NOT DISTINCT FROM %s
            """, (row["label"],row["confidence"],row["id"],row["previous_label"],row["previous_confidence"])).rowcount
    return updated


def main():
    parser = argparse.ArgumentParser(description="Score news locally; prints change count before optional writes")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100000: parser.error("limit must be 1..100000")
    with database() as db:
        rows = db.execute("SELECT id,title,raw_content,sentiment_hint,sentiment_confidence FROM news ORDER BY id LIMIT %s", (args.limit,)).fetchall()
    plan = changes(rows)
    print(json.dumps({"scanned":len(rows),"would_change":len(plan),"apply":args.apply}), flush=True)
    if args.apply:
        with database(readonly=False) as db:
            updated = apply_changes(db,plan)
        print(json.dumps({"updated":updated,"skipped_concurrent_changes":len(plan)-updated}))


if __name__ == "__main__":
    try: main()
    except Exception:
        raise SystemExit("Sentiment batch failed; check optional dependencies, model, and DB schema") from None
