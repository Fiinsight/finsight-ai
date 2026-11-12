"""Java ChartTextEvidence is authoritative; mirrored rules are checked with shared synthetic contracts."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import re
from app.services import llm_client

COMPANIES={
 '005930':r'삼성\s*전자|삼전(?!기)|(?<![a-z])Samsung\s+Electronics(?![a-z])',
 '000660':r'(?:SK\s*)?하이닉스|(?:SK\s*)?하닉|삼전닉스|(?<![a-z])SK\s+hynix(?![a-z])',
 '035720':r'카카오(?!뱅크|페이|게임즈|뱅|분말|버터|열매)|(?<![a-z])Kakao(?![a-z])',
 '035420':r'네이버|(?<![a-z])NAVER(?![a-z])',
 '373220':r'LG\s*에너지\s*솔루션|LG\s*엔솔|엘지\s*(?:에너지\s*솔루션|엔솔)|(?<![a-z])LG\s+Energy\s+Solution(?![a-z])',
 '005380':r'현대\s*자동차|현대차(?!\s*증권)|(?<![a-z])Hyundai\s+Motor(?![a-z])',
 '000270':r'(?<![가-힣])기아(?:자동차)?(?!대책|문제|상태)',
 '207940':r'삼성\s*바이오\s*로직스|삼성\s*바이오(?!\s*에피스)|삼바(?!춤|축제)',
 '051910':r'(?:LG|엘지)\s*화학','068270':r'셀트리온',
 '005490':r'포스코홀딩스|POSCO\s*홀딩스|포스코(?!퓨처엠|인터내셔널|이앤씨)',
}
SECTORS={s:terms for symbols,terms in [
 (['005930','000660'],['반도체','메모리','HBM']),
 (['035420','035720'],['인터넷 기업','인터넷 업계','플랫폼 기업','플랫폼 업계','온라인 광고','검색 광고','포털 업계']),
 (['373220','051910','006400'],['배터리','이차전지','2차전지']),
 (['005380','000270'],['자동차','완성차','전기차']),
 (['207940','068270'],['바이오','제약','의약품'])] for s in symbols}
EVENT=re.compile(r'발표|공시|수주|계약|실적|가이던스|인수|소송|제재|승인|리콜|순매도|순매수|금리|관세')
MARKET=re.compile(r'코스피|코스닥|증시|주식시장|주식 시장|주가지수|FOMC|나스닥',re.I)
CAUSE=re.compile(r'([^.!?。！？\n]{2,90}?(?:소식에|우려에|기대에|영향으로|여파로|발표 후|매도세에|매수세에|으로|로|에))\s*(?:(?:[+-]?\d+(?:\.\d+)?%|주가가|주가는|장중|이날|오늘)\s*){0,4}(?:급등|급락|상승|하락|강세|약세)')
CAUSE_EVENT=re.compile(r'실적|이익|매출|수주|계약|금리|환율|관세|매도|매수|수급|우려|기대|수요|공급|발표|공시|규제|정책|인수|소송|제재|승인|리콜')
UP=re.compile(r'급등|상승|상향|강세|반등|상한가|신고가|폭등|치솟|껑충|뛰었|올라|사자|매수|상회|호실적|수혜|우려\s*해소|하락\s*멈춰|매도\s*의견\s*철회|52주.{0,5}(?:최고|고점)|%\s*↑')
DOWN=re.compile(r'반등\s*실패|우려\s*해소\s*실패|매도\s*의견\s*철회\s*실패|급락|하락|하향|약세|낙폭|하한가|신저가|폭락|추락|곤두박질|주저앉|내려|떨어|팔자|매도|하회|부진|우려|규제 강화|52주.{0,5}(?:최저|저점)|%\s*↓')
UNCERTAIN=re.compile(r'상승폭\s*축소|낙폭\s*축소|(?:상승|하락).{0,8}(?:않|못)')

def number(value):
    return Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

def signed(value):return f'{number(value):+.2f}%'

def excess(request):
    value=number(request.change_percent)-number(request.index_change_percent)
    return Decimal(0) if value==0 else value

def topic(word):
    code=ord(word[-1])
    return word+('은' if 0xAC00<=code<=0xD7A3 and (code-0xAC00)%28 else '는')

def sentiment(title,hint=None,confidence=None):
    if confidence is not None:return hint if confidence>=.6 and hint in ('POSITIVE','NEGATIVE') else None
    last=lambda p:max((m.end() for m in p.finditer(title)),default=-1)
    up,down,unknown=last(UP),last(DOWN),last(UNCERTAIN)
    if unknown>=max(up,down) and unknown>=0:return None
    return None if up==down else 'POSITIVE' if up>down else 'NEGATIVE'

def sentences(title,summary,day):
    reference=datetime.fromisoformat(day).date();result=[]
    for text in llm_client._split_sentences(llm_client._clean_article_text(title,summary)):
        if re.search(r'사진\s*=|\(사진\)|제공',text):continue
        if re.search(r'(지난해|작년|\d{1,2}\s*월\s*\d{1,2}\s*일).*열린',text) and re.search(r'(되고|하고)\s*있(?:다|어요)',text):continue
        old=False
        for year,month,date in re.findall(r'(20\d{2})[./년-]\s*(\d{1,2})[./월-]\s*(\d{1,2})',text):
            try:old|=abs((reference-datetime(int(year),int(month),int(date)).date()).days)>=365
            except ValueError:pass
        if not old and text.strip():result.append(text)
    return result

def subject(request,text,relation):
    if relation=='DIRECT':return bool(re.search(COMPANIES.get(request.symbol,re.escape(request.symbol_name)),text,re.I))
    if relation=='SECTOR':return any(term in text for term in SECTORS.get(request.symbol,[]))
    return relation=='MARKET' and bool(MARKET.search(text))

def lead(request,article):
    candidates=sentences(article.title,article.summary,request.date)
    direction=re.compile(r'하락|급락|약세|매도' if request.change_percent<0 else r'상승|급등|강세|매수')
    eligible=[(i,s) for i,s in enumerate(candidates) if len(s)<=400 and subject(request,s,article.relation)]
    if eligible:return max(eligible,key=lambda pair:(2 if EVENT.search(pair[1]) else 0,1 if direction.search(pair[1]) else 0,-pair[0]))[1]
    return article.title if subject(request,article.title,article.relation) else '이 종목을 직접 다루는 문장을 확인하지 못했어요.' if article.relation=='DIRECT' else '이 시점의 관련 보도를 확인했어요.'

def polite(text,level):
    if level=='analyst':return text
    return re.sub(r'이다(?=[.!?。！？]|$)','이에요',llm_client._repair_rewrite_style(text))

def cause(request,article):
    if article.cause_phrase is not None:return article.cause_phrase
    for text in [article.title]+sentences(article.title,article.summary,request.date):
        if not subject(request,text,article.relation):continue
        for match in CAUSE.finditer(text):
            phrase=match[1].strip()
            if CAUSE_EVENT.search(phrase) and '에도' not in phrase and '지만' not in phrase:return phrase
    return None

def comparison(request):
    if request.index_change_percent is None or request.index_name is None:return ''
    difference=excess(request)
    context=request.market_context or ('OPPOSITE' if request.change_percent*request.index_change_percent<0 else 'FOLLOWING' if abs(request.change_percent-request.index_change_percent)<1 else 'INDIVIDUAL')
    position='' if abs(request.change_percent)<=.5 else '시장과 비슷한 방향·폭으로, ' if context=='FOLLOWING' else '시장과 반대 방향으로, ' if context=='OPPOSITE' else ''
    period='같은 주간' if request.period=='W' else '같은 시점' if request.period=='MINUTE' else '같은 날'
    if request.level=='analyst':return f'{period} {request.index_name} {signed(request.index_change_percent)}·{request.symbol_name} {signed(request.change_percent)}로, {position}초과 등락률은 {difference:+.2f}%p예요.'
    return f"{period} {topic(request.index_name)} {signed(request.index_change_percent)}, {topic(request.symbol_name)} {signed(request.change_percent)}로, {position}등락률이 시장보다 {abs(difference):.2f}%p {'높았어요' if difference>=0 else '낮았어요'}."

def reason(request,article):
    market=comparison(request)
    if article is None:return market+' 가격 비교만으로 원인을 단정하지 않아요.' if market else f'주가는 {signed(request.change_percent)} 움직였지만, 이 시점을 설명하는 뉴스와 시장 자료를 찾지 못했어요.'
    title=article.title
    hint=sentiment(title.split('에도',1)[0],article.sentiment_hint,article.sentiment_confidence)
    neutral=abs(request.change_percent)<=.5
    opposite=not neutral and (hint=='POSITIVE' and request.change_percent<0 or hint=='NEGATIVE' and request.change_percent>0)
    phrase=cause(request,article)
    if neutral:first='시장이 움직인 날에도 주가는 거의 변하지 않았어요.' if article.relation=='MARKET' else '관련 소식이 나왔지만 주가는 거의 움직이지 않았어요.'
    elif opposite:first=f"{'호재' if hint=='POSITIVE' else '악재'} 소식에도 주가는 {'내렸어요' if request.change_percent<0 else '올랐어요'}, 다른 원인은 이 기사만으로 확인하기 어려워요."
    elif phrase:first=f"{'마감 후 보도의 ' if article.after_close_report else '기사의 '}‘{phrase}’ 표현처럼 해당 요인이 영향을 줬을 수 있어요."
    else:first=f"{'마감 후 관련 소식: ‘' if article.after_close_report else '관련 소식: ‘'}{title}’."
    if article.relation=='SECTOR':first=first[:-1]+', 이 종목을 직접 다룬 기사는 아니에요.'
    if market and not neutral and (request.market_context=='FOLLOWING' or request.market_context is None and request.change_percent*request.index_change_percent>=0 and abs(request.change_percent-request.index_change_percent)<1):return market+' '+first
    return first+' '+(market or f'주가는 {signed(request.change_percent)} 움직였지만, 같은 기간 지수 자료는 확인하지 못했어요.')

def impact(request,article,selected_lead):
    evidence=article.title+' '+selected_lead if article else ''
    if re.search('수주|계약',evidence):next_check='계약 규모·기간 공시를 확인해요'
    elif re.search('실적|매출|영업이익',evidence):next_check='발표 실적과 시장 예상치의 차이를 확인해요'
    elif re.search('규제|정책|관세',evidence):next_check='발표한 정책의 시행 시점을 확인해요'
    elif re.search(r'(?:외국인|기관).{0,20}(?:순매수|순매도|매도세|매수세|매매)|수급|프로그램 매매',evidence):next_check='이후 외국인·기관 매매가 이어지는지 확인해요'
    else:next_check='추가로 확인할 개별 사건 자료가 없어요'
    if request.index_change_percent is None:return '추가로 확인할 시장 자료가 없어요.' if article is None or next_check.startswith('추가로') else next_check+'.'
    return f'시장 대비 초과 등락률은 {excess(request):+.2f}%p이며, {next_check}.'
