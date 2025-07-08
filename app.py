import streamlit as st
import pandas as pd
import requests
import zipfile
import io

# 환경변수에서 API 키 불러오기
DART_API_KEY = st.secrets["DART_API_KEY"]
KRX_API_KEY = st.secrets["KRX_API_KEY"]

@st.cache_data
def get_corp_code(company_name):
    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_API_KEY}"
    res = requests.get(url)
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    xml_data = zf.read("CORPCODE.xml")
    df = pd.read_xml(xml_data)
    row = df[df['corp_name'].str.contains(company_name)]
    return row.iloc[0]['corp_code'] if not row.empty else None

@st.cache_data
def get_financials(corp_code, year):
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    
    for fs_div in ["CFS", "OFS"]:  # 연결재무제표 -> 개별재무제표 순으로 시도
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": "11011",
            "fs_div": fs_div
        }
        r = requests.get(url, params=params).json()
        if r.get("status") == "013":
            continue  # 데이터 없음, 다음 시도
        if "list" in r:
            return pd.DataFrame(r["list"])
        else:
            st.warning(f"{year}년 {fs_div} 재무제표를 찾을 수 없습니다. (message: {r.get('message', '')})")
    return pd.DataFrame([])


def extract_item(df, item):
    if df.empty:
        return 0
    f = df[df['account_nm'] == item]
    if f.empty:
        return 0
    return int(f.iloc[0]['thstrm_amount'].replace(',', ''))

def calculate_fair_price(data):
    net_income_y1, net_income_y0, revenue_y1, revenue_y0, equity, debt, shares, per_avg, growth_weight, stability_score = data

    eps = net_income_y1 / shares if shares else 0
    roe = (net_income_y1 / equity) * 100 if equity else 0
    revenue_growth = ((revenue_y1 - revenue_y0) / revenue_y0) * 100 if revenue_y0 else 0
    eps_growth = ((net_income_y1 - net_income_y0) / abs(net_income_y0)) * 100 if net_income_y0 else 0
    peg_adj = per_avg / eps_growth if eps_growth != 0 else 0
    debt_ratio = (debt / (equity + debt)) * 100 if (equity + debt) else 0
    stability_score = max(0, 100 - debt_ratio)

    price = eps * (per_avg + peg_adj + growth_weight) * (roe * 0.01 + revenue_growth * 0.01) * (stability_score / 100)
    return round(price, 2), round(eps, 2), round(roe, 2), round(revenue_growth, 2), round(stability_score, 2)

st.title("📊 복합 적정주가 자동 계산기")

company = st.text_input("종목명 입력 (예: 삼성전자)")
per_avg = st.slider("PER 평균", 5, 30, 10)
growth_weight = st.slider("성장가중치", 0.0, 2.0, 1.0)

if st.button("계산 시작"):
    corp_code = get_corp_code(company)
    st.write("corp_code:", corp_code)  # 여기에 출력문 넣기
    if not corp_code:
        st.error("종목명을 찾을 수 없습니다.")
    else:
        st.info("DART에서 재무정보 수집 중...")
        df1 = get_financials(corp_code, 2023)
        st.write(df1.head())
        st.write("계정명 리스트:", df1['account_nm'].unique())
        df0 = get_financials(corp_code, 2022)

        net_income_y1 = extract_item(df1, "당기순이익")
        net_income_y0 = extract_item(df0, "당기순이익")
        revenue_y1 = extract_item(df1, "매출액")
        revenue_y0 = extract_item(df0, "매출액")
        equity = extract_item(df1, "자본총계")
        debt = extract_item(df1, "부채총계")

        # 예시: 상장주식수 (실제는 KRX 연동 필요)
        shares = 6000000000

        result = calculate_fair_price(
            [net_income_y1, net_income_y0, revenue_y1, revenue_y0, equity, debt, shares, per_avg, growth_weight, 0]
        )

        fair_price, eps, roe, rev_growth, stability = result

        st.success(f"📌 EPS: {eps:.2f} 원")
        st.success(f"📈 적정주가: {fair_price:.2f} 원")
        st.caption(f"ROE: {roe:.2f}%, 매출 성장률: {rev_growth:.2f}%, 안정성 점수: {stability}")
