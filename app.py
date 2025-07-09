import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- KRX, DART API 인증키 ---
KRX_API_KEY = st.secrets["KRX_API_KEY"]
DART_API_KEY = st.secrets["DART_API_KEY"]

# --- KRX API URLs ---
KOSPI_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"
KOSDAQ_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"

# --- DART API URLs ---
DART_FINANCIAL_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

# --- Helper Functions ---

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

# DART API: CorpCode.xml 다운로드 후 종목코드 -> DART 고유기업코드 변환 함수
import zipfile
import xml.etree.ElementTree as ET
import os

def get_corp_code_map():
    corp_code_zip = "corp_code.zip"
    corp_code_xml = "CORPCODE.xml"
    if not os.path.exists(corp_code_xml):
        url = f"https://opendart.fss.or.kr/api/corpCode.xml"
        params = {"crtfc_key": DART_API_KEY}
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml", params={"crtfc_key":DART_API_KEY})
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
        corp_name = corp.find("corp_name").text
        if stock_code:
            corp_map[stock_code] = corp_code
    return corp_map

# DART API: 재무제표 가져오기
def fetch_dart_financial_data(corp_code, year, reprt_code="11011"): 
    """
    reprt_code: 11011=사업보고서, 11012=반기보고서, 11013=분기보고서
    """
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": reprt_code,
        "fs_div": "CFS"  # 연결재무제표
    }
    resp = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json", params=params)
    data = resp.json()
    if data.get("status") != "000":
        st.warning(f"DART 재무 데이터 조회 실패: {data.get('message')}")
        return None
    return data.get("list", [])

def extract_financial_items(financial_list):
    # 재무 데이터에서 필요한 항목을 추출
    result = {}
    for item in financial_list:
        # item 예시: {'account_nm': '당기순이익(손실)', 'thstrm_amount': '123456'}
        key = item['account_nm'].strip()
        value = item['thstrm_amount']
        try:
            value = float(value.replace(',', ''))
        except:
            value = None
        result[key] = value
    return result

# 적정주가 계산 함수
def calculate_fair_price(eps, per_avg, peg_adj, growth_weight, roe_adj, sales_growth_adj, stability_score):
    base = eps * (per_avg + peg_adj + growth_weight)
    modifier = roe_adj + sales_growth_adj
    price = base * modifier * (stability_score / 100)
    return price

# --- Streamlit UI 시작 ---

st.title("📊 KRX + DART 기반 적정주가 계산기")

# 기준일자 설정
yesterday = datetime.today() - timedelta(days=1)
base_date = st.date_input("KRX 기준일자", yesterday).strftime("%Y%m%d")

# KRX 종목 데이터 로드
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

    # DART 기업코드 매핑
    corp_code_map = get_corp_code_map()
    stock_code = selected_row["ISU_SRT_CD"].lstrip('0')  # 주식코드는 앞 0 제거 필요
    corp_code = corp_code_map.get(stock_code)
    if not corp_code:
        st.error("DART 기업코드 매핑 실패 (상장코드와 DART 코드 불일치)")
        st.stop()

    # 사업보고서 기준 연도 설정 (작년)
    this_year = datetime.today().year
    last_year = this_year - 1

    financial_list = fetch_dart_financial_data(corp_code, last_year)
    if financial_list is None:
        st.error("DART 재무제표 데이터를 불러올 수 없습니다.")
        st.stop()

    fin_data = extract_financial_items(financial_list)

    # 주요 데이터 추출 (키 이름은 공시 양식마다 다르므로 케이스별 처리 필요)
    EPS = fin_data.get("지배주주귀속순이익(손실) / 주식수(보통주)","")
    if not EPS:
        EPS = fin_data.get("주당순이익(지배주주귀속)", None)
    if not EPS:
        EPS = fin_data.get("주당순이익", None)
    # ROE는 따로 계산하거나, 간접적으로 산출 가능
    ROE = fin_data.get("자기자본이익률(%)", None)
    # 매출액
    SALES = fin_data.get("매출액", None)

    # 임의로 사용자 입력받기 (PER 평균, PEG 조정치, 성장가중치, ROE 보정계수, 매출성장률 보정치, 안정성 점수)
    st.write("----")
    st.subheader("적정주가 계산에 필요한 입력값을 설정하세요")

    per_avg = st.number_input("PER 평균", min_value=0.0, value=10.0, step=0.1)
    peg_adj = st.number_input("PEG 조정치", value=0.0, step=0.1)
    growth_weight = st.number_input("성장가중치", value=0.0, step=0.1)
    roe_adj = st.number_input("ROE 보정계수", value=1.0, step=0.01)
    sales_growth_adj = st.number_input("매출성장률 보정치", value=0.0, step=0.01)
    stability_score = st.number_input("안정성 점수 (0~100)", min_value=0, max_value=100, value=80)

    # 화면에 불러온 재무 데이터 표시
    st.write("### DART 재무정보 (최근 사업보고서)")
    st.write(fin_data)

    if EPS is None or EPS == "":
        st.warning("EPS 데이터를 불러올 수 없습니다. 수동 입력하세요.")
        EPS = st.number_input("EPS (주당순이익)", value=0.0, step=0.01)
    else:
        st.write(f"EPS (주당순이익): {EPS}")

    if ROE is None:
        ROE = st.number_input("ROE (자기자본이익률 %)", value=0.0, step=0.01)
    else:
        st.write(f"ROE: {ROE}")

    if SALES is None:
        SALES = st.number_input("매출액 (단위: 백만원)", value=0.0, step=1.0)
    else:
        st.write(f"매출액: {SALES}")

    # 적정주가 계산 버튼
    if st.button("적정주가 계산"):
        try:
            EPS_val = float(EPS)
            fair_price = calculate_fair_price(
                EPS=EPS_val,
                per_avg=per_avg,
                peg_adj=peg_adj,
                growth_weight=growth_weight,
                roe_adj=roe_adj,
                sales_growth_adj=sales_growth_adj,
                stability_score=stability_score
            )
            st.success(f"✅ 계산된 적정주가: {fair_price:,.2f} 원")
        except Exception as e:
            st.error(f"계산 중 오류 발생: {e}")
