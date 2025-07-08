import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# KRX REST API endpoint (JSON 방식)
KRX_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info.json"

# 공통 헤더 (User-Agent 필수)
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://data.krx.co.kr",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# 종목 정보 조회 함수
def get_krx_stock_info(date: str) -> pd.DataFrame:
    params = {"basDt": date}
    res = requests.get(KRX_URL, params=params, headers=KRX_HEADERS)
    res.raise_for_status()
    json_data = res.json()
    return pd.DataFrame(json_data.get("OutBlock_1", []))

# 상장주식수 추출
def get_stock_data(df: pd.DataFrame, input_str: str) -> dict:
    input_str = input_str.strip().upper()
    match = df[
        (df["ISU_SRT_CD"].str.upper() == input_str) |
        (df["ISU_ABBRV"].str.contains(input_str, case=False)) |
        (df["ISU_NM"].str.contains(input_str, case=False))
    ]
    if match.empty:
        raise ValueError("❌ 입력한 종목을 찾을 수 없습니다.")
    row = match.iloc[0]
    return {
        "종목명": row["ISU_NM"],
        "종목코드": row["ISU_SRT_CD"],
        "상장주식수": int(row["LIST_SHRS"].replace(",", ""))
    }

# Streamlit UI
st.set_page_config(page_title="KRX 종목 조회기", layout="centered")
st.title("📈 실시간 KRX 종목코드 & 상장주식수 조회기")

user_input = st.text_input("종목명 또는 종목코드 입력 (예: 삼성전자 또는 005930)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

if user_input:
    with st.spinner("📡 실시간 데이터 로드 중..."):
        try:
            df = get_krx_stock_info(base_date)
            result = get_stock_data(df, user_input)
            st.success("✅ 조회 성공")
            st.write(f"**종목명**: {result['종목명']}")
            st.write(f"**종목코드**: {result['종목코드']}")
            st.write(f"**상장주식수**: {result['상장주식수']:,} 주")
        except Exception as e:
            st.error(f"❌ 오류 발생: {e}")
