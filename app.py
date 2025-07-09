...
    net_income, equity, revenue, revenue_prev = None, None, None, None
    for item in fin_list:
        name = item.get("account_nm", "")
        aid = item.get("account_id", "")
        sj_div = item.get("sj_div", "")
        if sj_div == "CIS" and aid == "ifrs-full_ProfitLoss" and "당기순이익" in name and "비지배" not in name:
            net_income = extract_amount(item)
        if name.strip() == "자본총계":
            equity = extract_amount(item)
        if name.strip() == "매출액":
            revenue = extract_amount(item)
            revenue_prev = extract_amount({"thstrm_amount": item.get("frmtrm_amount")})
...
