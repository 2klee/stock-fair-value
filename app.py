import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# 인증키 (Streamlit secrets에 저장했다고 가정)
KRX_API_KEY = st.secrets["KRX_API_KEY"]

API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"

def get_krx_stock_info(basDd):
    headers = {
        "AUTH_KEY": KRX_API_KEY  # 인증키를 헤더에 넣기
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
st.title("📈 KRX API - 종목 조회기 (data-dbg.krx.co.kr)")

# 어제 날짜 계산
yesterday = datetime.today() - timedelta(days=1)

# 기준일자 입력 (기본값 어제)
base_date = st.date_input("기준일자", yesterday).strftime("%Y%m%d")
user_input = st.text_input("종목명 또는 종목코드 입력 (예: 삼성전자 또는 005930)")

if user_input:
    with st.spinner("KRX API에서 데이터 조회 중..."):
        try:
            df = get_krx_stock_info(base_date)
            result = search_stock(df, user_input)
            st.success("✅ 조회 성공")
            st.write(f"**종목명:** {result['종목명']}")
            st.write(f"**종목코드:** {result['종목코드']}")
            st.write(f"**상장주식수:** {result['상장주식수']:,} 주")
        except Exception as e:
            st.error(f"❌ 오류 발생: {e}")
