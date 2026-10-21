"""All provider traffic and ledgers in this module are local mocks/temporary files."""
import copy
import json
import logging
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from app import config
from app.services import llm_client as f

LEAD = '기업 매출이 전년보다 증가했다.'
REASON = '매출 증가로 이익 개선을 기대해요.'
CONTEXT = dict(news_title='분기 실적', user_reason=REASON, related_symbol='005930',
               related_symbol_name='삼성전자', comparison_date='2026-10-13')


def candidate(choice='UP', direction='DOWN', percent=-2.3, **updates):
    return f._mock_generate_feedback(LEAD,choice,direction,percent,**{**CONTEXT,**updates})


def deliver(monkeypatch, value, choice='UP', direction='DOWN', percent=-2.3, **updates):
    monkeypatch.setattr(config,'USE_REAL_LLM',True)
    with patch.object(f,'_call_llm',return_value=json.dumps(value,ensure_ascii=False)) as paid:
        result=f.generate_feedback(LEAD,choice,direction,percent,**{**CONTEXT,**updates})
    paid.assert_called_once()
    return result


def test_prompt_contains_only_decision_facts_instead_of_a_rule_answer():
    facts=f._feedback_prompt_facts(LEAD,'UP','DOWN',-2.3,**CONTEXT)
    prompt=f._build_feedback_prompt(LEAD,'UP','DOWN',-2.3,**CONTEXT)
    fallback=candidate()
    assert not {'headline','summary','reasons','feedbackText','nextTip'}.intersection(facts)
    assert fallback['reasons'][0]['detail'] not in prompt
    assert fallback['reasons'][1]['detail'] not in prompt
    assert '1%p' not in json.dumps(facts,ensure_ascii=False)
    assert facts['article_lead']==LEAD and facts['article_signal']=='호재'
    assert facts['result_sentence']==fallback['summary'].split('. ',1)[0]+'.'
    assert facts['market_sentence']==fallback['reasons'][2]['detail']
    assert facts['reason_check']==dict(has_fact=True,has_link=True,contradicts=False,substantial=True,strong=True)
    for instruction in ['누가 무엇을','일반론','사실 → 영향 경로 → 방향','라벨','자연스러운 문장','2번 reason([1])']:
        assert instruction in prompt


@pytest.mark.parametrize('symbol,percent,index,relation,expected', [
    ('005930',-4.39,-.27,'INDIVIDUAL','기사에 없는 다른 개별 소식'),
    ('005930',-.7,-.27,'MARKET','기사 밖 시장 흐름·수급'),
    ('005930',-4.39,None,'NO_INDEX','기사 밖 시장 흐름·수급'),
    ('KOSPI',-4.39,None,'INDEX','기사 밖 시장 흐름·수급'),
])
def test_no_signal_candidate_is_consistent_with_market_relation(symbol,percent,index,relation,expected):
    facts=f._feedback_prompt_facts('지원 정책의 운영 일정이 공지됐다.','UP','DOWN',percent,
                                   news_title='지원 정책 일정',related_symbol=symbol,index_name='코스피' if index is not None else None,index_change_percent=index)
    assert facts['article_signal']=='없음'
    assert facts['market_relation']==relation
    assert facts['miss_cause']['code']=='NO_SIGNAL'
    assert expected in facts['miss_cause']['candidate']
    if relation=='INDIVIDUAL': assert '시장 흐름' not in facts['miss_cause']['candidate']


@pytest.mark.parametrize('quote', ['“원문 문장. 다음 문장.”','"원문 문장. 다음 문장."'])
def test_sentence_repair_never_splits_a_quoted_period(quote):
    source=f'기사에서는 {quote}라고 전했어요. 이익 경로를 살펴봐요.'
    assert f._feedback_sentences(source)==[f'기사에서는 {quote}라고 전했어요.','이익 경로를 살펴봐요.']
    placeholder='__FEEDBACK_QUOTE_0__'
    assert placeholder in f._feedback_sentences(placeholder+' '+source)[0]


def test_missing_article_quote_is_added_without_copying_rule_explanation(monkeypatch):
    value=candidate()
    value['reasons'][0]['detail']='기업 매출 증가는 제품 수요와 매출 기대를 연결해볼 근거예요. 다만 이 뉴스만으로 가격 움직임을 단정할 수는 없어요.'
    original=copy.deepcopy(value)
    result=deliver(monkeypatch,value)
    assert result['mode']=='LLM'
    assert result['reasons'][0]['detail'].startswith(f'기사에서는 “{LEAD}”라고 전했어요.')
    assert '제품 수요와 매출 기대' in result['reasons'][0]['detail']
    assert value==original


def test_article_quote_is_not_added_when_it_would_exceed_four_sentences(monkeypatch,caplog):
    value=candidate()
    value['reasons'][0]['detail']='기업 매출을 살펴봐요. 제품 수요를 봐요. 비용도 봐요. 가격은 다른 요인도 반영해요.'
    with caplog.at_level(logging.WARNING): result=deliver(monkeypatch,value)
    assert result['mode']=='RULE' and 'reason=missing_quote' in caplog.text


def test_repeated_explanation_is_removed_from_article_not_from_source_quote(monkeypatch):
    value=candidate()
    last=f._feedback_sentences(value['reasons'][0]['detail'])[-1]
    value['reasons'][1]['detail']+=' '+last
    result=deliver(monkeypatch,value)
    assert result['mode']=='LLM'
    assert last not in result['reasons'][0]['detail'] and last in result['reasons'][1]['detail']
    assert f'“{LEAD}”' in result['reasons'][0]['detail']
    assert f._feedback_sentence_count(result['reasons'][0]['detail'])==2


def test_repeat_cannot_be_removed_if_article_would_have_only_one_sentence(monkeypatch,caplog):
    value=candidate()
    last=f._feedback_sentences(value['reasons'][0]['detail'])[-1]
    value['reasons'][0]['detail']=f'기사에서는 “{LEAD}”라고 전했어요. '+last
    value['reasons'][1]['detail']+=' '+last
    with caplog.at_level(logging.WARNING): result=deliver(monkeypatch,value)
    assert result['mode']=='RULE' and 'reason=repeated_explanation' in caplog.text


@pytest.mark.parametrize('choice,direction,percent,body', [
    ('UP','NEUTRAL',-.27,f'남긴 근거: “{REASON}”. 기사에서 확인한 매출과 이익 경로를 다시 살펴봐요.'),
    ('NEUTRAL','DOWN',-1.5,f'남긴 근거: “{REASON}”.'),
])
def test_missing_neutral_guidance_is_repaired_only_within_three_sentences(monkeypatch,choice,direction,percent,body):
    value=candidate(choice,direction,percent)
    value['reasons'][1]['detail']=body
    result=deliver(monkeypatch,value,choice,direction,percent)
    assert result['mode']=='LLM' and '±0.5%' in result['reasons'][1]['detail']
    assert f'{percent:+.2f}%' in result['reasons'][1]['detail']
    assert f._feedback_sentence_count(result['reasons'][1]['detail'])==3


def test_neutral_repair_refuses_to_overflow_and_never_fills_in_a_missing_user_quote(monkeypatch,caplog):
    value=candidate('NEUTRAL','DOWN',-1.5)
    value['reasons'][1]['detail']=f'남긴 근거: “{REASON}”. 선택한 범위를 다시 확인해보세요.'
    with caplog.at_level(logging.WARNING): result=deliver(monkeypatch,value,'NEUTRAL','DOWN',-1.5)
    assert result['mode']=='RULE' and 'reason=missing_neutral_band' in caplog.text
    caplog.clear()
    value=candidate();value['reasons'][1]['detail']='기사 사실을 확인해보세요.'
    with caplog.at_level(logging.WARNING): result=deliver(monkeypatch,value)
    assert result['mode']=='RULE' and 'reason=missing_quote' in caplog.text


def test_repair_does_not_mask_too_many_sentences_or_invented_numbers(monkeypatch,caplog):
    value=candidate();value['reasons'][0]['detail']+=' 사실을 확인해요. 시점을 확인해요.'
    original=copy.deepcopy(value)
    assert f._repair_feedback_reasons(value,lead=LEAD,neutral_guidance='')==original
    with caplog.at_level(logging.WARNING): result=deliver(monkeypatch,value)
    assert result['mode']=='RULE' and 'reason=sentence_count' in caplog.text
    caplog.clear();value=candidate();value['summary']+=' 매출이 999% 늘었어요.'
    with caplog.at_level(logging.WARNING): result=deliver(monkeypatch,value)
    assert result['mode']=='RULE' and 'reason=number_not_in_source' in caplog.text
    assert REASON not in caplog.text
    assert all(record.levelno>=logging.WARNING for record in caplog.records if 'feedback_fallback' in record.message)


@pytest.mark.parametrize('reason,expected', [(REASON,'근거는 기사 사실과 가격 경로를 이었지만 다음 거래일에는 시장이 이 소식을 크게 반영하지 않았어요.'),('상승할 것 같아요','다음엔 기사에서 본 사실과')])
def test_neutral_result_keeps_reason_assessment(reason,expected):
    value=candidate('UP','NEUTRAL',-.27,user_reason=reason)
    assert expected in value['reasons'][1]['detail']
    assert '±0.5%' in value['reasons'][1]['detail']
    assert f._feedback_sentence_count(value['reasons'][1]['detail'])==3


def test_conftest_isolates_feedback_switch_and_ledger(tmp_path):
    assert not config.FEEDBACK_WITH_LLM
    assert config.FEEDBACK_LEDGER_PATH==str(tmp_path/'feedback.db')


def test_cache_includes_prompt_version_and_kst_day_without_extra_calls(monkeypatch):
    monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',True);monkeypatch.setattr(config,'MAX_DAILY_FEEDBACK_CALLS',50)
    value=candidate();tomorrow=datetime(2026,10,15,tzinfo=ZoneInfo('Asia/Seoul'))
    with patch.object(f,'_call_gemini',return_value=json.dumps(value,ensure_ascii=False)) as paid, patch.object(f,'_reserve_process_llm_call'), patch('app.services.rewrite_budget.status',return_value={'rewriteStoppedToday':False}), patch.object(f.time,'sleep'), patch.object(f,'datetime') as clock:
        clock.now.return_value=datetime(2026,10,14,tzinfo=ZoneInfo('Asia/Seoul'))
        first=f.generate_feedback(LEAD,'UP','DOWN',-2.3,**CONTEXT)
        assert f.generate_feedback(LEAD,'UP','DOWN',-2.3,**CONTEXT)==first
        assert first['mode']=='LLM';assert paid.call_count==1
        monkeypatch.setattr(f,'FEEDBACK_PROMPT_VERSION',f.FEEDBACK_PROMPT_VERSION+'-new')
        assert f.generate_feedback(LEAD,'UP','DOWN',-2.3,**CONTEXT)['mode']=='LLM';assert paid.call_count==2
        clock.now.return_value=tomorrow
        assert f.generate_feedback(LEAD,'UP','DOWN',-2.3,**CONTEXT)['mode']=='LLM';assert paid.call_count==3


def test_rejected_response_stays_rule_for_that_day_and_can_retry_the_next_day(monkeypatch):
    monkeypatch.setattr(config,'FEEDBACK_WITH_LLM',True);monkeypatch.setattr(config,'MAX_DAILY_FEEDBACK_CALLS',50)
    bad=candidate();bad['verdict']='CORRECT'
    with patch.object(f,'_call_gemini',side_effect=[json.dumps(bad,ensure_ascii=False),json.dumps(candidate(),ensure_ascii=False)]) as paid, patch.object(f,'_reserve_process_llm_call'), patch('app.services.rewrite_budget.status',return_value={'rewriteStoppedToday':False}), patch.object(f.time,'sleep'), patch.object(f,'datetime') as clock:
        clock.now.return_value=datetime(2026,10,14,tzinfo=ZoneInfo('Asia/Seoul'))
        first=f.generate_feedback(LEAD,'UP','DOWN',-2.3,**CONTEXT)
        assert first['mode']=='RULE' and f.generate_feedback(LEAD,'UP','DOWN',-2.3,**CONTEXT)==first
        assert paid.call_count==1
        clock.now.return_value=datetime(2026,10,15,tzinfo=ZoneInfo('Asia/Seoul'))
        assert f.generate_feedback(LEAD,'UP','DOWN',-2.3,**CONTEXT)['mode']=='LLM' and paid.call_count==2
