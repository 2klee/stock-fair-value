import requests
import datetime
import os

BASE_TRD_URL = "http://openapi.krx.co.kr/openapi/service/sto/stk_bydd_trd"
BASE_MAST_URL = "http://openapi.krx.co.kr/openapi/service/sto/stk_mast_get"
AUTH_KEY = os.environ.get("AUTH_KEY") or ""

def get_today():
    return datetime.datetime.now().strftime("%Y%m%d")

def get_isin_from_input(user_input):
    params = {
        "serviceKey": AUTH_KEY,
        "pageNo": "1",
        "numOfRows": "5000",
        "resultType": "json"
    }
    response = requests.get(BASE_MAST_URL, params=params)
    if response.status_code == 200:
        items = response.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
        for item in items:
            if user_input in (item.get("itmsNm", ""), item.get("srtnCd", "")):
                return item.get("isuCd")
    return None

def get_stock_info_by_name_or_code(user_input):
    if not AUTH_KEY:
        raise ValueError("AUTH_KEY가 설정되지 않았습니다. secrets.toml 또는 환경변수에서 등록해주세요.")

    isin = get_isin_from_input(user_input)
    if not isin:
        return None

    params = {
        "basDd": get_today(),
        "isuCd": isin,
        "serviceKey": AUTH_KEY
    }
    response = requests.get(BASE_TRD_URL, params=params)
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
