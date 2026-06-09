import json
import urllib.request
import requests
from newspaper4k import Article

# 1. 네이버 API 인증 정보 설정
CLIENT_ID = "iz0XBoN0gbwosRbh5GSB"        # 발급받은 Client ID 입력
CLIENT_SECRET = "1CR6msoO53" # 발급받은 Client Secret 입력

def get_naver_news(search_keyword, display_count=5):
    """
    네이버 검색 API를 통해 뉴스 검색 결과를 가져옵니다.
    """
    encText = urllib.parse.quote(search_keyword)
    # 속보성 순으로 가져오려면 sort=sim 대신 sort=date 사용 가능
    url = f"https://openapi.naver.com/v1/search/news.json?query={encText}&display={display_count}&sort=sim"
    
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", CLIENT_SECRET)
    
    try:
        response = urllib.request.urlopen(request)
        rescode = response.getcode()
        if rescode == 200:
            response_body = response.read()
            return json.loads(response_body.decode('utf-8'))['items']
        else:
            print(f"Error Code: {rescode}")
            return []
    except Exception as e:
        print(f"API 요청 중 오류 발생: {e}")
        return []

def extract_article_text(url):
    """
    newspaper3k 라이브러리를 이용해 해당 URL의 기사 본문을 추출합니다.
    """
    try:
        # 한국어 설정(ko) 후 다운로드 및 파싱
        article = Article(url, language='ko')
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        # 네이버 뉴스 인링크(sports, entertain 등)나 일부 언론사 보안 정책에 따라 차단될 수 있음
        return f"[본문 추출 실패: {e}]"

# 3. 메인 실행부
if __name__ == "__main__":
    keyword = "항공 산업" # 검색할 키워드
    print(f"'{keyword}' 검색 결과 관련 뉴스 본문 추출을 시작합니다...\n")
    
    news_items = get_naver_news(keyword, display_count=3)
    
    for idx, item in enumerate(news_items, 1):
        title = item['title'].replace("<b>", "").replace("</b>", "").replace("&quot;", '"')
        link = item['link'] # 원본 언론사 링크 (네이버 인링크가 아닐 수 있음)
        
        print(f"[{idx}] 제목: {title}")
        print(f"    링크: {link}")
        
        # 본문 추출 진행
        print("    본문 추출 중...")
        content = extract_article_text(link)
        
        print("-" * 50)
        print(content[:300] + "..." if len(content) > 300 else content) # 앞부분 300자만 출력
        print("-" * 50)
        print("\n")