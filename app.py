import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

KRX_API_KEY = st.secrets["KRX_API_KEY"]

KOSPI_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"
KOSDAQ_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"

def fetch_krx_data(api_url, basDd):
    headers = {"AUTH_KEY": KRX_API_KEY}
    params = {"basDd": basDd}
    response = requests.get(api_url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    return pd.DataFrame(data.get("OutBlock_1", []))

def filter_common_stock(df):
    return df[df["KIND_STKCERT_TP_NM"] == "보통주"]

def search_stock(df, query):
    query = query.strip().upper()
    match = df[
        (df["ISU_SRT_CD"].str.upper() == query) |
        (df["ISU_NM"].str.contains(query, case=False))
    ]
    return match

st.title("📈 KRX 코스피/코스닥 보통주 종목 조회기")

yesterday = datetime.today() - timedelta(days=1)
base_date = st.date_input("기준일자", yesterday).strftime("%Y%m%d")
user_input = st.text_input("종목명 또는 종목코드 입력 (예: 삼성전자 또는 005930)")

if user_input:
    with st.spinner("KRX API에서 코스피/코스닥 데이터 조회 중..."):
        try:
            kospi_df = filter_common_stock(fetch_krx_data(KOSPI_API_URL, base_date))
            kosdaq_df = filter_common_stock(fetch_krx_data(KOSDAQ_API_URL, base_date))

            kospi_match = search_stock(kospi_df, user_input)
            kosdaq_match = search_stock(kosdaq_df, user_input)

            if not kospi_match.empty:
                row = kospi_match.iloc[0]
                st.success("✅ 코스피 보통주 종목 조회 성공")
                st.write(f"**시장:** 코스피")
                st.write(f"**종목명:** {row['ISU_NM']}")
                st.write(f"**종목코드:** {row['ISU_SRT_CD']}")
                st.write(f"**상장주식수:** {int(row['LIST_SHRS'].replace(',', '')):,} 주")
            elif not kosdaq_match.empty:
                row = kosdaq_match.iloc[0]
                st.success("✅ 코스닥 보통주 종목 조회 성공")
                st.write(f"**시장:** 코스닥")
                st.write(f"**종목명:** {row['ISU_NM']}")
                st.write(f"**종목코드:** {row['ISU_SRT_CD']}")
                st.write(f"**상장주식수:** {int(row['LIST_SHRS'].replace(',', '')):,} 주")
            else:
                st.warning("❌ 입력한 종목의 보통주를 찾을 수 없습니다.")
        except Exception as e:
            st.error(f"❌ 오류 발생: {e}")
