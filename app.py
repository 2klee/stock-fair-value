# fair_price_app.py
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# DART API Key (Streamlit secrets)
DART_API_KEY = st.secrets["DART_API_KEY"]
# KRX Open API 키 (현재 직접 사용하진 않지만, 필요시 참조용)
KRX_API_KEY = st.secrets["KRX_API_KEY"]

# 공통 헤더 (KRX Open API는 Referer 검사)
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://openapi.krx.co.kr",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

# 1) OTP 생성 함수
def _get_otp(bld, extra_params):
    """
    bld: OTP 용 빌드코드 (예: 'MKD/13/1301/13010101/mkd13010101')
    extra_params: basDt, mktId 등 bld별 추가 파라미터 dict
    """
    url = "http://openapi.krx.co.kr/contents/COM/GenerateOTP.jspx"
    params = {"bld": bld, **extra_params}
    res = requests.get(url, params=params, headers=KRX_HEADERS, timeout=10)
    res.raise_for_status()
    return res.text

# 2) OTP로 데이터 가져오기 (HTML 테이블 → DataFrame)
def _fetch_with_otp(otp):
    url = "http://openapi.krx.co.kr/contents/COM/UniOutput.jspx"
    # UniOutput.jspx 에는 otp 코드만 POST
    res = requests.post(url, data={"code": otp}, headers=KRX_HEADERS, timeout=10)
    res.raise_for_status()
    # 스트리밍된 HTML 테이블을 DataFrame 으로 변환
    return pd.read_html(res.text, header=0)[0]

# 3) 종목 기본정보 (코스피+코스닥 통합)
def get_krx_basic_info_openapi(date):
    # 코스피
    otp_kospi = _get_otp(
        bld="MKD/13/1301/13010101/mkd13010101",
        extra_params={"mktId": "STK", "basDt": date, "share": "1", "money": "1", "csvxls_isNo": "false"},
    )
    df_kospi = _fetch_with_otp(otp_kospi)

    # 코스닥
    otp_kosdaq = _get_otp(
        bld="MKD/13/1301/13010201/mkd13010201",
        extra_params={"mktId": "KSQ", "basDt": date, "share": "1", "money": "1", "csvxls_isNo": "false"},
    )
    df_kosdaq = _fetch_with_otp(otp_kosdaq)

    return pd.concat([df_kospi, df_kosdaq], ignore_index=True)

# 4) 일별 시세 정보
def get_krx_daily_info_openapi(date):
    otp = _get_otp(
        bld="MKD/04/0406/04060101/mkd04060101",
        extra_params={"basDt": date, "share": "1", "money": "1", "csvxls_isNo": "false"},
    )
    return _fetch_with_otp(otp)

# =============== 적정주가 계산 함수들 (이전과 동일) ===============
def calculate_fair_price(eps, per_avg, peg_adj, growth_factor, roe_weight, revenue_growth_adj, stability_score):
    price = eps * (per_avg + peg_adj + growth_factor)
    price *= (roe_weight + revenue_growth_adj)
    price *= (stability_score / 100)
    return price

def estimate_stability_score(debt_ratio, current_ratio):
    score = 100 - (debt_ratio * 0.1) + (current_ratio * 0.05)
    return max(min(score, 100), 0)

# =============== Streamlit UI ===============
st.set_page_config(page_title="KRX Open API 적정주가 계산기", layout="centered")
st.title("📈 KRX Open API 연동 적정주가 계산기")

# 사용자 입력
user_input = st.text_input("종목명 또는 종목코드 입력 (예: 삼성전자 또는 005930)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

if user_input:
    with st.spinner("🔄 KRX Open API로 데이터 불러오는 중..."):
        basic_df = get_krx_basic_info_openapi(base_date)
        daily_df = get_krx_daily_info_openapi(base_date)

    if basic_df.empty or daily_df.empty:
        st.error("KRX 데이터 로드에 실패했습니다. 나중에 다시 시도해주세요.")
        st.stop()

    # 종목명/코드 양방향 매핑
    user_in = user_input.strip()
    match = basic_df[
        (basic_df["단축코드"].str.upper() == user_in.upper()) |
        (basic_df["종목명"] == user_in)
    ]

    if match.empty:
        st.warning("해당 종목을 찾을 수 없습니다.")
        st.dataframe(basic_df[["종목명", "단축코드"]].head(10))
        st.stop()

    row = match.iloc[0]
    isu_srt_cd = row["단축코드"]
    isu_nm     = row["종목명"]
    isu_cd     = row["종목코드"]  # 내부 ISU_CD

    st.markdown(f"### 🔍 선택된 종목: **{isu_nm} ({isu_srt_cd})**")
    st.subheader("📄 종목 기본정보")
    st.dataframe(match)

    st.subheader("📈 일별 시세 정보")
    trade = daily_df[daily_df["종목코드"] == isu_cd]
    st.dataframe(trade)

    try:
        curr = int(trade.iloc[0]["현재가"].replace(",", ""))
    except:
        curr = 0
        st.warning("현재가를 가져올 수 없습니다.")

    # — 재무정보 수동 입력 —
    st.subheader("📑 재무정보 입력")
    eps = st.number_input("EPS (원)", value=5500.0)
    roe = st.number_input("ROE (%)", value=12.0)
    rev_growth = st.number_input("매출 성장률 (%)", value=8.0)
    debt = st.number_input("부채비율 (%)", value=80.0)
    curr_ratio = st.number_input("유동비율 (%)", value=130.0)

    # — 중간 계산 —
    per_avg = 10
    peg_adj = 1.0
    growth_factor = rev_growth / 10
    roe_w = roe * 0.01
    rev_adj = rev_growth * 0.01
    stability = estimate_stability_score(debt, curr_ratio)

    st.subheader("🧮 계산 중간값")
    st.write(f"PER 평균: {per_avg}")
    st.write(f"PEG 조정치: {peg_adj}")
    st.write(f"성장가중치: {growth_factor:.2f}")
    st.write(f"ROE 보정계수: {roe_w:.2f}")
    st.write(f"매출성장률 보정치: {rev_adj:.2f}")
    st.write(f"안정성 점수: {stability:.2f}")

    # — 최종 적정주가 —
    fair_price = calculate_fair_price(eps, per_avg, peg_adj, growth_factor, roe_w, rev_adj, stability)

    st.subheader("🎯 적정주가 결과")
    st.metric("적정주가", f"{fair_price:,.0f} 원")
    st.metric("현재 주가", f"{curr:,.0f} 원")
    if curr > 0:
        st.metric("프리미엄/할인율", f"{(fair_price - curr) / curr:+.2%}")
