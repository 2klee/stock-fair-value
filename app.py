import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import zipfile
import io

# API 키 입력
DART_API_KEY = st.secrets["DART_API_KEY"]

# --- DART corp_code ---
@st.cache_data(show_spinner=False)
def get_corp_code(company_name):
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    res = requests.get(url)
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    xml_data = zf.read("CORPCODE.xml")
    df = pd.read_xml(xml_data)
    row = df[df['corp_name'].str.contains(company_name)]
    return row.iloc[0]['corp_code'] if not row.empty else None

# --- KRX 전종목 리스트 ---
@st.cache_data(show_spinner=False)
def get_krx_all_stock_list():
    url = "http://openapi.krx.co.kr/contents/COM/GenerateOTP.jspx"
    params = {
        "name": "fileDown",
        "filetype": "csv",
        "url": "MKD/04/0406/04060200/mkd04060200",
        "market_gubun": "ALL",
        "pagePath": "/contents/MKD/04/0406/04060200/MKD04060200.jsp"
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://data.krx.co.kr/"}
    res = requests.get(url, params=params, headers=headers)
    if res.status_code != 200:
        st.error("KRX 종목 리스트 OTP 생성 실패")
        return pd.DataFrame()
    otp = res.text
    dl_url = "http://file.krx.co.kr/download.jspx"
    dl_res = requests.post(dl_url, data={"code": otp}, headers=headers)
    df = pd.read_csv(io.StringIO(dl_res.content.decode("EUC-KR")))
    return df

# --- KRX 업종별 PER 평균 ---
@st.cache_data(show_spinner=False)
def get_industry_per():
    url = "http://openapi.krx.co.kr/contents/COM/GenerateOTP.jspx"
    params = {
        "name": "fileDown",
        "filetype": "csv",
        "url": "MKD/04/0406/04060204/mkd04060204",
        "market_gubun": "ALL",
        "pagePath": "/contents/MKD/04/0406/04060204/MKD04060204.jsp"
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://data.krx.co.kr/"}
    res = requests.get(url, params=params, headers=headers)
    if res.status_code != 200:
        st.error("KRX 업종별 PER OTP 생성 실패")
        return pd.DataFrame()
    otp = res.text
    dl_url = "http://file.krx.co.kr/download.jspx"
    dl_res = requests.post(dl_url, data={"code": otp}, headers=headers)
    df = pd.read_csv(io.StringIO(dl_res.content.decode("EUC-KR")))
    return df

# --- KRX에서 특정 종목 현재가, 상장주식수, 업종명 가져오기 ---
@st.cache_data(show_spinner=False)
def get_krx_stock_info(stock_name, krx_df):
    row = krx_df[krx_df['종목명'] == stock_name]
    if row.empty:
        return None, None, None
    try:
        price_col = [c for c in krx_df.columns if '현재가' in c or '종가' in c][0]
        share_col = [c for c in krx_df.columns if '상장주식수' in c][0]
        price = int(str(row.iloc[0][price_col]).replace(",", ""))
        shares = int(str(row.iloc[0][share_col]).replace(",", ""))
        industry = row.iloc[0]['업종']
        return price, shares, industry
    except Exception as e:
        st.error(f"KRX 데이터 추출 오류: {e}")
        return None, None, None

# --- DART 재무제표 가져오기 ---
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

# --- 재무 항목 금액 추출 ---
def extract_item(df, item_name):
    row = df[df['account_nm'] == item_name]
    if row.empty:
        return 0
    try:
        return int(float(row.iloc[0]['thstrm_amount'].replace(",", "")))
    except:
        return 0

# --- Streamlit UI ---
st.title("📊 KRX + DART 적정주가 자동 계산기 (자동값)")

company_name = st.text_input("종목명 입력", "삼성전자")

if company_name:
    krx_df = get_krx_all_stock_list()
    industry_per_df = get_industry_per()

    price, shares, industry = get_krx_stock_info(company_name, krx_df)
    if price is None:
        st.error("종목 정보를 찾을 수 없습니다.")
        st.stop()

    corp_code = get_corp_code(company_name)
    if corp_code is None:
        st.error("DART 기업코드를 찾을 수 없습니다.")
        st.stop()

    industry_row = industry_per_df[industry_per_df['업종'] == industry]
    if not industry_row.empty:
        per_col_candidates = [c for c in industry_per_df.columns if 'PER' in c or 'P/E' in c]
        if per_col_candidates:
            avg_per = float(industry_row.iloc[0][per_col_candidates[0]])
        else:
            avg_per = 10.0
    else:
        avg_per = 10.0

    now = datetime.now()
    y1, y2 = now.year - 1, now.year - 2
    df1 = get_financials(corp_code, y1)
    df0 = get_financials(corp_code, y2)

    if df1.empty:
        st.error(f"{y1}년 재무제표 데이터를 찾을 수 없습니다.")
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

    # 자동 계산값
    peg_adj = 0  # PEG 직접 계산 어려우니 0 고정
    growth_weight = max(0, sales_growth) * 2  # 매출성장률 기반 성장가중치 예시 (임의 가중치 2배)
    roe_adj = 1.2 if roe >= 0.1 else 1.0  # ROE 10% 이상일 때 가중치 1.2, 미만 1.0
    sales_adj = sales_growth  # 매출성장률 그대로 사용
    stability_score = 80  # 고정 또는 추가 재무안정성 평가 추가 가능

    fair_value = eps * (avg_per + peg_adj + growth_weight)
    fair_value *= (roe_adj + sales_adj)
    fair_value *= (stability_score / 100)

    st.metric("📈 적정주가", f"{fair_value:,.2f} 원")
    st.write(f"- 현재가: {price:,} 원")
    st.write(f"- 상장주식수: {shares:,} 주")
    st.write(f"- EPS: {eps:,.2f}")
    st.write(f"- ROE: {roe:.2%}")
    st.write(f"- 매출성장률: {sales_growth:.2%}")
    diff = (fair_value - price) / price * 100
    st.write(f"- 현재가 대비 적정주가 차이: {diff:.2f}%")

    st.caption("※ 자동 계산된 값으로 산출된 결과이며, 실제 투자 판단은 본인 책임입니다.")
