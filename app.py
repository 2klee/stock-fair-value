import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# API 키 (필요 시 대비)
DART_API_KEY = st.secrets["DART_API_KEY"]
KRX_API_KEY = st.secrets["KRX_API_KEY"]

# KRX 헤더 설정
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://data.krx.co.kr",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# 코스피 + 코스닥 종목 기본정보 가져오기
def get_krx_merged_basic_info(date):
    kospi_url = "https://data-dbg.krx.co.kr/svc/apis/sto/stk/stk_isu_base_info.json"
    kosdaq_url = "https://data-dbg.krx.co.kr/svc/apis/sto/ksq/ksq_isu_base_info.json"
    params = {"basDd": date}

    try:
        kospi_data = requests.get(kospi_url, params=params, headers=KRX_HEADERS).json().get("OutBlock_1", [])
        kosdaq_data = requests.get(kosdaq_url, params=params, headers=KRX_HEADERS).json().get("OutBlock_1", [])
        df_total = pd.DataFrame(kospi_data + kosdaq_data)
        return df_total
    except Exception as e:
        st.error(f"KRX 종목 기본정보 호출 오류: {e}")
        return pd.DataFrame()

# 일별 시세 가져오기
def get_krx_daily_trading_info(date):
    url = "https://data-dbg.krx.co.kr/svc/apis/sto/sto/stk_bydd_trd.json"
    params = {"basDd": date}

    try:
        data = requests.get(url, params=params, headers=KRX_HEADERS).json().get("OutBlock_1", [])
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"KRX 일별 시세 호출 오류: {e}")
        return pd.DataFrame()

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

# 🟩 Streamlit UI 시작
st.set_page_config(page_title="적정주가 계산기", layout="centered")
st.title("📈 KRX 연동 적정주가 계산기")

# 날짜 및 입력
user_input = st.text_input("종목명 또는 종목코드 입력 (예: 삼성전자 또는 005930)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

if user_input:
    with st.spinner("🔄 KRX 데이터 불러오는 중..."):
        basic_info_df = get_krx_merged_basic_info(base_date)
        daily_info_df = get_krx_daily_trading_info(base_date)

    if basic_info_df.empty or daily_info_df.empty:
        st.error("📉 KRX 데이터를 불러오지 못했습니다.")
        st.stop()

    # 종목명/코드 모두 대응
    user_input = user_input.strip()
    matched = basic_info_df[
        (basic_info_df["ISU_SRT_CD"].str.upper() == user_input.upper()) |
        (basic_info_df["ISU_NM"] == user_input)
    ]

    if matched.empty:
        st.warning("❌ 해당 종목을 찾을 수 없습니다.")
        st.dataframe(basic_info_df[["ISU_NM", "ISU_SRT_CD"]].head(10))
        st.stop()

    # 종목 정보 추출
    row = matched.iloc[0]
    isu_cd = row["ISU_CD"]
    isu_nm = row["ISU_NM"]
    isu_srt_cd = row["ISU_SRT_CD"]

    st.markdown(f"### 📌 선택한 종목: **{isu_nm} ({isu_srt_cd})**")

    st.subheader("📄 종목 기본정보")
    st.dataframe(matched)

    # 시세 정보 출력
    target_daily = daily_info_df[daily_info_df["ISU_CD"] == isu_cd]
    st.subheader("📈 일별 시세 정보")
    st.dataframe(target_daily)

    try:
        current_price = int(target_daily.iloc[0]["TDD_CLSPRC"].replace(",", ""))
    except:
        st.warning("현재가 정보가 없습니다.")
        current_price = 0

    # 재무정보 입력
    st.subheader("📑 재무정보 입력")
    eps = st.number_input("EPS (원)", value=5500.0)
    roe = st.number_input("ROE (%)", value=12.0)
    revenue_growth = st.number_input("매출 성장률 (%)", value=8.0)
    debt_ratio = st.number_input("부채비율 (%)", value=80.0)
    current_ratio = st.number_input("유동비율 (%)", value=130.0)

    # 계산
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

    fair_price = calculate_fair_price(
        eps, per_avg, peg_adj, growth_factor,
        roe_weight, revenue_growth_adj, stability_score
    )

    st.subheader("🎯 적정주가 계산 결과")
    st.metric("적정주가", f"{fair_price:,.0f} 원")
    st.metric("현재 주가", f"{current_price:,.0f} 원")
    if current_price > 0:
        diff_pct = (fair_price - current_price) / current_price
        st.metric("프리미엄/할인율", f"{diff_pct:+.2%}")
