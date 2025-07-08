import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# 🔑 인증키
API_KEY = st.secrets["KRX_API_KEY"]

# ✅ 종목 리스트 가져오기 (코스피 + 코스닥)
def fetch_stock_list():
    def get_market_data(api_id):
        url = f"https://data-dbg.krx.co.kr/svc/apis/sto/{api_id}.json"
        params = {
            "serviceKey": API_KEY,
            "resultType": "json",
            "pageNo": "1",
            "numOfRows": "1000"
        }
        res = requests.get(url, params=params)
        if res.status_code == 200:
            return res.json().get("response", {}).get("body", {}).get("items", [])
        else:
            return []

    kospi = get_market_data("stk_isu_base_info")
    kosdaq = get_market_data("ksq_isu_base_info")
    return kospi + kosdaq

# ✅ 이름 또는 코드로 종목 검색하기
def find_isin_by_input(stock_list, user_input):
    user_input = user_input.strip().lower()
    for item in stock_list:
        if user_input in item.get("itmsNm", "").lower() or user_input in item.get("srtnCd", "").lower():
            return item.get("isuCd"), item.get("itmsNm"), item.get("srtnCd")
    return None, None, None

# ✅ 종목 시세 정보 불러오기 (전일종가, 시가총액 등)
def get_stock_info_by_isin(isin):
    url = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd.json"
    today = datetime.today().strftime("%Y%m%d")
    params = {
        "serviceKey": API_KEY,
        "resultType": "json",
        "basDd": today,
        "isuCd": isin
    }
    res = requests.get(url, params=params)
    if res.status_code == 200:
        items = res.json().get("response", {}).get("body", {}).get("items", [])
        return items[0] if items else None
    return None

# ✅ 적정주가 계산 로직 (예시)
def calculate_fair_value(eps, target_per):
    try:
        return float(eps) * float(target_per)
    except:
        return None

# ✅ Streamlit UI 구성
st.set_page_config(page_title="KRX 종목 적정주가 계산기", layout="centered")
st.title("📊 KRX 종목 적정주가 계산기")

user_input = st.text_input("종목명 또는 코드 입력", "")
if st.button("조회하기"):
    with st.spinner("데이터를 조회 중입니다..."):
        stock_list = fetch_stock_list()
        isin, name, code = find_isin_by_input(stock_list, user_input)

        if not isin:
            st.error("📛 해당 종목을 찾을 수 없습니다. 정확한 이름이나 코드를 입력해 주세요.")
        else:
            st.success(f"✅ 종목명: {name}, 종목코드: {code}, ISIN: {isin}")
            info = get_stock_info_by_isin(isin)
            if info:
                st.subheader("📈 시세 정보")
                st.write(info)
                
                eps = st.number_input("EPS (주당순이익)", value=3000.0)
                per = st.number_input("적정 PER (주가수익비율)", value=10.0)
                fair_price = calculate_fair_value(eps, per)
                if fair_price:
                    st.metric(label="📌 계산된 적정주가", value=f"{fair_price:,.0f} 원")
                else:
                    st.warning("EPS 또는 PER 입력이 잘못되었습니다.")
            else:
                st.warning("🚨 시세 정보를 불러오지 못했습니다.")
