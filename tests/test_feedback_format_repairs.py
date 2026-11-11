import copy
import pytest
from test_feedback_delivery import candidate, deliver, REASON

@pytest.mark.parametrize('variant', range(20))
def test_twenty_equivalent_format_variants_keep_factual_checks(monkeypatch, variant):
    value=copy.deepcopy(candidate())
    for item in value['reasons']: item['title']=' ' * variant + item['title'] + ' ' * (20-variant)
    if variant % 4 == 0:
        for item in value['reasons']: item['title']='  '+item['title']+' : '
    elif variant % 4 == 1:
        value['reasons'][1]['detail']=value['reasons'][1]['detail'].replace(f'남긴 근거: “{REASON}”.',f'남긴 근거: "{REASON}".')
    elif variant % 4 == 2:
        for item in value['reasons']: item['detail']=item['detail'].replace('-2.30%', '-2.3%')
    else:
        for item in value['reasons']: item['title']='['+item['title']+']'
    assert deliver(monkeypatch,value)['mode']=='LLM'

@pytest.mark.parametrize('change', ['wrong_verdict','invented_number','changed_reason','advice'])
def test_bad_facts_still_never_pass(monkeypatch,change):
    value=copy.deepcopy(candidate())
    if change=='wrong_verdict': value['verdict']='CORRECT'
    if change=='invented_number': value['reasons'][0]['detail']+='매출은 999억원이에요.'
    if change=='changed_reason': value['reasons'][1]['detail']=value['reasons'][1]['detail'].replace(REASON,'조작된 근거')
    if change=='advice': value['nextTip']='매수하세요.'
    assert deliver(monkeypatch,value)['mode']=='RULE'
