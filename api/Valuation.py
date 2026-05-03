from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
from bs4 import BeautifulSoup
import pandas as pd
import yfinance as yf
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

def scrape_with_beautifulsoup(ticker, statement_type):
    endpoints = {
        "Income Statement": "financials",
        "Balance Sheet": "balance-sheet",
        "Cash Flow": "cash-flow"
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    }
    url = f"https://finance.yahoo.com/quote/{ticker}/{endpoints[statement_type]}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        header_div = soup.find('div', class_='D(tbhg)')
        table_headers =[col.get_text(strip=True) for col in header_div.children if col.name] if header_div else[]
            
        rows = soup.find_all('div', class_='D(tbr)')
        if not rows:
            return None, "Yahoo Finance blocked the scraper. Try yfinance!"
            
        financial_data = []
        for row in rows:
            cols =[col.get_text(strip=True) for col in row.children if col.name]
            if cols:
                financial_data.append(cols)
                
        df = pd.DataFrame(financial_data)
        if table_headers and len(table_headers) == len(df.columns):
            df.columns = table_headers
        return df, f"Successfully scraped {len(financial_data)} rows!"
    except Exception as e:
        return None, f"An error occurred: {e}"

def get_yf_data(ticker):
    ticker_obj = yf.Ticker(ticker)
    return ticker_obj.financials, ticker_obj.balance_sheet, ticker_obj.cashflow, ticker_obj.info

def safe_extract(df, row_names, default=0.0):
    if df is None or df.empty:
        return default
    if isinstance(row_names, str):
        row_names =[row_names]
    df_index_lower =[str(idx).strip().lower() for idx in df.index]
    for name in row_names:
        name_lower = str(name).strip().lower()
        for i, idx_name in enumerate(df_index_lower):
            if name_lower in idx_name:
                original_idx = df.index[i]
                for col in df.columns:
                    val = df.loc[original_idx, col]
                    if pd.notna(val) and str(val).strip() != '':
                        try:
                            return float(val)
                        except (ValueError, TypeError):
                            continue
    return default

# --- FastAPI Routes ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "data": None})

@app.post("/recalculate", response_class=HTMLResponse)
async def recalculate(request: Request, ticker: str = Form(...), coe: float = Form(...), cod: float = Form(...), tax: float = Form(...), growth: float = Form(...), term_growth: float = Form(...)):
    # Get the data again
    try:
        financials, balance_sheet, cashflow, info = get_yf_data(ticker)
        
        # Recalculate with new assumptions
        valuation = calculate_valuation_with_assumptions(financials, balance_sheet, cashflow, info, coe/100, cod/100, tax/100, growth/100, term_growth/100)
        
        data = {
            "ticker": ticker,
            "method": "yfinance",
            "income_statement": financials.to_html() if not financials.empty else "No data",
            "balance_sheet": balance_sheet.to_html() if not balance_sheet.empty else "No data", 
            "cash_flow": cashflow.to_html() if not cashflow.empty else "No data",
            "valuation": valuation
        }
    except Exception as e:
        data = {"error": str(e)}
    
    return templates.TemplateResponse("index.html", {"request": request, "data": data})

def calculate_valuation_with_assumptions(financials, balance_sheet, cashflow, info, ui_coe, ui_cod, ui_tax, ui_growth, ui_term_growth):
    price = info.get("currentPrice", 0)
    shares = safe_extract(financials, ["Diluted Average Shares", "Basic Average Shares", "Ordinary Shares Number"])
    market_cap = price * shares if shares else info.get("marketCap", 0)

    total_debt = safe_extract(balance_sheet, ["Total Debt", "Long Term Debt"])
    cash = safe_extract(balance_sheet, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Total Cash", "Cash"])
    net_debt = total_debt - cash

    interest_expense = safe_extract(financials, ["Interest Expense", "Interest Expense Non Operating"])
    pretax_income = safe_extract(financials, ["Pretax Income", "Income Before Tax", "EBT"], default=1.0)
    tax_provision = safe_extract(financials, ["Tax Provision", "Income Tax Expense", "Tax Effect Of Unusual Items"])

    capex = abs(safe_extract(cashflow, ["Capital Expenditure", "Purchases Of Property Plant And Equipment", "Capital Expenditures", "Investment In Property Plant And Equipment"]))
    cfo = safe_extract(cashflow, ["Operating Cash Flow", "Cash Flowsfromusedin Operating Activities Direct", "Total Cash From Operating Activities", "Net Cash Provided By Operating Activities", "Cash Flow From Continuing Operating Activities", "Net Cash From Operating Activities"])
    debt_issued = safe_extract(cashflow, ["Issuance Of Debt", "Proceeds From Debt", "Long Term Debt Issuance", "Debt Issuance"])
    debt_repaid = safe_extract(cashflow, ["Repayment Of Debt", "Payments Of Debt", "Long Term Debt Payments", "Debt Repayment"])
    net_borrowing = debt_issued + debt_repaid

    weight_eq = market_cap / (market_cap + total_debt) if (market_cap + total_debt) > 0 else 1
    weight_d = total_debt / (market_cap + total_debt) if (market_cap + total_debt) > 0 else 0
    dynamic_wacc = (weight_eq * ui_coe) + (weight_d * ui_cod * (1 - ui_tax))

    base_fcff = cfo + (abs(interest_expense) * (1 - ui_tax)) - capex
    base_fcfe = cfo - capex + net_borrowing

    eff_tax_rate = tax_provision / pretax_income if pretax_income > 0 else 0.21
    if eff_tax_rate > 0.40:
        eff_tax_rate = 0.21

    beta = info.get("beta", 1.0)
    calc_coe = 0.042 + beta * 0.058
    calc_cod = (abs(interest_expense) / total_debt) if total_debt > 0 else 0.05
    if calc_cod > 0.15:
        calc_cod = 0.05
    est_growth = info.get("earningsGrowth", 0.05)

    if dynamic_wacc <= ui_term_growth or ui_coe <= ui_term_growth:
        return None

    # Projections
    proj_fcff, proj_fcfe = base_fcff, base_fcfe
    pv_fcff, pv_fcfe = 0, 0

    for year in range(1, 6):
        proj_fcff *= (1 + ui_growth)
        proj_fcfe *= (1 + ui_growth)

        pv_cf_fcff = proj_fcff / ((1 + dynamic_wacc) ** year)
        pv_cf_fcfe = proj_fcfe / ((1 + ui_coe) ** year)

        pv_fcff += pv_cf_fcff
        pv_fcfe += pv_cf_fcfe

    tv_fcff = (proj_fcff * (1 + ui_term_growth)) / (dynamic_wacc - ui_term_growth)
    tv_fcfe = (proj_fcfe * (1 + ui_term_growth)) / (ui_coe - ui_term_growth)

    pv_tv_fcff = tv_fcff / ((1 + dynamic_wacc) ** 5)
    pv_tv_fcfe = tv_fcfe / ((1 + ui_coe) ** 5)

    firm_value = pv_fcff + pv_tv_fcff
    eq_value_from_fcff = firm_value + cash - total_debt
    implied_price_fcff = eq_value_from_fcff / shares if shares else 0

    operating_eq_value = pv_fcfe + pv_tv_fcfe
    eq_value_from_fcfe = operating_eq_value + cash
    implied_price_fcfe = eq_value_from_fcfe / shares if shares else 0

    return {
        "price": price,
        "total_debt": total_debt,
        "net_debt": net_debt,
        "tax_rate": eff_tax_rate,
        "coe": ui_coe,
        "cod": ui_cod,
        "growth": ui_growth,
        "fcfe_price": implied_price_fcfe,
        "fcff_price": implied_price_fcff
    }


    

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


            
