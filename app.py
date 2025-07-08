import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# 공통 헤더 (KRX Open API용)
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://openapi.krx.co.kr",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

# OTP 발급 함수
def get_otp(bld: str, params: dict) -> str:
    url = "http://openapi.krx.co.kr/contents/COM/GenerateOTP.jspx"
    res = requests.get(url, params={"bld": bld, **params}, headers=KRX_HEADERS)
    res.raise_for_status()
    return res.text

# OTP로 실제 데이터 요청
def fetch_krx_data(otp: str) -> pd.DataFrame:
    url = "http://openapi.krx.co.kr/contents/COM/UniOutput.jspx"
    res = requests.post(url, data={"code": otp}, headers=KRX_HEADERS)
    res.raise_for_status()
    return pd.read_html(res.text)[0]

# 상장주식수 추출 함수
def get_listed_shares(df: pd.DataFrame, input_str: str) -> dict:
    input_str = input_str.strip().upper()
    match = df[
        (df["단축코드"].str.upper() == input_str) |
        (df["종목명"].str.contains(input_str, case=False))
    ]
    if match.empty:
        raise ValueError("❌ 입력한 종목을 찾을 수 없습니다.")
    row = match.iloc[0]
    return {
        "종목명": row["종목명"],
        "종목코드": row["단축코드"],
        "상장주식수": int(row["상장주식수"].replace(",", ""))
    }

# Streamlit 앱 시작
st.set_page_config(page_title="KRX 종목 조회기", layout="centered")
st.title("📈 KRX 종목코드 & 상장주식수 조회기")

# 입력 항목
user_input = st.text_input("종목명 또는 종목코드를 입력하세요 (예: 삼성전자 또는 005930)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

# 실행
if user_input:
    with st.spinner("📡 KRX Open API에서 데이터 불러오는 중..."):
        try:
            # 코스피 + 코스닥 전체 데이터 불러오기
            otp_kospi = get_otp("MKD/13/1301/13010101/mkd13010101", {"basDt": base_date})
            df_kospi = fetch_krx_data(otp_kospi)

            otp_kosdaq = get_otp("MKD/13/1301/13010201/mkd13010201", {"basDt": base_date})
            df_kosdaq = fetch_krx_data(otp_kosdaq)

            all_stocks = pd.concat([df_kospi, df_kosdaq], ignore_index=True)

            result = get_listed_shares(all_stocks, user_input)

            # 결과 출력
            st.success("✅ 조회 완료")
            st.write(f"**종목명**: {result['종목명']}")
            st.write(f"**종목코드**: {result['종목코드']}")
            st.write(f"**상장주식수**: {result['상장주식수']:,} 주")

        except Exception as e:
            st.error(str(e))
