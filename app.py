import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# 인증키 (Streamlit secrets에 저장됨)
KRX_API_KEY = st.secrets["KRX_API_KEY"]

# API URL
KOSPI_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"
KOSDAQ_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"

# API 호출 함수
def fetch_krx_data(api_url, basDd):
    headers = {"AUTH_KEY": KRX_API_KEY}
    params = {"basDd": basDd}
    response = requests.get(api_url, headers=headers, params=params)
    response.raise_for_status()
    return pd.DataFrame(response.json().get("OutBlock_1", []))

# '보통주'만 필터링
def filter_common_stock(df):
    return df[df["KIND_STKCERT_TP_NM"] == "보통주"]

# '보통주' 텍스트 제거 함수
def clean_name(name: str) -> str:
    return name.replace("보통주", "").strip()

# 표시용 텍스트 생성
def make_display_label(row):
    name = clean_name(row["ISU_NM"])
    return f"{name} ({row['ISU_SRT_CD']})"

# Streamlit UI
st.title("📈 KRX 종목 실시간 검색기")

# 기준일자: 어제로 설정
yesterday = datetime.today() - timedelta(days=1)
base_date = st.date_input("기준일자", yesterday).strftime("%Y%m%d")

# 데이터 불러오기
with st.spinner("📡 보통주 전체 종목을 불러오는 중..."):
    try:
        kospi_df = filter_common_stock(fetch_krx_data(KOSPI_API_URL, base_date))
        kosdaq_df = filter_common_stock(fetch_krx_data(KOSDAQ_API_URL, base_date))
        all_df = pd.concat([kospi_df, kosdaq_df], ignore_index=True)
        all_df["ISU_NM_CLEAN"] = all_df["ISU_NM"].apply(clean_name)
        all_df["label"] = all_df.apply(make_display_label, axis=1)
    except Exception as e:
        st.error(f"❌ 데이터 불러오기 오류: {e}")
        st.stop()

# 검색형 선택창
selected_label = st.selectbox(
    "🔍 종목명을 검색하세요 (예: 삼성전자 또는 005930)",
    options=all_df["label"].tolist()
)

# 조회 결과 표시
if selected_label:
    selected_row = all_df[all_df["label"] == selected_label].iloc[0]
    st.success("✅ 종목 조회 결과")
    st.write(f"**시장구분:** {'코스피' if selected_row['MKT_TP_NM'] == 'KOSPI' else '코스닥'}")
    st.write(f"**종목명:** {selected_row['ISU_NM_CLEAN']}")
    st.write(f"**종목코드:** {selected_row['ISU_SRT_CD']}")
    st.write(f"**상장주식수:** {int(selected_row['LIST_SHRS'].replace(',', '')):,} 주")