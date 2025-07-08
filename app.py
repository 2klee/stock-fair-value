import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import zipfile
import io

# ✅ DART & KRX API KEY 입력
DART_API_KEY = st.secrets["DART_API_KEY"]
KRX_API_KEY = st.secrets["KRX_API_KEY"]

# ✅ DART: 회사명 → corp_code
@st.cache_data(show_spinner=False)
def get_corp_code(company_name):
    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    res = requests.get(url)
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    xml_data = zf.read("CORPCODE.xml")
    df = pd.read_xml(xml_data)
    row = df[df['corp_name'].str.contains(company_name)]
    return row.iloc[0]['corp_code'] if not row.empty else None

# ✅ DART: 재무제표 조회
@st.cache_data(show_spinner=False)
def get_financials(corp_code, year):
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": "11011",  # 사업보고서
        "fs_div": "CFS"         # 연결
    }
    r = requests.get(url, params=params).json()
    if r.get("status") == "013" or "list" not in r:
        return pd.DataFrame([])
    return pd.DataFrame(r["list"])

# ✅ 특정 항목 추출
def extract_item(df, keywords):
    if df.empty: return 0
    for k in keywords:
        row = df[df["account_nm"].str.contains(k)]
        if not row.empty:
            val = row.iloc[0]["thstrm_amount"]
            try:
                return int(str(val).replace(',', ''))
            except:
                return 0
    return 0

# ✅ KRX: 주가, 상장주식수 불러오기
@st.cache_data(show_spinner=False)
def get_krx_stock_info(stock_name):
    url = f"http://openapi.krx.co.kr/contents/COM/GenerateOTP.jspx"
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",  # 개별종목 시세
        "name": "form",
        "mktId": "ALL",
        "share": "1",
        "url": "MDCSTAT01901",
        "searchType": "1"
    }
    otp = requests.get(url, params=params).text
    download_url = "http://file.krx.co.kr/download.jspx"
    r = requests.post(download_url, data={"code": otp}, headers={"Referer": url})
    df = pd.read_csv(io.StringIO(r.content.decode("EUC-KR")))

    row = df[df['종목명'].str.strip() == stock_name.strip()]
    if row.empty:
        return None, None
    price = int(str(row.iloc[0]['현재가']).replace(",", ""))
    shares = int(str(row.iloc[0]['상장주식수']).replace(",", ""))
    return price, shares

# ✅ Streamlit UI
st.title("📊 KRX + DART 기반 적정주가 계산기")

company_name = st.text_input("종목명 (예: 삼성전자)", "삼성전자")
growth_weight = st.slider("성장가중치", 0.0, 2.0, 1.0)

if st.button("계산 시작"):
    with st.spinner("KRX & DART 데이터 수집 중..."):
        price, shares = get_krx_stock_info(company_name)
        corp_code = get_corp_code(company_name)
        now = datetime.now()
        y1, y2 = now.year - 1, now.year - 2
        df1 = get_financials(corp_code, y1)
        df0 = get_financials(corp_code, y2)

    if not corp_code:
        st.error("📛 DART에서 기업코드를 찾을 수 없습니다.")
    elif price is None or shares is None:
        st.error("📛 KRX에서 주가 또는 상장주식수를 찾을 수 없습니다.")
    elif df1.empty or df0.empty:
        st.error("📛 DART 재무제표 조회 실패")
    else:
        st.success("✅ 데이터 수집 완료")

        # 항목 추출
        net_income = extract_item(df1, ["당기순이익", "지배"])
        net_income_prev = extract_item(df0, ["당기순이익", "지배"])
        sales = extract_item(df1, ["매출", "수익"])
        sales_prev = extract_item(df0, ["매출", "수익"])
        equity = extract_item(df1, ["자본총계"])
        debt = extract_item(df1, ["부채총계"])

        eps = net_income / shares if shares else 0
        eps_prev = net_income_prev / shares if shares else 0
        per = price / eps if eps else 0
        eps_growth = (eps - eps_prev) / eps_prev if eps_prev else 0
        peg = per / eps_growth if eps_growth else per
        roe = net_income / equity if equity else 0
        sales_growth = (sales - sales_prev) / sales_prev if sales_prev else 0
        debt_ratio = (debt / equity * 100) if equity else 0
        stability_score = max(0, 100 - debt_ratio)

        fair_price = eps * (per + peg + growth_weight) * (roe + sales_growth) * (stability_score / 100)

        # 결과 출력
        st.subheader("📈 계산 결과")
        st.write(f"현재 주가: {price:,}원")
        st.write(f"EPS: {eps:.2f}원")
        st.write(f"PER: {per:.2f}")
        st.write(f"PEG: {peg:.2f}")
        st.write(f"ROE: {roe:.2%}")
        st.write(f"매출 성장률: {sales_growth:.2%}")
        st.write(f"부채비율: {debt_ratio:.2f}%")
        st.write(f"안정성 점수: {stability_score:.2f}")
        st.markdown(f"### 💵 적정주가: `{fair_price:,.0f} 원`")
