import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import zipfile
import xml.etree.ElementTree as ET
import os

# --- API 인증키 ---
KRX_API_KEY = st.secrets["KRX_API_KEY"]
DART_API_KEY = st.secrets["DART_API_KEY"]

# --- KRX API URLs ---
KOSPI_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"
KOSDAQ_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"

# --- 헬퍼 함수들 ---
def fetch_krx_data(api_url, basDd):
    headers = {"AUTH_KEY": KRX_API_KEY}
    params = {"basDd": basDd}
    response = requests.get(api_url, headers=headers, params=params)
    response.raise_for_status()
    return pd.DataFrame(response.json().get("OutBlock_1", []))

def filter_common_stock(df):
    return df[df["KIND_STKCERT_TP_NM"] == "보통주"]

def clean_name(name: str) -> str:
    return name.replace("보통주", "").strip()

def make_display_label(row):
    name = clean_name(row["ISU_NM"])
    return f"{name} ({row['ISU_SRT_CD']})"

def get_corp_code_map():
    corp_code_zip = "corp_code.zip"
    corp_code_xml = "CORPCODE.xml"
    if not os.path.exists(corp_code_xml):
        r = requests.get(f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_API_KEY}")
        with open(corp_code_zip, "wb") as f:
            f.write(r.content)
        with zipfile.ZipFile(corp_code_zip, 'r') as zip_ref:
            zip_ref.extractall()
    tree = ET.parse(corp_code_xml)
    root = tree.getroot()
    corp_map = {}
    for corp in root.findall("list"):
        corp_code = corp.find("corp_code").text
        stock_code = corp.find("stock_code").text
        if stock_code and stock_code.strip() != "":
            corp_map[stock_code] = corp_code
    return corp_map

def fetch_dart_financial_data(corp_code):
    current_year = datetime.today().year
    for year in range(current_year, current_year - 5, -1):
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",
            "fs_div": "CFS"
        }
        resp = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json", params=params)
        data = resp.json()
        if data.get("status") == "000":
            return data.get("list", []), year
    return None, None

def extract_amount(item):
    value = item.get("thstrm_amount", "")
    try:
        return int(value.replace(',', '')) if value else None
    except:
        return None

def calculate_growth_rate(current, previous):
    try:
        return round((current - previous) / previous, 4) if previous else 0
    except:
        return 0

# --- Streamlit UI ---
st.title("📊 KRX + DART 적정주가 계산기")

yesterday = datetime.today() - timedelta(days=1)
base_date = st.date_input("KRX 기준일자", yesterday).strftime("%Y%m%d")

with st.spinner("KRX 보통주 종목 불러오는 중..."):
    try:
        kospi_df = filter_common_stock(fetch_krx_data(KOSPI_API_URL, base_date))
        kosdaq_df = filter_common_stock(fetch_krx_data(KOSDAQ_API_URL, base_date))
        all_df = pd.concat([kospi_df, kosdaq_df], ignore_index=True)
        all_df["ISU_NM_CLEAN"] = all_df["ISU_NM"].apply(clean_name)
        all_df["label"] = all_df.apply(make_display_label, axis=1)
    except Exception as e:
        st.error(f"KRX 데이터 로드 오류: {e}")
        st.stop()

selected_label = st.selectbox("종목 선택", options=all_df["label"].tolist())

if selected_label:
    selected_row = all_df[all_df["label"] == selected_label].iloc[0]
    stock_code = selected_row["ISU_SRT_CD"]
    st.write(f"### 선택 종목: {selected_row['ISU_NM_CLEAN']} ({stock_code})")
    st.write(f"시장구분: {'코스피' if selected_row['MKT_TP_NM']=='KOSPI' else '코스닥'}")
    try:
        shares_outstanding = int(selected_row['LIST_SHRS'].replace(',', ''))
        st.write(f"상장주식수: {shares_outstanding:,} 주")
    except:
        shares_outstanding = None
        st.warning("상장주식수 정보 없음")

    corp_code_map = get_corp_code_map()
    corp_code = corp_code_map.get(stock_code) or corp_code_map.get(stock_code.lstrip("0"))

    if corp_code is None:
        st.error(f"DART 기업코드 매핑 실패: 종목코드 '{stock_code}'가 DART DB에 없습니다.")
        st.stop()

    st.write(f"DART 기업코드: {corp_code}")

    fin_list, used_year = fetch_dart_financial_data(corp_code)
    if fin_list is None:
        st.error("최근 연도 재무데이터를 불러올 수 없습니다.")
        st.stop()

    net_income, equity, revenue, revenue_prev = None, None, None, None
    for item in fin_list:
        name = item.get("account_nm", "")
        aid = item.get("account_id", "")
        sj_div = item.get("sj_div", "")
        if sj_div == "CIS" and aid == "ifrs-full_ProfitLoss" and "당기순이익" in name and "비지배" not in name:
            net_income = extract_amount(item)
        if name.strip() == "자본총계":
            equity = extract_amount(item)
        if name.strip() == "매출액":
            revenue = extract_amount(item)
            revenue_prev = extract_amount({"thstrm_amount": item.get("frmtrm_amount")})

    eps = net_income / shares_outstanding if net_income and shares_outstanding else None
    roe = net_income / equity if net_income and equity else None
    sales_growth = calculate_growth_rate(revenue, revenue_prev)

    st.write("### 자동 계산된 재무 지표")
    st.write(f"- EPS: {eps:.2f} 원" if eps else "- EPS: 계산 불가")
    st.write(f"- ROE: {roe*100:.2f}%" if roe else "- ROE: 계산 불가")
    st.write(f"- 매출성장률: {sales_growth*100:.2f}%" if sales_growth else "- 매출성장률: 계산 불가")

    st.write("### 사용자 입력 (수정 가능)")
    per = st.number_input("PER 평균", value=12.0)
    peg_adj = st.number_input("PEG 조정치", value=0.8)
    growth_weight = st.number_input("성장가중치", value=1.1)
    roe_adj = st.number_input("ROE 보정계수", value=1.0)
    stability_score = st.slider("안정성 점수 (0~100)", 0, 100, 80)

    if eps and roe:
        fair_price = (
            eps * (per + peg_adj + growth_weight)
            * (roe_adj + sales_growth)
            * (stability_score / 100)
        )
        st.write(f"### 📈 적정주가: {fair_price:,.2f} 원")
    else:
        st.warning("EPS 또는 ROE 계산이 불가능하여 적정주가를 계산할 수 없습니다.")
