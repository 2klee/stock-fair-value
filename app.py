import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# 인증키 (streamlit secrets에 저장)
KRX_API_KEY = st.secrets["KRX_API_KEY"]

API_URL = "https://openapi.krx.co.kr/svc/sample/apis/sto/stk_isu_base_info"

def get_krx_stock_info(basDd):
    headers = {
        "AUTH_KEY": KRX_API_KEY
    }
    params = {
        "basDd": basDd
    }
    response = requests.get(API_URL, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    return pd.DataFrame(data.get("OutBlock_1", []))

def search_stock(df, query):
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
st.title("📈 KRX 공식 OpenAPI 종목 조회기")

user_input = st.text_input("종목명 또는 종목코드 입력 (예: 삼성전자 또는 005930)")
base_date = st.date_input("기준일자", datetime.today()).strftime("%Y%m%d")

if user_input:
    with st.spinner("KRX OpenAPI에서 데이터 조회 중..."):
        try:
            df = get_krx_stock_info(base_date)
            result = search_stock(df, user_input)
            st.success("✅ 조회 성공")
            st.write(f"**종목명:** {result['종목명']}")
            st.write(f"**종목코드:** {result['종목코드']}")
            st.write(f"**상장주식수:** {result['상장주식수']:,} 주")
        except Exception as e:
            st.error(f"❌ 오류 발생: {e}")
