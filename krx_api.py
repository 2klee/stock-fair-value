import requests
import streamlit as st

BASE_MAST_URL = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_mast_get.json"
BASE_INFO_URL = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd.json"
AUTH_KEY = st.secrets["AUTH_KEY"]


def get_isin_from_input(user_input):
    print("🔍 [get_isin_from_input] 실행됨")
    print("✅ 사용자 입력값:", user_input)

    params = {
    "serviceKey": AUTH_KEY,
    "resultType": "json",
    "pageNo": "1",
    "numOfRows": "5000"
}

    try:
        response = requests.get(BASE_MAST_URL, params=params)
        print("📡 API 응답 코드:", response.status_code)

        if response.status_code == 200:
            data = response.json()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            print(f"📦 종목 수신 개수: {len(items)}개")

            user_input = user_input.strip().lower()
            for item in items:
                name = item.get("itmsNm", "").lower()
                code = item.get("srtnCd", "").lower()
                isin = item.get("isuCd", "")
                if user_input in name or user_input in code:
                    print(f"🎯 일치 항목 찾음: {name} / {code} → ISIN: {isin}")
                    return isin

            print("❗ 일치하는 종목 없음")
        else:
            print("🚨 API 응답 실패:", response.text)

    except Exception as e:
        print("❌ 예외 발생:", e)

    return None


def get_stock_info_by_name_or_code(user_input):
    isin = get_isin_from_input(user_input)
    if not isin:
        return None

    params = {
        "serviceKey": AUTH_KEY,
        "basDd": "20240705",  # 날짜는 테스트용 고정값 또는 오늘 날짜로 설정 가능
        "isuCd": isin,
        "resultType": "json"
    }

    try:
        response = requests.get(BASE_INFO_URL, params=params)
        print("📡 종목 상세 API 응답 코드:", response.status_code)
        if response.status_code == 200:
            data = response.json()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if items:
                print("📊 종목 데이터:", items[0])
                return items[0]
            else:
                print("📭 데이터 없음")
        else:
            print("⚠️ 응답 실패:", response.text)
    except Exception as e:
        print("❌ 예외 발생:", e)

    return None
