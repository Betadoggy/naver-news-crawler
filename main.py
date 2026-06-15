import csv, math, os, re, requests, time
from bs4 import BeautifulSoup
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from kiwipiepy import Kiwi
import urllib3

# 네이버 뉴스 리다이렉트(n.news.naver.com) 시 발생하는 SSL 경고까지 완벽히 차단
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import logging
logging.getLogger("urllib3").setLevel(logging.ERROR)

LIMIT_COUNT = 100
CLIENT_ID, CLIENT_SECRET = "iz0XBoN0gbwosRbh5GSB", "1CR6msoO53"
KEYWORD = "공항 친환경"
DATA_DIR, OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data"), os.path.join(os.path.dirname(__file__), "output")
STOPWORDS = {"이", "그", "저", "것", "수", "등", "들", "더", "가", "와", "과", "에서", "에게", "를", "은", "는", "도", "로", "으로", "하다", "합니다", "이다", "되다", "있다", "없다", "이번", "여기", "오늘", "내일", "지난", "대한", "관련", "뉴스", "기자", "단계", "공항", "친환경", "위하", "까지", "브리핑", "이슈", "올해"}

session = requests.Session()
session.verify = False
session.headers.update({"X-Naver-Client-Id": CLIENT_ID, "X-Naver-Client-Secret": CLIENT_SECRET, "User-Agent": "Mozilla/5.0"})
kiwi = Kiwi()

def tokenize_ko(text):
    return [t.form.strip() for t in kiwi.tokenize(text) if t.tag and t.tag[0] in ("N", "V", "J", "X") and len(t.form.strip()) > 1 and t.form.strip() not in STOPWORDS]

def compute_tfidf(documents):
    token_docs = [tokenize_ko(doc) for doc in documents]
    df = Counter()
    for tokens in token_docs: df.update(set(tokens))
    
    corpus_scores = []
    for tokens in token_docs:
        tf = Counter(tokens)
        total = sum(tf.values()) or 1
        scores = {term: (count / total) * (math.log((len(token_docs) + 1) / (df[term] + 1)) + 1) for term, count in tf.items()}
        corpus_scores.append(scores)
    return corpus_scores, df

def analyze_tfidf(documents, titles):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tfidf_corpora, df = compute_tfidf(documents)
    
    overall = Counter()
    for scores in tfidf_corpora: overall.update(scores)

    with open(os.path.join(OUTPUT_DIR, "tfidf_summary.csv"), "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "term", "score", "document_frequency"])
        for r, (term, score) in enumerate(overall.most_common(50), 1): writer.writerow([r, term, f"{score:.6f}", df[term]])

    with open(os.path.join(OUTPUT_DIR, "tfidf_document_top_terms.csv"), "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["document_index", "title", "term", "score"])
        for idx, (title, scores) in enumerate(zip(titles, tfidf_corpora), 1):
            for term, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:20]:
                writer.writerow([idx, title, term, f"{score:.6f}"])

def get_naver_news(keyword, total_count):
    url, results = "https://openapi.naver.com/v1/search/news.json", []
    
    for sort_type in ["sim", "date"]:
        start = 1
        while len(results) < total_count and start <= 1000:
            try:
                res = session.get(url, params={"query": keyword, "display": 100, "start": start, "sort": sort_type})
                items = res.json().get('items', []) if res.status_code == 200 else []
                if not items: break
                
                for item in items:
                    if "news.naver.com" in item.get('link', '') and item['link'] not in [r['link'] for r in results]:
                        results.append(item)
                        if len(results) >= total_count: return results
                start += 100
                time.sleep(0.1)
            except: break
    return results

def extract_article_text(url):
    try:
        res = session.get(url, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        article = soup.find("article", id="dic_area") or soup.find("div", id="newsct_article") or soup.find("div", id="articleBodyContents")
        if article:
            for tag in article(["script", "style", "noscript", "iframe", "span"]): tag.decompose()
            text = re.sub(r'\[.*?\]', '', article.get_text(separator="\n", strip=True))
            if text.strip(): return text.strip()
    except: pass
    return None

def process_single_news(args):
    idx, item = args
    title = re.sub(r'<[^>]*>|&quot;|&amp;', lambda m: {'&quot;': '"', '&amp;': '&'}.get(m.group(), ''), item['title'])
    content = extract_article_text(item['link'])
    if not content: return None
    
    # [버그 수정] 윈도우 파일명 금지 문자(\ / : * ? " < > |)를 모두 언더바(_)로 안전하게 변경
    safe_title = re.sub(r'[\/:*?"<>|]', '_', title).strip()[:30]
    filename = f"{idx:04d}_{safe_title}.txt"
    
    with open(os.path.join(DATA_DIR, filename), 'w', encoding='utf-8') as f:
        f.write(f"제목: {title}\n링크: {item['link']}\n{'-'*50}\n본문:\n{content}\n")
    print(f"    [{idx:03d}] 저장 완료")
    return {'title': title, 'content': content}

if __name__ == "__main__":
    print(f"검색어: {KEYWORD} | 목표: {LIMIT_COUNT}개")
    news_items = get_naver_news(KEYWORD, LIMIT_COUNT)
    
    if not news_items:
        print("수집된 링크가 없습니다.")
        exit()

    os.makedirs(DATA_DIR, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as executor:
        saved_results = list(executor.map(process_single_news, enumerate(news_items, 1)))

    valid_results = [r for r in saved_results if r]
    print(f"\n▶ 본문 추출 성공 문서: {len(valid_results)} / {len(news_items)}")
    
    if valid_results:
        analyze_tfidf([r['content'] for r in valid_results], [r['title'] for r in valid_results])
    print("\n완료!")