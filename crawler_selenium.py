import os
import time
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from notion_client import Client
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 노션 설정
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DB_ID = os.getenv('NOTION_DB_ID')
notion = Client(auth=NOTION_API_KEY)

# 추적 단지 설정
COMPLEXES = {
    'hilstate1': {
        'name': '힐스테이트 도안리버파크 1단지',
        'naver_id': 148729,
        'sizes': ['84', '101', '151', '170', '180', '240']
    },
    'hilstate2': {
        'name': '힐스테이트 도안리버파크 2단지',
        'naver_id': 148730,
        'sizes': ['84', '101', '151', '170', '180', '240']
    },
    'hilstate3': {
        'name': '힐스테이트 도안리버파크 3단지',
        'naver_id': 148731,
        'sizes': ['84', '101', '151', '170', '180', '240']
    },
    'triple5': {
        'name': '도안신도시 트리풀시티 5단지',
        'naver_id': 99822,
        'sizes': ['59', '74', '84']
    },
    'triple9': {
        'name': '도안신도시 트리풀시티 9단지',
        'naver_id': 99826,
        'sizes': ['84', '107', '128', '145', '175', '231']
    },
    'thesharp1': {
        'name': '관저더샵 1차',
        'naver_id': 97040,
        'sizes': ['59', '74', '84', '104']
    },
    'thesharp2': {
        'name': '관저더샵 2차',
        'naver_id': 107123,
        'sizes': ['59', '74', '84', '104']
    },
    'arte': {
        'name': '더샵 관저아르테',
        'naver_id': 160000,
        'sizes': ['59', '84', '104', '119']
    }
}

def setup_chrome():
    """Chrome 드라이버 설정"""
    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-resources')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        logger.error(f"Chrome 드라이버 설정 실패: {str(e)}")
        return None

def get_naver_prices(driver, complex_id, complex_info):
    """네이버 부동산에서 호가 정보 추출"""
    try:
        naver_id = complex_info['naver_id']
        url = f"https://land.naver.com/complex/{naver_id}"
        
        logger.info(f"크롤링 중: {complex_info['name']} ({url})")
        
        driver.get(url)
        
        # 페이지 로딩 대기 (매물 정보 로드)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "price"))
            )
        except:
            logger.warning(f"{complex_info['name']}: 페이지 로딩 타임아웃")
        
        time.sleep(2)  # 추가 렌더링 시간
        
        # 페이지 소스 파싱
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        result = {
            'complex_id': complex_id,
            'complex_name': complex_info['name'],
            'date': datetime.now().strftime('%Y-%m-%d'),
            'prices': {},
            'count': 0
        }
        
        # 호가 정보 추출 시도 (여러 셀렉터)
        prices_found = extract_prices(soup, complex_info)
        
        if prices_found:
            result['prices'] = prices_found
            result['count'] = len(prices_found)
            logger.info(f"✓ {complex_info['name']}: {len(prices_found)}개 평수 호가 수집")
        else:
            logger.warning(f"✗ {complex_info['name']}: 호가 정보 미발견")
        
        return result
        
    except Exception as e:
        logger.error(f"크롤링 오류 ({complex_info['name']}): {str(e)}")
        return None

def extract_prices(soup, complex_info):
    """BeautifulSoup으로 호가 추출"""
    prices = {}
    
    try:
        # 셀렉터 1: 일반적인 호가 테이블
        price_items = soup.find_all('div', class_='item')
        
        for item in price_items:
            try:
                # 평수 정보
                size_text = item.find('span', class_='title')
                if not size_text:
                    continue
                
                size = size_text.get_text(strip=True)
                # "84㎡" 형식에서 "84"만 추출
                size_num = ''.join(filter(str.isdigit, size))
                
                if size_num not in complex_info['sizes']:
                    continue
                
                # 호가 정보
                price_text = item.find('span', class_='price')
                if not price_text:
                    continue
                
                price_str = price_text.get_text(strip=True)
                # "5,500만원" → "5500"
                price_num = price_str.replace(',', '').replace('만원', '').replace('억', '').strip()
                
                if price_num.isdigit():
                    prices[size_num] = int(price_num)
                    
            except Exception as e:
                logger.debug(f"항목 파싱 오류: {str(e)}")
                continue
        
        # 셀렉터 2: 다른 구조의 페이지
        if not prices:
            trade_rows = soup.find_all('tr')
            for row in trade_rows:
                try:
                    cells = row.find_all('td')
                    if len(cells) < 3:
                        continue
                    
                    size = cells[0].get_text(strip=True)
                    size_num = ''.join(filter(str.isdigit, size))
                    
                    if size_num in complex_info['sizes']:
                        price = cells[1].get_text(strip=True)
                        price_num = price.replace(',', '').replace('만원', '').strip()
                        if price_num.isdigit():
                            prices[size_num] = int(price_num)
                except:
                    continue
        
        return prices
        
    except Exception as e:
        logger.error(f"가격 추출 실패: {str(e)}")
        return {}

def save_to_notion(data):
    """노션에 데이터 저장"""
    if not data or not data.get('prices'):
        return False
    
    try:
        for size, price in data['prices'].items():
            try:
                page_data = {
                    'parent': {'database_id': NOTION_DB_ID},
                    'properties': {
                        '단지명': {
                            'title': [{'text': {'content': f"{data['complex_name']} ({size}㎡)"}}]
                        },
                        '날짜': {
                            'date': {'start': data['date']}
                        },
                        '평수': {
                            'rich_text': [{'text': {'content': f"{size}㎡"}}]
                        },
                        '호가': {
                            'number': int(price)
                        },
                        '변동율': {
                            'rich_text': [{'text': {'content': 'Auto-crawled'}}]
                        }
                    }
                }
                
                notion.pages.create(**page_data)
                logger.info(f"  → {data['complex_name']} {size}㎡: {price}만원 저장됨")
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"노션 저장 실패 ({size}㎡): {str(e)}")
                continue
        
        return True
        
    except Exception as e:
        logger.error(f"노션 연결 실패: {str(e)}")
        return False

def main():
    """메인 실행"""
    logger.info("=" * 60)
    logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 호가 자동 수집 시작")
    logger.info("=" * 60)
    
    driver = setup_chrome()
    if not driver:
        logger.error("Chrome 드라이버 초기화 실패")
        return
    
    all_results = []
    success_count = 0
    
    try:
        for complex_id, complex_info in COMPLEXES.items():
            result = get_naver_prices(driver, complex_id, complex_info)
            
            if result and result['count'] > 0:
                all_results.append(result)
                
                # 노션 저장
                if save_to_notion(result):
                    success_count += 1
                    logger.info(f"✓ {result['complex_name']}: 노션 저장 완료")
                else:
                    logger.warning(f"✗ {result['complex_name']}: 노션 저장 실패")
            else:
                logger.warning(f"✗ {complex_info['name']}: 호가 수집 실패")
            
            time.sleep(1)  # 네이버 서버 부담 경감
    
    finally:
        driver.quit()
    
    # 결과 로그 저장
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'total_complexes': len(COMPLEXES),
        'successful': success_count,
        'results': all_results
    }
    
    with open('crawl_log.json', 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    
    logger.info("=" * 60)
    logger.info(f"수집 완료: {success_count}/{len(COMPLEXES)} 단지 성공")
    logger.info(f"로그 저장: crawl_log.json")
    logger.info("=" * 60)

if __name__ == '__main__':
    main()
