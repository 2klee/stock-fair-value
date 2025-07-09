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

def calculate_eps(net_income, stock_shares):
    if net_income is None or stock_shares == 0:
        return None
    return net_income / stock_shares

def calculate_roe(net_income, equity):
    if net_income is None or equity is None or equity == 0:
        return None
    return (net_income / equity) * 100

def calculate_sales_growth(sales_last, sales_prev):
    if sales_last is None or sales_prev is None or sales_prev == 0:
        return 0.0
    return (sales_last - sales_prev) / sales_prev * 100

def calculate_fair_price(eps, per_avg, peg_adj, growth_weight, roe_adj, sales_growth_adj, stability_score):
    base = eps * (per_avg + peg_adj + growth_weight)
    modifier = roe_adj + sales_growth_adj
    price = base * modifier * (stability_score / 100)
    return price

# --- Streamlit UI ---
st.title("📊 KRX + DART 기반 적정주가 자동 계산기")

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

    try:
        stock_shares = int(selected_row['LIST_SHRS'].replace(',', ''))
    except:
        stock_shares = 0
    st.write(f"상장주식수: {stock_shares:,} 주")

    corp_code_map = get_corp_code_map()
    stock_code = selected_row["ISU_SRT_CD"]
    corp_code = corp_code_map.get(stock_code) or corp_code_map.get(stock_code.lstrip("0"))

    if corp_code is None:
        st.error(f"DART 기업코드 매핑 실패: 종목코드 '{stock_code}'가 DART DB에 없습니다.")
        st.stop()

    this_year = datetime.today().year

    # 사업보고서(11011), 없으면 반기보고서(11012), 없으면 3분기보고서(11014) 순서로 조회
    fin_list_last = fetch_dart_financial_data(corp_code, this_year - 1, reprt_code="11011")
    if fin_list_last is None:
        fin_list_last = fetch_dart_financial_data(corp_code, this_year - 1, reprt_code="11012")
    if fin_list_last is None:
        fin_list_last = fetch_dart_financial_data(corp_code, this_year - 1, reprt_code="11014")

    if fin_list_last is None:
        st.error("최근 연도 재무데이터를 불러올 수 없습니다.")
        st.stop()

    fin_list_prev = fetch_dart_financial_data(corp_code, this_year - 2, reprt_code="11011")
    if fin_list_prev is None:
        fin_list_prev = fetch_dart_financial_data(corp_code, this_year - 2, reprt_code="11012")
    if fin_list_prev is None:
        fin_list_prev = fetch_dart_financial_data(corp_code, this_year - 2, reprt_code="11014")

    fin_map_last = extract_financial_items(fin_list_last)
    fin_map_prev = extract_financial_items(fin_list_prev) if fin_list_prev else {}

    net_income_ownership = fin_map_last.get("지배주주귀속순이익")
    net_income_total = fin_map_last.get("당기순이익")

    st.write(f"🔢 지배주주귀속순이익: {net_income_ownership if net_income_ownership is not None else '데이터 없음'}")
    st.write(f"🔢 당기순이익: {net_income_total if net_income_total is not None else '데이터 없음'}")

    net_income = (
        net_income_ownership
        or net_income_total
        or find_financial_value(fin_map_last, "지배주주귀속순이익", exact_match=True)
        or find_financial_value(fin_map_last, "당기순이익", exact_match=True)
    )
    equity = find_financial_value(fin_map_last, "자본총계", exact_match=True)
    sales_last = find_financial_value(fin_map_last, "매출")
    sales_prev = find_financial_value(fin_map_prev, "매출")

    EPS = calculate_eps(net_income, stock_shares)
    ROE = calculate_roe(net_income, equity)
    sales_growth = calculate_sales_growth(sales_last, sales_prev)

    st.write("### 자동 계산된 재무정보")
    st.write(f"- EPS (주당순이익): {EPS if EPS is not None else '데이터 없음'}")
    st.write(f"- ROE (자기자본이익률 %): {ROE if ROE is not None else '데이터 없음'}")
    st.write(f"- 매출 성장률 (%): {sales_growth:.2f}")

    st.subheader("📐 적정주가 계산을 위한 입력값")
    per_avg = st.number_input("PER 평균", min_value=0.0, value=10.0, step=0.1)
    peg_adj = st.number_input("PEG 조정치", value=0.0, step=0.1)
    growth_weight = st.number_input("성장가중치", value=0.0, step=0.1)
    roe_adj = st.number_input("ROE 보정계수", value=1.0, step=0.01)
    sales_growth_adj = st.number_input("매출성장률 보정치", value=0.0, step=0.01)
    stability_score = st.number_input("안정성 점수 (0~100)", min_value=0, max_value=100, value=80)

    if st.button("적정주가 계산"):
        if EPS is None:
            st.error("EPS 데이터가 없어 적정주가를 계산할 수 없습니다.")
        else:
            try:
                fair_price = calculate_fair_price(
                    eps=EPS,
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
