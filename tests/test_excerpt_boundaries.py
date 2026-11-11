from app.services import llm_client as llm

def test_sentence_clipping_keeps_whole_words():
    assert llm._clip_reading_text('첫 문장이다. ' + '정확한단어 ' * 100, 35) == '첫 문장이다.'
    clipped = llm._clip_reading_text('매출은 ' + '아주긴단어 ' * 100, 35)
    assert len(clipped) <= 35
    assert clipped.rstrip('…').endswith('아주긴단어')

def test_recorded_fall_is_not_relabelled_as_prospective_risk():
    text = llm._reading_summary('기업 영업이익 발표', '기업 영업이익이 20% 하락했다. 매출은 100억원으로 집계됐다.', 'analyst')
    risk = text.split('리스크·확인할 점\n')[1]
    assert '20% 하락했다.' not in risk
    assert '확인' in risk

def test_past_reported_speech_and_numbers_survive_clipping():
    text = llm.rewrite_news('매출 발표', '관계자는 매출이 1,000억원으로 늘었다고 말했다.', allow_llm=False)['beginner']
    assert '1,000억원' in text and '늘었다고 말했어요.' in text
