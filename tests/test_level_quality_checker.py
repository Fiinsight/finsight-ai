import io
import json
import sys

import pytest

from app.services import llm_client as llm
from scripts import check_level_quality as quality


def results():
    return llm.rewrite_news(quality.DEFAULT_TITLE, quality.DEFAULT_BODY, allow_llm=False)


def test_original_broken_analyst_is_rejected_for_lost_evidence():
    value = results()
    first, _, forecast = llm._split_sentences(quality.DEFAULT_BODY)
    value['analyst'] = f'근거\n{first}\n\n수치·비교 기준\n{forecast}\n\n리스크·확인할 점\n기사에 별도로 언급된 위험 요인은 없습니다. 추가 확인이 필요합니다.'
    assessment = quality.assess(value, quality.DEFAULT_BODY)
    assert not assessment['passed']
    assert any('근거 누락' in issue and 'HBM' in issue for issue in assessment['issues'])


def test_only_exact_presentation_metadata_is_removed():
    body = 'HBM 수요가 증가했다.'
    note = 'HBM(여러 메모리 칩을 쌓아 빠르게 데이터를 처리하는 고대역폭 메모리)을 함께 살펴봐요.'
    assert quality.reading_body('[사실] ' + body + '\n\n' + note) == body
    assert quality.reading_body('근거\n' + body + '\n\n리스크·확인할 점\n규제 위험이 언급됐다.') == body + ' 규제 위험이 언급됐다.'
    assert '999억원' in quality.reading_body('HBM(매출이 999억원)을 함께 살펴봐요.')


@pytest.mark.parametrize('text', ['', '근거\n\n추가 비교 수치 없음\n기사에 별도로 언급된 위험 요인은 없습니다.'])
def test_empty_bodies_cannot_pass_on_zero_scores(text):
    value = {level: text for level in quality.LEVELS}
    assessment = quality.assess(value, quality.DEFAULT_BODY)
    assert not assessment['passed']
    assert any('본문 없음' in issue for issue in assessment['issues'])


def test_reversed_difficulty_and_invented_numbers_still_fail():
    value = results()
    value['beginner'] = ('영업이익 전망치 컨센서스 변동성 ' * 12) + '999억원이다.'
    assessment = quality.assess(value, quality.DEFAULT_BODY)
    assert not assessment['passed']
    assert any('난이도 순서' in issue for issue in assessment['issues'])
    assert any('원문에 없는 수치' in issue for issue in assessment['issues'])


def test_fetch_explicitly_disables_generation(monkeypatch):
    def fake_urlopen(request, timeout):
        assert json.loads(request.data)['allow_llm'] is False
        return io.BytesIO(json.dumps({'summary': '수출이 늘었다.'}).encode())
    monkeypatch.setattr(quality.urllib.request, 'urlopen', fake_urlopen)
    assert quality.fetch_rewrite('http://fixture.test', '수출', '수출이 늘었다.', 'normal') == '수출이 늘었다.'


def test_failed_cli_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['check_level_quality'])
    monkeypatch.setattr(quality, 'fetch_rewrite', lambda *args: '')
    with pytest.raises(SystemExit, match='1'):
        quality.main()
    assert 'FAIL' in capsys.readouterr().out


def test_fixed_cli_passes_and_still_reports_the_old_raw_scores(monkeypatch, capsys):
    value = results()
    monkeypatch.setattr(sys, 'argv', ['check_level_quality'])
    monkeypatch.setattr(quality, 'fetch_rewrite', lambda base, title, body, level: value[level])
    quality.main()
    output = capsys.readouterr().out
    assert 'PASS' in output and '표시 문구 포함 참고 점수' in output
