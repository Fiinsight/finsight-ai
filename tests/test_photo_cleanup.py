import pytest
from app.services.llm_client import _clean_article_text, _strip_photo_noise
from app.routers.chart import event_lead


@pytest.mark.parametrize('notice', ['사진은 기사와 관련 없음.', '사진은 기사 내용과 무관합니다.', '이미지는 기사와 관련 없습니다.', '자료사진', '일러스트=자료', '그래픽=자료'])
def test_photo_notices_are_removed_and_article_is_preserved(notice):
    source = notice + '\n\n사진=챗GPT 생성 이미지 인공지능(AI) 열풍으로 메모리 반도체 가격이 치솟으면서 부담이 커지고 있다.'
    assert _clean_article_text('반도체 가격', source).startswith('인공지능(AI) 열풍으로 메모리 반도체 가격이 치솟으면서')


def test_photo_credits_preserve_following_body_and_unrelated_text():
    assert _strip_photo_noise('사진=게티이미지뱅크 코스피는 3% 하락했다.') == '코스피는 3% 하락했다.'
    assert _strip_photo_noise('사진=한국거래소 제공 코스피는 3% 하락했다.') == '코스피는 3% 하락했다.'
    assert _strip_photo_noise('근거\n코스피는 3% 하락했다.\n\n수치·비교 기준') == '근거\n코스피는 3% 하락했다.\n\n수치·비교 기준'


def test_docent_uses_directional_event_and_not_old_exhibition_caption():
    body = '지난해 10월22일 서울 코엑스에서 열린 반도체 대전에서 HBM4 실물이 공개되고 있다. 2024년 10월 12일 지수가 표시되고 있다. 코스피는 외국인 매도로 3% 하락했다.'
    assert event_lead('코스피 약세', body, '2026-10-12', -4.39) == '코스피는 외국인 매도로 3% 하락했다.'
