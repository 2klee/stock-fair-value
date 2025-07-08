# fair_price_app.py
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# API 키
DART_API_KEY = st.secrets["DART_API_KEY"]
KRX_API_KEY = st.secrets["KRX_API_KEY"]  # 현재 KRX는 API 키 사용 없이 작동하는 구조지만 추후 대비

# 공통 헤더
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://data.krx.co.kr",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# 코스피 + 코스닥 통합 기본정보
def get_krx_merged_basic_info(date):
    kospi_url = "https://data-dbg.krx.co.kr/svc/apis/sto/stk/stk_isu_base_info.json"
    kosdaq_url = "https://data-dbg.krx.co.kr/svc/apis/sto/ksq/ksq_isu_base_info.json"

    params = {"basDt": date}
    df_kospi = requests.get(kospi_url, params=params, headers=KRX_HEADERS).json().get("OutBlock_1", [])
    df_kosdaq = requests.get(kosdaq_url, params=params, headers=KRX_HEADERS).json().get("OutBlock_1", [])

    df_total = pd.DataFrame(df_kospi + df_kosdaq)
    return df_total

# 일별 시세
def get_krx_daily_trading_info(date):
    url = "https://data-dbg.krx.co.kr/svc/apis/sto/sto/stk_bydd_trd.json"
    params = {"basDt": date}
    df = requests.get(url, params=params, headers=KRX_HEADERS).json().get("OutBlock_1", [])
    return pd.DataFrame(df)

# 적정주가 계산식
def calculate_fair_price(eps, per_avg, peg_adj, growth_factor, roe_weight, revenue_growth_adj, stability_score):
    price = eps * (per_avg + peg_adj + growth_factor)
    price *= (roe_weight + revenue_growth_adj)
    price *= (stability_score / 100)
    return price

# 안정성 점수 계산
def estimate_stability_score(debt_ratio, current_ratio):
    score = 100 - (debt_ratio * 0.1) + (current_ratio * 0.05)
    return max(min(score, 100), 0)

# 스트림릿 인터페이스 시작
st.title("📊 KRX 연동 적정주가 계산기")

user_input = st.text_input("종목 코드(6자리) 또는 종목명 입력 (예: 005930 또는 삼성전자)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

if user_input:
    basic_info_df = get_krx_merged_basic_info(base_date)
    daily_info_df = get_krx_daily_trading_info(base_date)

    # 종목 검색
    target_info = basic_info_df[
        (basic_info_df["ISU_SRT_CD"] == user_input) |
        (basic_info_df["ISU_NM"] == user_input)
    ]

    if target_info.empty:
        st.error("입력한 종목의 정보를 찾을 수 없습니다.")
        st.stop()

    st.subheader("📄 종목 기본정보")
    st.dataframe(target_info)

    isu_cd = target_info.iloc[0]["ISU_CD"]
    isu_nm = target_info.iloc[0]["ISU_NM"]

    # 일별 시세 조회
    target_daily = daily_info_df[daily_info_df["ISU_CD"] == isu_cd]
    st.subheader("📈 일별 시세")
    st.dataframe(target_daily)

    try:
        current_price = int(target_daily.iloc[0]["TDD_CLSPRC"].replace(",", ""))
    except:
        st.warning("현재 주가 정보가 없습니다.")
        current_price = 0

    # 샘플 재무정보
    st.subheader("📑 재무정보 입력 또는 연동 예정")
    eps = st.number_input("EPS", value=5500)
    roe = st.number_input("ROE(%)", value=12.0)
    revenue_growth = st.number_input("매출성장률(%)", value=8.0)
    debt_ratio = st.number_input("부채비율(%)", value=80.0)
    current_ratio = st.number_input("유동비율(%)", value=130.0)

    # 계산 항목
    per_avg = 10
    peg_adj = 1.0
    growth_factor = revenue_growth / 10
    roe_weight = roe * 0.01
    revenue_growth_adj = revenue_growth * 0.01
    stability_score = estimate_stability_score(debt_ratio, current_ratio)

    st.subheader("🧮 계산 중간값")
    st.write(f"PER 평균: {per_avg}")
    st.write(f"PEG 조정치: {peg_adj}")
    st.write(f"성장가중치: {growth_factor}")
    st.write(f"ROE 보정계수: {roe_weight}")
    st.write(f"매출성장률 보정치: {revenue_growth_adj}")
    st.write(f"안정성 점수: {stability_score:.2f}")

    # 적정주가 계산
    fair_price = calculate_fair_price(
        eps, per_avg, peg_adj, growth_factor,
        roe_weight, revenue_growth_adj, stability_score
    )

    st.subheader("🎯 적정주가 결과")
    st.metric("적정주가", f"{fair_price:,.0f} 원")
    st.metric("현재 주가", f"{current_price:,.0f} 원")
    if current_price > 0:
        diff_pct = (fair_price - current_price) / current_price
        st.metric("프리미엄/할인율", f"{diff_pct:+.2%}")
