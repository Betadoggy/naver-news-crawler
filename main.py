import csv
import json
import math
import os
import re
import requests
import time
from bs4 import BeautifulSoup
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from kiwipiepy import Kiwi

LIMIT_COUNT = 100
CLIENT_ID = "iz0XBoN0gbwosRbh5GSB"
CLIENT_SECRET = "1CR6msoO53"
KEYWORD = "공항 AND 친환경"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
STOPWORDS = {
    "이", "그", "저", "것", "수", "등", "들", "더", "가", "와", "과",
    "에서", "에게", "를", "은", "는", "도", "로", "으로", "하다", "합니다",
    "이다", "되다", "있다", "없다", "이번", "여기", "오늘", "내일", "지난",
    "대한", "관련", "뉴스", "기자", "단계", "공항", "친환경"
}

session = requests.Session()
session.headers.update({
    "X-Naver-Client-Id": CLIENT_ID,
    "X-Naver-Client-Secret": CLIENT_SECRET,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/120.0.0.0"
})

kiwi = Kiwi()

def tokenize_ko(text):
    tokens = []
    for token in kiwi.tokenize(text):
        if not token.tag:
            continue
        if token.tag[0] not in ("N", "V", "J", "X"):
            continue
        form = token.form.strip()
        if len(form) > 1 and form not in STOPWORDS:
            tokens.append(form)
    return tokens


def compute_tfidf(documents):
    token_docs = [tokenize_ko(doc) for doc in documents]
    df = Counter()
    for tokens in token_docs:
        df.update(set(tokens))

    n_docs = len(token_docs)
    corpus_scores = []
    for tokens in token_docs:
        tf = Counter(tokens)
        total = sum(tf.values()) or 1
        scores = {}
        for term, count in tf.items():
            tf_val = count / total
            idf_val = math.log((n_docs + 1) / (df[term] + 1)) + 1
            scores[term] = tf_val * idf_val
        corpus_scores.append(scores)
    return corpus_scores, df


def get_top_terms(tfidf_scores, top_n=10):
    return sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]


def analyze_tfidf(documents, titles=None, top_n_terms=50):
    if not documents:
        print("TF-IDF 분석할 문서가 없습니다.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    titles = titles or [f"문서 {i + 1}" for i in range(len(documents))]
    tfidf_corpora, df = compute_tfidf(documents)
    overall = Counter()
    for scores in tfidf_corpora:
        overall.update(scores)

    summary_path = os.path.join(OUTPUT_DIR, "tfidf_summary.csv")
    with open(summary_path, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["rank", "term", "score", "document_frequency"])
        for rank, (term, score) in enumerate(overall.most_common(top_n_terms), 1):
            writer.writerow([rank, term, f"{score:.6f}", df[term]])

    detailed_path = os.path.join(OUTPUT_DIR, "tfidf_document_top_terms.csv")
    with open(detailed_path, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["document_index", "title", "term", "score"])
        for idx, (title, scores) in enumerate(zip(titles, tfidf_corpora), 1):
            for term, score in get_top_terms(scores, 20):
                writer.writerow([idx, title, term, f"{score:.6f}"])

    print(f"TF-IDF 분석 완료: {summary_path}")
    print(f"문서별 상위 단어 저장 완료: {detailed_path}")


def handle_exception(default_return):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try: return func(*args, **kwargs)
            except Exception as e:
                print(f" [{func.__name__}] 오류 발생: {e}")
                return default_return
        return wrapper
    return decorator

@handle_exception(default_return=[])
def get_naver_news(search_keyword, total_count=1000):
    """페이징을 사용하여 total_count 만큼 뉴스 리스트를 가져옵니다."""
    url = "https://openapi.naver.com/v1/search/news.json"
    results = []
    
    # 100개씩 루프를 돌며 수집
    for start in range(1, total_count + 1, 100):
        params = {"query": search_keyword, "display": 100, "start": start, "sort": "sim"}
        response = session.get(url, params=params)
        
        if response.status_code == 200:
            items = response.json().get('items', [])
            if not items: break
            results.extend(items)
            print(f"    ▶ 뉴스 리스트 수집 중... (현재 {len(results)}개 확보)")
            time.sleep(0.1) # 서버 부하 방지
        else:
            print(f"    ▶ API 호출 오류: {response.status_code}")
            break
    return results

@handle_exception(default_return="[본문 추출 실패]")
def extract_article_text(url):
    """BeautifulSoup 기반으로 HTML에서 본문 텍스트를 추출합니다."""
    response = session.get(url, timeout=5)
    response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8'

    if response.status_code != 200:
        return f"[본문 추출 실패: HTTP {response.status_code}]"

    soup = BeautifulSoup(response.text, "html.parser")

    # 불필요한 스크립트/스타일 제거
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    article = soup.find("article")
    if article:
        paragraphs = article.find_all("p")
    else:
        candidates = soup.find_all("div", class_=re.compile(r"(article|content|news|text|body)", re.I))
        if candidates:
            paragraphs = []
            for candidate in candidates:
                paragraphs.extend(candidate.find_all("p"))
        else:
            paragraphs = soup.find_all("p")

    paragraph_texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
    if paragraph_texts:
        return "\n\n".join(paragraph_texts)

    return soup.get_text(separator="\n", strip=True)

def clean_text(text, is_filename=False):
    if is_filename:
        return re.sub(r'[\/:*?"<>|]', '_', text).strip()
    return re.sub(r'<[^>]*>|&quot;|&amp;', lambda m: {'&quot;': '"', '&amp;': '&'}.get(m.group(), ''), text)

def process_single_news(args):
    idx, item, total = args
    title = clean_text(item['title'])
    link = item['link']
    content = extract_article_text(link)
    
    file_content = f"제목: {title}\n링크: {link}\n{'-'*50}\n본문:\n{content}\n"
    filename = f"{idx:04d}_{clean_text(title, is_filename=True)[:30]}.txt"
    filepath = os.path.join(DATA_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(file_content)
    print(f"    저장 완료: {filepath}")
    return {
        'idx': idx,
        'title': title,
        'content': content,
        'filepath': filepath,
    }

if __name__ == "__main__":
    print(f"검색어: {KEYWORD}")
    print(f"관련 뉴스 {LIMIT_COUNT}개 수집 시작...\n")
    
    # 1. 뉴스 리스트 먼저 확보
    news_items = get_naver_news(KEYWORD, total_count=LIMIT_COUNT)
    total_count = len(news_items)
    print(f"\n총 {total_count}개의 뉴스 본문 추출 및 저장을 시작합니다.\n")

    os.makedirs(DATA_DIR, exist_ok=True)
    
    # 2. 병렬로 본문 처리
    tasks = [(idx, item, total_count) for idx, item in enumerate(news_items, 1)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        saved_results = list(executor.map(process_single_news, tasks))

    # 3. 추출된 본문을 기반으로 TF-IDF 분석
    valid_results = [item for item in saved_results if item and item['content'] and not item['content'].startswith('[본문 추출 실패]')]
    contents = [item['content'] for item in valid_results]
    titles = [item['title'] for item in valid_results]
    if contents:
        analyze_tfidf(contents, titles, top_n_terms=15)
    else:
        print("TF-IDF 분석을 위한 본문 데이터가 충분하지 않습니다.")
        
    print("\n완료!")