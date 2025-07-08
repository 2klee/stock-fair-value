import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# 🔑 KRX Open API 인증키
KRX_API_KEY = st.secrets["KRX_API_KEY"]

# API 요청 함수 (예: 상장종목 검색 API)
def get_krx_stock_list(base_date):
    url = "https://open.krx.co.kr/contents/MDC/99/MDC99000001.jspx"
    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
        "mktId": "ALL",
        "share": "1",
        "csvxls_isNo": "false",
        "authKey": KRX_API_KEY,
        "basDd": base_date  # 날짜 파라미터는 basDd로 설정
    }
    res = requests.post(url, data=payload)
    res.raise_for_status()
    json_data = res.json()
    return pd.DataFrame(json_data.get("OutBlock_1", []))

# 종목 필터링 함수
def search_stock(df: pd.DataFrame, query: str) -> dict:
    query = query.strip().upper()
    match = df[
        (df["ISU_SRT_CD"].str.upper() == query) |
        (df["ISU_NM"].str.contains(query, case=False))
    ]
    if match.empty:
        raise ValueError("해당 종목을 찾을 수 없습니다.")
    row = match.iloc[0]
    return {
        "종목명": row["ISU_NM"],
        "종목코드": row["ISU_SRT_CD"],
        "상장주식수": int(row["LIST_SHRS"].replace(",", ""))
    }

# Streamlit UI
st.set_page_config(page_title="KRX 종목 조회기", layout="centered")
st.title("📈 KRX Open API 기반 종목 정보 조회")

user_input = st.text_input("종목명 또는 종목코드 입력 (예: 삼성전자 또는 005930)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

if user_input:
    with st.spinner("📡 KRX Open API에서 데이터 조회 중..."):
        try:
            stock_df = get_krx_stock_list(base_date)
            result = search_stock(stock_df, user_input)
            st.success("✅ 조회 성공")
            st.write(f"**종목명**: {result['종목명']}")
            st.write(f"**종목코드**: {result['종목코드']}")
            st.write(f"**상장주식수**: {result['상장주식수']:,} 주")
        except Exception as e:
            st.error(f"❌ 오류: {e}")
