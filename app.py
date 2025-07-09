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

def extract_financial_items(financial_list):
    result = {}
    for item in financial_list:
        key = item['account_nm'].strip()
        value = item['thstrm_amount']
        try:
            if value is None or value.strip() == "":
                value = None
            else:
                value = int(value.replace(',', ''))
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
    st.write(f"상장주식수: {int(selected_row['LIST_SHRS'].replace(',', '')):,} 주")

    corp_code_map = get_corp_code_map()
    stock_code = selected_row["ISU_SRT_CD"]
    corp_code = corp_code_map.get(stock_code) or corp_code_map.get(stock_code.lstrip("0"))

    if corp_code is None:
        st.error(f"DART 기업코드 매핑 실패: 종목코드 '{stock_code}'가 DART DB에 없습니다.")
        st.stop()

    st.write(f"DART 기업코드: {corp_code}")

    fin_list, used_year = fetch_dart_financial_data(corp_code)

    if fin_list is None:
        st.error("최근 연도 재무데이터를 불러올 수 없습니다.")
        st.stop()

    fin_map = extract_financial_items(fin_list)

    net_income = None
    for keyword in ["지배주주귀속순이익", "당기순이익", "ProfitLoss", "순이익"]:
        net_income = find_financial_value(fin_map, keyword, exact_match=False)
        if net_income is not None:
            break

    st.write("### 재무정보")
    if net_income is None:
        st.write("- 최근 당기순이익: 데이터 없음")
    elif net_income == 0:
        st.write("- 최근 당기순이익: 0 (미제공 또는 미기입 가능성 있음)")
    else:
        st.write(f"- 최근 ({used_year}년) 당기순이익: {int(net_income):,} 원")
