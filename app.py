import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import zipfile
import io

# API 키 세팅 (본인 키로 교체)
DART_API_KEY = st.secrets["DART_API_KEY"]

# DART corp_code 조회
@st.cache_data(show_spinner=False)
def get_corp_code(company_name):
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    res = requests.get(url)
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    xml_data = zf.read("CORPCODE.xml")
    df = pd.read_xml(xml_data)
    row = df[df['corp_name'].str.contains(company_name)]
    return row.iloc[0]['corp_code'] if not row.empty else None

# KRX 코스피 / 코스닥 기본정보 API 호출
@st.cache_data(show_spinner=False)
def get_krx_base_info(market: str, bas_dt: str):
    if market == "코스피":
        url = "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"
    else:
        url = "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"

    params = {
        "basDt": bas_dt
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    # 데이터는 data['OutBlock_1']에 종목 리스트 배열로 존재
    items = data.get("OutBlock_1", [])
    df = pd.DataFrame(items)
    return df

# DART 재무제표 조회
@st.cache_data(show_spinner=False)
def get_financials(corp_code, year):
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": "11011",
        "fs_div": "CFS"
    }
    r = requests.get(url, params=params).json()
    if 'list' not in r:
        return pd.DataFrame()
    return pd.DataFrame(r['list'])

def extract_item(df, item_name):
    row = df[df['account_nm'] == item_name]
    if row.empty:
        return 0
    try:
        return int(float(row.iloc[0]['thstrm_amount'].replace(",", "")))
    except:
        return 0

st.title("KRX (코스피/코스닥) + DART 연동 적정주가 계산기")

market = st.selectbox("시장 선택", ["코스피", "코스닥"])
today = datetime.now().strftime("%Y%m%d")
stock_name = st.text_input("종목명 입력", "삼성전자")

if st.button("계산 시작"):
    with st.spinner("KRX 기본정보 조회 중..."):
        try:
            krx_df = get_krx_base_info(market, today)
        except Exception as e:
            st.error(f"KRX API 호출 실패: {e}")
            st.stop()

    st.write("KRX 기본정보 컬럼명:", krx_df.columns)
    st.write("KRX 기본정보 데이터 일부:", krx_df.head())

    stock_row = krx_df[krx_df['isuKorNm'] == stock_name]
    if stock_row.empty:
        st.error("해당 종목을 찾을 수 없습니다.")
        st.stop()

    isu_cd = stock_row.iloc[0]['isuCd']
    shares_str = stock_row.iloc[0]['listShrs']
    try:
        shares = int(shares_str.replace(",", ""))
    except:
        shares = 0

    corp_code = get_corp_code(stock_name)
    if corp_code is None:
        st.error("DART 기업코드를 찾을 수 없습니다.")
        st.stop()

    now = datetime.now()
    y1, y2 = now.year - 1, now.year - 2

    with st.spinner("DART 재무정보 조회 중..."):
        df1 = get_financials(corp_code, y1)
        df0 = get_financials(corp_code, y2)

    if df1.empty:
        st.error(f"{y1}년 재무정보가 없습니다.")
        st.stop()

    net_income_y1 = extract_item(df1, "당기순이익")
    equity_y1 = extract_item(df1, "자본")
    revenue_y1 = extract_item(df1, "매출액")

    eps = net_income_y1 / shares if shares else 0
    roe = net_income_y1 / equity_y1 if equity_y1 else 0

    sales_growth = 0
    if not df0.empty:
        revenue_y0 = extract_item(df0, "매출액")
        sales_growth = ((revenue_y1 - revenue_y0) / revenue_y0) if revenue_y0 else 0

    # 계산식 예시 (자동화된 가중치)
    avg_per = 10.0
    peg_adj = 0
    growth_weight = max(0, sales_growth) * 2
    roe_adj = 1.2 if roe >= 0.1 else 1.0
    sales_adj = sales_growth
    stability_score = 80

    fair_value = eps * (avg_per + peg_adj + growth_weight)
    fair_value *= (roe_adj + sales_adj)
    fair_value *= (stability_score / 100)

    st.metric("📈 적정주가", f"{fair_value:,.2f} 원")
    st.write(f"- 종목명: {stock_name}")
    st.write(f"- ISU 코드: {isu_cd}")
    st.write(f"- 상장주식수: {shares:,}")
    st.write(f"- EPS: {eps:,.2f}")
    st.write(f"- ROE: {roe:.2%}")
    st.write(f"- 매출성장률: {sales_growth:.2%}")
    st.caption("※ 투자 참고용이며, 책임은 본인에게 있습니다.")
