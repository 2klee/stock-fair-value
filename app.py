# fair_price_app.py
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# API KEY 세팅 (Streamlit secrets에 미리 등록해두어야 함)
DART_API_KEY = st.secrets["DART_API_KEY"]
KRX_API_KEY = st.secrets["KRX_API_KEY"]  # 현재 사용 안 하지만 필요시 활용 가능

# 기본 URL
KRX_BASE = "http://data-krx.co.kr/svc/apis/sto"
DART_BASE = "https://opendart.fss.or.kr/api"

# 공통 헤더 (KRX API 우회용)
KRX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://data.krx.co.kr",
    "Accept": "application/json",
    "Content-Type": "application/json"
}


def get_krx_basic_info(date):
    """KRX 기본정보 조회 (코스피+코스닥)"""
    url = f"{KRX_BASE}/stk_isu_base_info.json"
    params = {"basDt": date}
    try:
        res = requests.get(url, params=params, headers=KRX_HEADERS, timeout=10)
        res.raise_for_status()
        data = res.json()
        df = pd.DataFrame(data.get("OutBlock_1", []))
        return df
    except Exception as e:
        st.error(f"KRX 기본정보 API 호출 실패: {e}")
        return pd.DataFrame()


def get_krx_daily_info(date):
    """KRX 일별 매매정보 조회"""
    url = f"{KRX_BASE}/stk_bydd_trd.json"
    params = {"basDt": date}
    try:
        res = requests.get(url, params=params, headers=KRX_HEADERS, timeout=10)
        res.raise_for_status()
        data = res.json()
        df = pd.DataFrame(data.get("OutBlock_1", []))
        return df
    except Exception as e:
        st.error(f"KRX 일별 매매정보 API 호출 실패: {e}")
        return pd.DataFrame()


def get_dart_corp_code(corp_name):
    """DART API에서 회사명으로 corp_code 조회"""
    url = f"{DART_BASE}/corpCode.xml"
    # DART는 XML 파일 한번 받아서 내부에서 검색하는 방식 (복잡하므로 DART OpenAPI 문서 참고)
    # 여기서는 편의상 간단히 API로 회사명 검색 시뮬레이션 (실제로는 사전 corpCode.xml 다운로드 후 파싱 필요)
    # 대신 기업명 검색 API는 따로 없으니, 내부 사전파일을 미리 받아서 관리해야 함.
    # 여기선 대체로 사전 준비되어 있다고 가정
    st.warning("DART 회사코드 검색 기능은 별도 구현 필요합니다. 직접 corp_code를 입력해주세요.")
    return None


def get_dart_financials(corp_code, year):
    """DART API에서 단일 재무제표 조회 (요약 재무정보)"""
    url = f"{DART_BASE}/fnlttSinglAcnt.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": "11011"  # 사업보고서
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data.get("status") != "013":  # 정상 상태코드가 아닌 경우 처리
            # 재무제표 항목 추출
            items = data.get("list", [])
            # 필요한 항목들 초기화
            eps = None
            roe = None
            revenue_growth = None
            debt_ratio = None
            current_ratio = None

            # 각 재무제표 항목명에 따라 값 매핑 (DART 항목명은 한글, 기업마다 조금씩 다름)
            for item in items:
                name = item.get("account_nm", "")
                val = item.get("thstrm_amount", "").replace(",", "").strip()
                try:
                    val = float(val)
                except:
                    val = None

                if "주당순이익" in name or "EPS" in name:
                    if val is not None:
                        eps = val
                elif "자기자본이익률" in name or "ROE" in name:
                    if val is not None:
                        roe = val
                elif "매출액증가율" in name or "매출액증감률" in name:
                    if val is not None:
                        revenue_growth = val
                elif "부채비율" in name:
                    if val is not None:
                        debt_ratio = val
                elif "유동비율" in name:
                    if val is not None:
                        current_ratio = val

            return {
                "EPS": eps,
                "ROE": roe,
                "매출성장률": revenue_growth,
                "부채비율": debt_ratio,
                "유동비율": current_ratio,
            }
        else:
            st.warning("DART API에서 재무정보를 찾지 못했습니다.")
            return None

    except Exception as e:
        st.error(f"DART 재무정보 API 호출 실패: {e}")
        return None


def calculate_fair_price(eps, per_avg, peg_adj, growth_factor, roe_weight, revenue_growth_adj, stability_score):
    price = eps * (per_avg + peg_adj + growth_factor)
    price *= (roe_weight + revenue_growth_adj)
    price *= (stability_score / 100)
    return price


def estimate_stability_score(debt_ratio, current_ratio):
    # 부채비율, 유동비율이 None이면 기본값 설정
    if debt_ratio is None:
        debt_ratio = 70.0
    if current_ratio is None:
        current_ratio = 120.0
    score = 100 - (debt_ratio * 0.1) + (current_ratio * 0.05)
    return max(min(score, 100), 0)  # 0~100 범위로 제한


# Streamlit UI
st.title("📈 적정주가 자동 계산기")

user_input = st.text_input("종목 코드(6자리) 또는 종목명 입력 (예: 005930 또는 삼성전자)")
base_date = st.date_input("기준일자", datetime.today())
base_date_str = base_date.strftime("%Y%m%d")
current_year = base_date.year - 1  # 재무정보는 보통 전년도 기준

if user_input:
    krx_basic_df = get_krx_basic_info(base_date_str)
    krx_daily_df = get_krx_daily_info(base_date_str)

    if krx_basic_df.empty:
        st.error("KRX 기본정보를 불러오지 못했습니다. 날짜를 확인하거나 서버 상태를 점검하세요.")
    elif "ISU_SRT_CD" not in krx_basic_df.columns:
        st.error(f"KRX 기본정보 형식이 예상과 다릅니다: {krx_basic_df.columns.tolist()}")
        st.dataframe(krx_basic_df)
    else:
        # 종목코드(6자리)와 종목명 구분
        user_input = user_input.strip()
        if user_input.isdigit() and len(user_input) == 6:
            # 종목코드로 조회 (단축코드)
            target_info = krx_basic_df[krx_basic_df["ISU_SRT_CD"] == user_input]
        else:
            # 종목명으로 조회
            target_info = krx_basic_df[krx_basic_df["ISU_NM"] == user_input]

        if target_info.empty:
            st.warning("입력한 종목에 대한 정보를 찾을 수 없습니다.")
        else:
            isu_cd = target_info.iloc[0]["ISU_CD"]
            isu_nm = target_info.iloc[0]["ISU_NM"]
            st.subheader(f"📋 종목 기본정보 - {isu_nm}")
            st.dataframe(target_info)

            target_daily = krx_daily_df[krx_daily_df["ISU_CD"] == isu_cd]
            if target_daily.empty:
                st.warning("일별 매매정보가 없습니다.")
            else:
                st.subheader("📊 일별 매매정보")
                st.dataframe(target_daily)

            st.write("---")

            st.subheader("📑 DART 재무 정보 입력 또는 자동 조회")

            corp_code_input = st.text_input("DART 회사코드 입력 (예: 00126380). 모르면 직접 입력해 주세요.")
            if not corp_code_input:
                st.info("DART 회사코드를 입력해야 재무정보를 조회할 수 있습니다.")
                st.stop()

            fin_data = get_dart_financials(corp_code_input, current_year)

            if fin_data is None:
                st.warning("재무정보를 불러오지 못했습니다. 직접 입력해 주세요.")
                # 수동 입력
                eps = st.number_input("EPS", value=0.0, step=100.0)
                roe = st.number_input("ROE(%)", value=0.0, step=0.1)
                revenue_growth = st.number_input("매출 성장률(%)", value=0.0, step=0.1)
                debt_ratio = st.number_input("부채비율(%)", value=0.0, step=0.1)
                current_ratio = st.number_input("유동비율(%)", value=0.0, step=0.1)
            else:
                eps = fin_data.get("EPS") or 0
                roe = fin_data.get("ROE") or 0
                revenue_growth = fin_data.get("매출성장률") or 0
                debt_ratio = fin_data.get("부채비율") or 70
                current_ratio = fin_data.get("유동비율") or 120

                st.write(f"EPS: {eps}")
                st.write(f"ROE: {roe}%")
                st.write(f"매출 성장률: {revenue_growth}%")
                st.write(f"부채비율: {debt_ratio}%")
                st.write(f"유동비율: {current_ratio}%")

            # 계산값
            per_avg = 10
            peg_adj = 1.0
            growth_factor = revenue_growth / 10
            roe_weight = roe * 0.01
            revenue_growth_adj = revenue_growth * 0.01
            stability_score = estimate_stability_score(debt_ratio, current_ratio)

            st.subheader("🧮 계산 중간값")
            st.write(f"PER 평균: {per_avg}")
            st.write(f"PEG 조정치: {peg_adj}")
            st.write(f"성장가중치: {growth_factor:.2f}")
            st.write(f"ROE 보정계수: {roe_weight:.2f}")
            st.write(f"매출성장률 보정치: {revenue_growth_adj:.2f}")
            st.write(f"안정성 점수: {stability_score:.2f}")

            fair_price = calculate_fair_price(
                eps,
                per_avg,
                peg_adj,
                growth_factor,
                roe_weight,
                revenue_growth_adj,
                stability_score,
            )

            st.subheader("🎯 적정주가 결과")
            try:
                current_price_str = target_daily.iloc[0]["TDD_CLSPRC"].replace(",", "")
                current_price = int(float(current_price_str))
            except Exception:
                current_price = 0

            st.metric("적정주가", f"{fair_price:,.0f} 원")
            st.metric("현재 주가", f"{current_price:,.0f} 원")

            if current_price > 0:
                diff_pct = (fair_price - current_price) / current_price
                st.metric("프리미엄/할인율", f"{diff_pct:+.2%}")
            else:
                st.warning("현재 주가 정보가 없어 프리미엄/할인율을 계산할 수 없습니다.")
