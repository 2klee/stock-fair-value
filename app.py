import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import zipfile
import xml.etree.ElementTree as ET
import os

# --- KRX, DART API 인증키 (Streamlit secrets에서 불러오기) ---
KRX_API_KEY = st.secrets["KRX_API_KEY"]
DART_API_KEY = st.secrets["DART_API_KEY"]

# --- KRX API URLs ---
KOSPI_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"
KOSDAQ_API_URL = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"

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

# --- DART 기업코드 매핑 함수 ---
def get_corp_code_map():
    corp_code_zip = "corp_code.zip"
    corp_code_xml = "CORPCODE.xml"
    # DART 공시기업코드 XML 파일 없으면 다운로드 및 압축 해제
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
        # stock_code가 빈 문자열 아닌 경우만 매핑
        if stock_code and stock_code.strip() != "":
            corp_map[stock_code] = corp_code
    return corp_map

# --- DART 재무제표 조회 함수 ---
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

# --- 적정주가 계산 함수 ---
def calculate_fair_price(eps, per_avg, peg_adj, growth_weight, roe_adj, sales_growth_adj, stability_score):
    base = eps * (per_avg + peg_adj + growth_weight)
    modifier = roe_adj + sales_growth_adj
    price = base * modifier * (stability_score / 100)
    return price

# --- Streamlit UI ---

st.title("📊 KRX + DART 기반 적정주가 계산기")

# 기준일자
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

    # 1차: 6자리 그대로 매핑 시도
    corp_code = corp_code_map.get(stock_code)

    # 2차: 앞자리 0 제거 후 매핑 시도
    if corp_code is None:
        stock_code_trim = stock_code.lstrip("0")
        corp_code = corp_code_map.get(stock_code_trim)

    if corp_code is None:
        st.error(f"DART 기업코드 매핑 실패: KRX 종목코드 '{stock_code}'가 DART DB에 없습니다.\n수동으로 EPS 등을 입력해주세요.")
        EPS = st.number_input("EPS (주당순이익)", value=0.0, step=0.01)
        per_avg = st.number_input("PER 평균", min_value=0.0, value=10.0, step=0.1)
        peg_adj = st.number_input("PEG 조정치", value=0.0, step=0.1)
        growth_weight = st.number_input("성장가중치", value=0.0, step=0.1)
        roe_adj = st.number_input("ROE 보정계수", value=1.0, step=0.01)
        sales_growth_adj = st.number_input("매출성장률 보정치", value=0.0, step=0.01)
        stability_score = st.number_input("안정성 점수 (0~100)", min_value=0, max_value=100, value=80)

        if st.button("적정주가 계산 (수동입력)"):
            try:
                fair_price = calculate_fair_price(
                    EPS, per_avg, peg_adj, growth_weight, roe_adj, sales_growth_adj, stability_score
                )
                st.success(f"✅ 계산된 적정주가: {fair_price:,.2f} 원")
            except Exception as e:
                st.error(f"계산 중 오류 발생: {e}")
        st.stop()

    this_year = datetime.today().year
    last_year = this_year - 1

    financial_list = fetch_dart_financial_data(corp_code, last_year)
    if financial_list is None:
        st.error("DART 재무제표 데이터를 불러올 수 없습니다.")
        st.stop()

    fin_data = extract_financial_items(financial_list)

    # 적정주가 계산식에 필요한 핵심 데이터만 표시
    EPS = fin_data.get("지배주주귀속순이익(손실) / 주식수(보통주)")
    if EPS is None:
        EPS = fin_data.get("주당순이익(지배주주귀속)")
    if EPS is None:
        EPS = fin_data.get("주당순이익")

    ROE = fin_data.get("자기자본이익률(%)")
    SALES = fin_data.get("매출액")

    st.write("### DART 재무정보 (적정주가 계산용)")

    if EPS is not None:
        st.write(f"- EPS (주당순이익): {EPS}")
    else:
        EPS = st.number_input("EPS (주당순이익)", value=0.0, step=0.01)

    if ROE is not None:
        st.write(f"- ROE (자기자본이익률 %): {ROE}")
    else:
        ROE = st.number_input("ROE (자기자본이익률 %)", value=0.0, step=0.01)

    if SALES is not None:
        st.write(f"- 매출액 (백만원): {SALES}")
    else:
        SALES = st.number_input("매출액 (단위: 백만원)", value=0.0, step=1.0)

    # 계산식 파라미터 입력 UI
    st.write("----")
    st.subheader("적정주가 계산을 위한 입력값을 설정하세요")

    per_avg = st.number_input("PER 평균", min_value=0.0, value=10.0, step=0.1)
    peg_adj = st.number_input("PEG 조정치", value=0.0, step=0.1)
    growth_weight = st.number_input("성장가중치", value=0.0, step=0.1)
    roe_adj = st.number_input("ROE 보정계수", value=1.0, step=0.01)
    sales_growth_adj = st.number_input("매출성장률 보정치", value=0.0, step=0.01)
    stability_score = st.number_input("안정성 점수 (0~100)", min_value=0, max_value=100, value=80)

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
