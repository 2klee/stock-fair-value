import requests
import datetime
import os

BASE_URL = "http://openapi.krx.co.kr/openapi/service/sto/stk_bydd_trd"
AUTH_KEY = os.environ.get("AUTH_KEY") or ""

def get_today():
    return datetime.datetime.now().strftime("%Y%m%d")

def get_stock_info_by_code(stock_code):
    if not AUTH_KEY:
        raise ValueError("AUTH_KEY가 설정되지 않았습니다. secrets.toml 또는 환경변수에서 등록해주세요.")

    isin_map = {
        "005930": "KR7005930003",  # 삼성전자
        "000660": "KR7000660001",  # SK하이닉스
    }
    isin = isin_map.get(stock_code)
    if not isin:
        return None

    params = {
        "basDd": get_today(),
        "isuCd": isin,
        "serviceKey": AUTH_KEY
    }
    response = requests.get(BASE_URL, params=params)
    if response.status_code == 200:
        try:
            items = response.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if items:
                return items[0]
        except:
            return None
    return None

def get_fair_value(data):
    try:
        eps = float(data.get("eps", 0))
        per = float(data.get("per", 0))
        return eps * per
    except:
        return 0
