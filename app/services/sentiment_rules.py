"""Shared, versioned lexical hints; model inference remains separate."""
import json
import re
from pathlib import Path

RULES = json.loads((Path(__file__).parent / 'rules/sentiment-rules.json').read_text())
COMPOUNDS = [(re.compile(row['pattern']), row['label']) for row in RULES['compounds']]


def topic_label(text: str) -> str | None:
    rises = any(word in text for word in RULES['rateRises'])
    falls = any(word in text for word in RULES['rateFalls'])
    if rises != falls:
        return 'NEGATIVE' if rises else 'POSITIVE'
    if '환율' in text and not any(word in text for word in ('수출', '수입')):
        return 'NEUTRAL'
    return None


def rule_label(text: str) -> str:
    topic = topic_label(text)
    if topic is not None:
        return topic
    positive = negative = False
    for pattern, label in COMPOUNDS:
        if pattern.search(text):
            positive |= label == 'POSITIVE'
            negative |= label == 'NEGATIVE'
            text = pattern.sub(' ', text)
    positive |= any(word in text for word in RULES['positive'])
    negative |= any(word in text for word in RULES['negative'])
    return 'NEUTRAL' if positive == negative else 'POSITIVE' if positive else 'NEGATIVE'
