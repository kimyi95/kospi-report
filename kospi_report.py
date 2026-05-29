from email.mime.text import MIMEText
from io import StringIO
import os
import smtplib

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_html(url, encoding="euc-kr"):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.encoding = encoding
    return r.text


def to_float_pct(x):
    try:
        return float(str(x).replace("%", "").replace("+", "").replace(",", "").strip())
    except:
        return 0.0


def to_int(x):
    try:
        s = str(x).strip().split()[0]
        s = s.replace(",", "").replace("+", "")
        return int(float(s))
    except:
        return 0


def get_kospi_return():
    url = "https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page=1"
    html = get_html(url)
    df = pd.read_html(StringIO(html))[0].dropna()
    latest = df.iloc[0]
    return str(latest["날짜"]), to_float_pct(latest["등락률"])


def get_kospi_recent_returns():
    dfs = []

    for page in [1, 2]:
        url = f"https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page={page}"
        html = get_html(url)
        df = pd.read_html(StringIO(html))[0].dropna()
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True)
    df["날짜"] = df["날짜"].astype(str)
    df["등락률"] = df["등락률"].apply(to_float_pct)

    return dict(zip(df["날짜"].head(10), df["등락률"].head(10)))


def get_top100_kospi():
    all_df = []

    for page in [1, 2]:
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page={page}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")

        table = pd.read_html(StringIO(html))[1]
        table = table.dropna(subset=["종목명"])

        codes = []
        for a in soup.select("a.tltle"):
            href = a.get("href", "")
            if "code=" in href:
                codes.append(href.split("code=")[-1][:6])

        table = table.head(len(codes)).copy()
        table["종목코드"] = codes[:len(table)]
        all_df.append(table)

    df = pd.concat(all_df, ignore_index=True).head(100)

    df["등락률"] = df["등락률"].apply(to_float_pct)
    df["현재가"] = df["현재가"].apply(to_int)

    return df


def get_stock_price_history(code, pages=26):
    dfs = []

    for page in range(1, pages + 1):
        url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}"
        html = get_html(url)
        df = pd.read_html(StringIO(html))[0].dropna()
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True)
    df["날짜"] = df["날짜"].astype(str)
    df["종가"] = df["종가"].apply(to_int)
    df = df[df["종가"] > 0].copy()

    return df


def get_stock_recent_returns(code):
    df = get_stock_price_history(code, pages=2)

    df["등락률"] = (df["종가"] / df["종가"].shift(-1) - 1) * 100
    df = df.dropna(subset=["등락률"])

    return dict(zip(df["날짜"], df["등락률"]))


def get_recent_outperform_count(code, kospi_recent_returns, report_date):
    try:
        stock_returns = get_stock_recent_returns(code)

        if report_date not in stock_returns:
            return "확인불가"

        count = 0

        for date, kospi_ret in kospi_recent_returns.items():
            if date in stock_returns:
                if stock_returns[date] > kospi_ret:
                    count += 1

        return count

    except:
        return "확인불가"


def get_high_status(code, current_price):
    try:
        df = get_stock_price_history(code, pages=26)

        if df.empty:
            return "확인불가"

        recent_250 = df.head(250)

        if len(recent_250) < 60:
            return "확인불가"

        high_250 = recent_250["종가"].max()

        if high_250 <= 0 or current_price <= 0:
            return "확인불가"

        gap_pct = (current_price / high_250 - 1) * 100

        if current_price >= high_250:
            return "🚀 돌파"

        if current_price >= high_250 * 0.97:
            return f"🔥 근접({gap_pct:.1f}%)"

        return f"{gap_pct:.1f}%"

    except:
        return "확인불가"


date, kospi_return = get_kospi_return()
kospi_recent_returns = get_kospi_recent_returns()

df = get_top100_kospi()

etf_keywords = [
    "KODEX", "TIGER", "KOSEF", "KBSTAR",
    "ARIRANG", "HANARO", "SOL", "ACE"
]

for keyword in etf_keywords:
    df = df[~df["종목명"].str.contains(keyword, na=False)]

result = df[df["등락률"] > kospi_return]
result = result.sort_values("등락률", ascending=False)

result["최근2주출현"] = result["종목코드"].apply(
    lambda code: get_recent_outperform_count(code, kospi_recent_returns, date)
)

result["전고점상태"] = result.apply(
    lambda row: get_high_status(row["종목코드"], row["현재가"]),
    axis=1
)

rows_html = ""

for i, row in enumerate(result.itertuples(), 1):
    recent_count = row.최근2주출현

    if isinstance(recent_count, int):
        recent_text = f"{recent_count}회"
    else:
        recent_text = recent_count

    rows_html += f"""
    <tr>
        <td>{i}</td>
        <td>{row.종목명}</td>
        <td>{row.현재가:,}</td>
        <td>{row.등락률:+.2f}%</td>
        <td>{recent_text}</td>
        <td>{row.전고점상태}</td>
    </tr>
    """

valid_counts = result[result["최근2주출현"].apply(lambda x: isinstance(x, int))]
valid_counts = valid_counts.sort_values("최근2주출현", ascending=False).head(5)

strong_html = ""

for i, row in enumerate(valid_counts.itertuples(), 1):
    strong_html += f"<li>{i}. {row.종목명} - 최근 2주 {row.최근2주출현}회</li>"

breakout = result[result["전고점상태"].astype(str).str.contains("돌파|근접", na=False)]

breakout_html = ""

if breakout.empty:
    breakout_html = "<li>전고점 돌파/근접 종목 없음</li>"
else:
    for row in breakout.itertuples():
        breakout_html += f"<li>{row.종목명} - {row.전고점상태}</li>"

html_body = f"""
<html>
<body>

<h2>KOSPI 상대강세 리포트</h2>

<p><b>기준일 :</b> {date}</p>
<p><b>KOSPI 등락률 :</b> {kospi_return:+.2f}%</p>
<p><b>상대강세 종목 수 :</b> {len(result)}개</p>

<table border="1" cellpadding="5" cellspacing="0">
<tr>
<th>순위</th>
<th>종목명</th>
<th>현재가</th>
<th>등락률</th>
<th>최근2주출현</th>
<th>전고점상태</th>
</tr>

{rows_html}

</table>

<br>

<h3>최근 2주 반복 출현 TOP 5</h3>
<ul>
{strong_html}
</ul>

<h3>전고점 돌파/근접 종목</h3>
<ul>
{breakout_html}
</ul>

<br>

<p><b>선별 기준</b></p>
<ul>
<li>KOSPI 상승일 : 종목 등락률 &gt; KOSPI 등락률</li>
<li>KOSPI 하락일 : KOSPI보다 덜 하락했거나 상승</li>
</ul>

<p>※ 최근2주출현 = 최근 10거래일 동안 KOSPI보다 강했던 횟수입니다.</p>
<p>※ 전고점상태 = 최근 약 250거래일 최고 종가 대비 위치입니다.</p>
<p>※ 데이터 출처 : 네이버 금융</p>
<p>※ 수급/뉴스는 네이버 구조상 불안정하여 제외했습니다.</p>
<p>※ 투자 참고용 자료입니다.</p>

</body>
</html>
"""

msg = MIMEText(html_body, "html", _charset="utf-8")
msg["Subject"] = f"[KOSPI 상대강세] {date}"
msg["From"] = os.environ["EMAIL_ADDRESS"]
msg["To"] = os.environ["RECEIVER_EMAIL"]

server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
server.login(os.environ["EMAIL_ADDRESS"], os.environ["EMAIL_PASSWORD"])
server.send_message(msg)
server.quit()
