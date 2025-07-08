# fair_price_app.py
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# API KEY 세팅
DART_API_KEY = st.secrets["DART_API_KEY"]
KRX_API_KEY = st.secrets["KRX_API_KEY"]

# 기본 URL
KRX_BASE = "http://data-dbg.krx.co.kr/svc/apis/sto"
DART_BASE = "https://opendart.fss.or.kr/api"

# 공통 헤더 (KRX API 우회용)
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://data.krx.co.kr",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def get_krx_basic_info(date):
    url = f"{KRX_BASE}/stk_isu_base_info.json"
    res = requests.get(url, params={"basDd": date}, headers=KRX_HEADERS)
    return pd.DataFrame(res.json().get("OutBlock_1", []))

def get_krx_daily_info(date):
    url = f"{KRX_BASE}/stk_bydd_trd.json"
    res = requests.get(url, params={"basDd": date}, headers=KRX_HEADERS)
    return pd.DataFrame(res.json().get("OutBlock_1", []))

def get_dart_financials(corp_code, year):
    url = f"{DART_BASE}/fnlttSinglAcnt.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": "11011"  # 사업보고서
    }
    res = requests.get(url, params=params)
    return res.json()

def calculate_fair_price(eps, per_avg, peg_adj, growth_factor, roe_weight, revenue_growth_adj, stability_score):
    price = eps * (per_avg + peg_adj + growth_factor)
    price *= (roe_weight + revenue_growth_adj)
    price *= (stability_score / 100)
    return price

def estimate_stability_score(debt_ratio, current_ratio):
    return 100 - (debt_ratio * 0.1) + (current_ratio * 0.05)

st.title("📈 적정주가 자동 계산기")

# 사용자 입력
user_input = st.text_input("종목 코드 또는 종목명 입력 (예: 005930 또는 삼성전자)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

if user_input:
    # 데이터 수집
    krx_basic_df = get_krx_basic_info(base_date)
    krx_daily_df = get_krx_daily_info(base_date)

    if krx_basic_df.empty:
        st.error("KRX 기본정보를 불러오지 못했습니다. 날짜를 확인하거나 서버 상태를 점검하세요.")
    elif "ISU_SRT_CD" not in krx_basic_df.columns:
        st.error(f"KRX 기본정보 형식이 예상과 다릅니다: {krx_basic_df.columns.tolist()}")
        st.dataframe(krx_basic_df)
    else:
        target_info = krx_basic_df[krx_basic_df["ISU_SRT_CD"] == user_input]
        if target_info.empty:
            target_info = krx_basic_df[krx_basic_df["ISU_NM"] == user_input]

        if not target_info.empty:
            isu_cd = target_info.iloc[0]["ISU_CD"]
            isu_nm = target_info.iloc[0]["ISU_NM"]
            st.subheader(f"📋 종목 기본정보 - {isu_nm}")
            st.dataframe(target_info)

            target_daily = krx_daily_df[krx_daily_df["ISU_CD"] == isu_cd]
            st.subheader("📊 일별 매매정보")
            st.dataframe(target_daily)

            # 임시 샘플 재무정보 (실제 DART 연동 필요)
            eps = 5500
            roe = 12.0
            revenue_growth = 8.0
            debt_ratio = 80.0
            current_ratio = 130.0

            st.subheader("📑 재무 정보 (샘플)")
            st.write(f"EPS: {eps}")
            st.write(f"ROE: {roe}%")
            st.write(f"매출 성장률: {revenue_growth}%")
            st.write(f"부채비율: {debt_ratio}%")
            st.write(f"유동비율: {current_ratio}%")

            # 계산값
            per_avg = 10
            peg_adj = 1.0
            growth_factor = revenue_growth / 10
            roe_weight = roe * 0.01
            revenue_growth_adj = revenue_growth * 0.01
            stability_score = estimate_stability_score(debt_ratio, current_ratio)

            st.subheader("🧮 계산 중간값")
            st.write(f"PER 평균: {per_avg}")
            st.write(f"PEG 조정치: {peg_adj}")
            st.write(f"성장가중치: {growth_factor:.2f}")
            st.write(f"ROE 보정계수: {roe_weight:.2f}")
            st.write(f"매출성장률 보정치: {revenue_growth_adj:.2f}")
            st.write(f"안정성 점수: {stability_score:.2f}")

            fair_price = calculate_fair_price(eps, per_avg, peg_adj, growth_factor, roe_weight, revenue_growth_adj, stability_score)

            st.subheader("🎯 적정주가 결과")
            current_price = int(target_daily.iloc[0]["TDD_CLSPRC"].replace(",", ""))
            st.metric("적정주가", f"{fair_price:,.0f} 원")
            st.metric("현재 주가", f"{current_price:,.0f} 원")
            diff_pct = (fair_price - current_price) / current_price
            st.metric("프리미엄/할인율", f"{diff_pct:+.2%}")

        else:
            st.warning("입력한 종목에 대한 정보를 찾을 수 없습니다.")
