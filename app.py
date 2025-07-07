import streamlit as st
from krx_api import get_stock_info_by_name_or_code, get_fair_value

st.set_page_config(page_title="KRX 적정주가 계산기", layout="centered")
st.title("📊 KRX 적정주가 계산기")

user_input = st.text_input("종목코드 또는 종목명", "삼성전자 또는 005930")

if st.button("계산하기"):
    with st.spinner("데이터를 불러오는 중..."):
        try:
            result = get_stock_info_by_name_or_code(user_input)
            if result is None:
                st.error("📛 해당 종목의 데이터를 찾을 수 없습니다.")
            else:
                st.success("✅ 데이터 불러오기 성공!")
                st.write("### 🔍 기본 정보")
                st.json(result)

                fair_value = get_fair_value(result)
                st.write("### 💰 적정주가 계산 결과")
                st.metric(label="적정주가", value=f"{fair_value:,.0f}원")
                try:
                    current_price = int(result.get("trdPrc", 0))
                    upside = (fair_value - current_price) / current_price * 100
                    st.metric(label="업사이드 (%)", value=f"{upside:.2f}%")
                except:
                    pass
        except Exception as e:
            st.exception(e)
