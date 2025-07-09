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

def calculate_fair_price(eps, per_avg, peg_adj, growth_weight, roe_adj, sales_growth_adj, stability_score):
    base = eps * (per_avg + peg_adj + growth_weight)
    modifier = roe_adj + sales_growth_adj
    price = base * modifier * (stability_score / 100)
    return price

# --- 자동 계산용 함수 ---

def calculate_eps(fin_map, stock_shares):
    net_income = fin_map.get("지배주주귀속순이익(손실)")
    if net_income is None:
        net_income = fin_map.get("당기순이익")
    if net_income is None or stock_shares == 0:
        return None
    return net_income / stock_shares

def calculate_roe(fin_map):
    roe = fin_map.get("자기자본이익률(%)")
    if roe is not None:
        return roe
    net_income = fin_map.get("당기순이익")
    equity = fin_map.get("자본총계")
    if net_income is None or equity is None or equity == 0:
        return None
    return (net_income / equity) * 100

def calculate_sales_growth(fin_map_last, fin_map_prev):
    sales_last = fin_map_last.get("매출액")
    sales_prev = fin_map_prev.get("매출액")
    if sales_last is None or sales_prev is None or sales_prev == 0:
        return 0.0
    return (sales_last - sales_prev) / sales_prev * 100

# --- Streamlit UI ---

st.title("📊 KRX + DART 기반 적정주가 계산기")

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
    stock_shares = int(selected_row['LIST_SHRS'].replace(',', ''))
    st.write(f"상장주식수: {stock_shares:,} 주")

    corp_code_map = get_corp_code_map()
    stock_code = selected_row["ISU_SRT_CD"]

    corp_code = corp_code_map.get(stock_code)
    if corp_code is None:
        corp_code = corp_code_map.get(stock_code.lstrip("0"))

    if corp_code is None:
        st.error(f"DART 기업코드 매핑 실패: KRX 종목코드 '{stock_code}'가 DART DB에 없습니다.\n수동으로 입력하세요.")
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

    fin_list_last = fetch_dart_financial_data(corp_code, last_year)
    fin_list_prev = fetch_dart_financial_data(corp_code, last_year - 1)

    if fin_list_last is None:
        st.error("재무데이터(최근년도)를 불러올 수 없습니다.")
        st.stop()

    fin_map_last = extract_financial_items(fin_list_last)
    fin_map_prev = extract_financial_items(fin_list_prev) if fin_list_prev else {}

    EPS = calculate_eps(fin_map_last, stock_shares)
    ROE = calculate_roe(fin_map_last)
    sales_growth = calculate_sales_growth(fin_map_last, fin_map_prev)

    st.write("### 자동 계산된 재무정보")
    st.write(f"- EPS (주당순이익): {EPS if EPS is not None else '데이터 없음'}")
    st.write(f"- ROE (자기자본이익률 %): {ROE if ROE is not None else '데이터 없음'}")
    st.write(f"- 매출 성장률 (%): {sales_growth:.2f}")

    if EPS is None:
        EPS = st.number_input("EPS (주당순이익)", value=0.0, step=0.01)
    if ROE is None:
        ROE = st.number_input("ROE (자기자본이익률 %)", value=0.0, step=0.01)

    st.write("---")
    st.subheader("적정주가 계산을 위한 추가 입력값")

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
