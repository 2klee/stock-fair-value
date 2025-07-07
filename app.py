import streamlit as st
from krx_api import get_stock_info_by_name_or_code

st.set_page_config(page_title="📈 주식 적정주가 계산기", layout="centered")
st.title("📊 종목 입력 후 적정주가 계산")

user_input = st.text_input("종목명 또는 종목코드를 입력하세요 (예: 삼성전자 또는 005930)", value="")

if st.button("📥 적정주가 계산"):
    print("🧪 [버튼 클릭됨] 입력값:", user_input)
    result = get_stock_info_by_name_or_code(user_input.strip())

    if result:
        st.success(f"✅ 적정주가 계산 완료!")
        st.json(result)
    else:
        st.error("📛 해당 종목의 데이터를 찾을 수 없습니다.")
        print("🚫 결과 없음")
