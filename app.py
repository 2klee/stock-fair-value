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

def fetch_dart_financial_data(corp_code, year, reprt_code="11011"):
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": reprt_code,
        "fs_div": "CFS"
    }
    resp = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json", params=params)
    data = resp.json()
    if data.get("status") != "000":
        st.warning(f"DART 재무 데이터 조회 실패: {data.get('message')}")
        return None
    return data.get("list", [])

def extract_financial_items(financial_list):
    result = {}
    for item in financial_list:
        key = item['account_nm'].strip()
        value = item['thstrm_amount']
        try:
            value = float(value.replace(',', ''))
        except:
            value = None
        result[key] = value
    return result

def find_financial_value(fin_map, keyword, exact_match=False):
    for key, val in fin_map.items():
        if exact_match:
            if keyword == key and val is not None:
                return val
        else:
            if keyword in key and val is not None:
                return val
    return None

# --- Streamlit UI ---
st.title("📊 KRX + DART 기반 재무정보 확인기")

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
    st.write(f"### 선택 종목: {selected_row['ISU_NM_CLEAN']} ({selected_row['ISU_SRT_CD']})")
    st.write(f"시장구분: {'코스피' if selected_row['MKT_TP_NM']=='KOSPI' else '코스닥'}")

    corp_code_map = get_corp_code_map()
    stock_code = selected_row["ISU_SRT_CD"]
    corp_code = corp_code_map.get(stock_code) or corp_code_map.get(stock_code.lstrip("0"))

    if corp_code is None:
        st.error(f"DART 기업코드 매핑 실패: 종목코드 '{stock_code}'가 DART DB에 없습니다.")
        st.stop()

    this_year = datetime.today().year
    last_year = this_year - 1

    fin_list_last = fetch_dart_financial_data(corp_code, last_year, reprt_code="11011")

    if fin_list_last is None:
        st.error(f"{last_year}년 사업보고서를 불러올 수 없습니다.")
        st.stop()

    fin_map_last = extract_financial_items(fin_list_last)

    net_income = (
        find_financial_value(fin_map_last, "지배주주귀속순이익", exact_match=True)
        or find_financial_value(fin_map_last, "당기순이익", exact_match=True)
    )

    st.write("### 재무정보")
    st.write(f"- {last_year}년 당기순이익: {net_income if net_income is not None else '데이터 없음'} 원")
