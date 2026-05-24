import requests
import json
from datetime import datetime
import time
import os
from notion_client import Client

# 설정
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
NOTION_DB_ID = os.getenv('NOTION_DB_ID')
notion = Client(auth=NOTION_API_KEY)

# 추적 단지 설정
COMPLEXES = {
    'hilstate1': {
        'name': '힐스테이트 도안리버파크 1단지',
        'naver_id': 148729,
        'area': 'doan',
        'sizes': ['84', '101', '151', '170', '180', '240']
    },
    'hilstate2': {
        'name': '힐스테이트 도안리버파크 2단지',
        'naver_id': 148730,
        'area': 'doan',
        'sizes': ['84', '101', '151', '170', '180', '240']
    },
    'hilstate3': {
        'name': '힐스테이트 도안리버파크 3단지',
        'naver_id': 148731,
        'area': 'doan',
        'sizes': ['84', '101', '151', '170', '180', '240']
    },
    'triple5': {
        'name': '도안신도시 트리풀시티 5단지',
        'naver_id': 99822,
        'area': 'doan',
        'sizes': ['59', '74', '84']
    },
    'triple9': {
        'name': '도안신도시 트리풀시티 9단지',
        'naver_id': 99826,
        'area': 'doan',
        'sizes': ['84', '107', '128', '145', '175', '231']
    },
    'thesharp1': {
        'name': '관저더샵 1차',
        'naver_id': 97040,
        'area': 'gwanjeo',
        'sizes': ['59', '74', '84', '104']
    },
    'thesharp2': {
        'name': '관저더샵 2차',
        'naver_id': 107123,
        'area': 'gwanjeo',
        'sizes': ['59', '74', '84', '104']
    },
    'arte': {
        'name': '더샵 관저아르테',
        'naver_id': 160000,
        'area': 'gwanjeo',
        'sizes': ['59', '84', '104', '119']
    }
}

SIZES_TO_TRACK = ['59', '74', '84', '104', '119']

def get_naver_prices(complex_id, complex_info):
    """네이버 부동산에서 호가 정보 수집"""
    try:
        naver_id = complex_info['naver_id']
        url = f"https://land.naver.com/api/complexes/{naver_id}/details"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if 'complexDetail' in data:
            complex_detail = data['complexDetail']
            
            # 매물 정보 추출
            result = {
                'complex_id': complex_id,
                'complex_name': complex_info['name'],
                'date': datetime.now().strftime('%Y-%m-%d'),
                'prices': {},
                'counts': {
                    'sale': 0,
                    'lease': 0,
                    'monthly': 0
                }
            }
            
            # 실거래 데이터가 있으면 사용
            if 'tradeHistory' in complex_detail:
                for trade in complex_detail['tradeHistory']:
                    size = str(trade.get('areaName', ''))
                    if size in SIZES_TO_TRACK:
                        if size not in result['prices']:
                            result['prices'][size] = {
                                'min': None,
                                'max': None,
                                'avg': None
                            }
                        price = trade.get('dealPricePerArea')
                        if price:
                            if result['prices'][size]['min'] is None or price < result['prices'][size]['min']:
                                result['prices'][size]['min'] = price
                            if result['prices'][size]['max'] is None or price > result['prices'][size]['max']:
                                result['prices'][size]['max'] = price
            
            return result
        else:
            return None
            
    except Exception as e:
        print(f"Error getting prices for {complex_info['name']}: {str(e)}")
        return None

def save_to_notion(data):
    """노션에 데이터 저장"""
    try:
        if not data or not data.get('prices'):
            return False
        
        # 각 평수별로 별도의 노션 항목 생성
        for size, prices in data['prices'].items():
            if size not in SIZES_TO_TRACK:
                continue
            
            # 최저가 사용
            price = prices.get('min') or prices.get('avg')
            if not price:
                continue
            
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
                        'number': int(price / 10000) if price > 100 else price  # 만원 단위
                    },
                    '변동율': {
                        'rich_text': [{'text': {'content': 'Auto-crawled'}}]
                    }
                }
            }
            
            notion.pages.create(**page_data)
            time.sleep(0.5)  # API 레이트 제한
        
        return True
    except Exception as e:
        print(f"Error saving to Notion: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 호가 수집 시작")
    
    all_results = []
    
    for complex_id, complex_info in COMPLEXES.items():
        print(f"수집 중: {complex_info['name']}")
        result = get_naver_prices(complex_id, complex_info)
        
        if result:
            all_results.append(result)
            save_to_notion(result)
        
        time.sleep(1)  # 네이버 서버 부담 경감
    
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 호가 수집 완료 ({len(all_results)}개 단지)")
    
    # 결과 로그
    with open('crawl_log.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
