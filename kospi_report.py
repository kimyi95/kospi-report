from email.mime.text import MIMEText
from io import StringIO
import os
import smtplib

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_html(url, encoding="euc-kr"):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )
    r.encoding = encoding
    return r.text


def to_float_pct(x):
    try:
        return float(
            str(x)
            .replace("%", "")
            .replace("+", "")
            .replace(",", "")
            .strip()
        )
    except:
        return 0.0


def to_int(x):
    try:
        return int(
            str(x)
            .replace(",", "")
            .replace("+", "")
            .strip()
        )
    except:
        return 0


def get_kospi_return():
    url = (
        "https://finance.naver.com/"
        "sise/sise_index_day.naver"
        "?code=KOSPI&page=1"
    )
    html = get_html(url)
    df = pd.read_html(StringIO(html))[0].dropna()
    latest = df.iloc[0]

    return (
        str(latest["날짜"]),
        to_float_pct(latest["등락률"])
    )


def get_top100_kospi():
    all_df = []

    for page in [1, 2]:
        url = (
            "https://finance.naver.com/"
            f"sise/sise_market_sum.naver"
            f"?sosok=0&page={page}"
        )
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


def get_investor_flow(code, date):
    """
    네이버 금융 종목별 투자자별 매매동향에서
    개인 / 외국인 / 기관 순매수를 직접 읽음.
    실패 시 0 반환.
    """

    try:
        url = (
            "https://finance.naver.com/"
            f"item/frgn.naver?code={code}&page=1"
        )

        html = get_html(url)
        tables = pd.read_html(StringIO(html))

        target = None

        for table in tables:
            cols = [str(c) for c in table.columns]

            has_date = any("날짜" in c for c in cols)
            has_person = any("개인" in c for c in cols)
            has_foreign = any("외국인" in c for c in cols)
            has_institution = any("기관" in c for c in cols)

            if has_date and has_person and has_foreign and has_institution:
                target = table
                break

        if target is None:
            return 0, 0, 0

        target = target.dropna()

        if target.empty:
            return 0, 0, 0

        date_col = None
        person_col = None
        foreign_col = None
        institution_col = None

        for col in target.columns:
            col_str = str(col)

            if "날짜" in col_str:
                date_col = col
            elif "개인" in col_str:
                person_col = col
            elif "외국인" in col_str:
                foreign_col = col
            elif "기관" in col_str:
                institution_col = col

        row = target[
            target[date_col].astype(str) == date
        ]

        if row.empty:
            row = target.iloc[[0]]

        individual = to_int(row[person_col].iloc[0])
        foreign = to_int(row[foreign_col].iloc[0])
        institution = to_int(row[institution_col].iloc[0])

        return individual, foreign, institution

    except:
        return 0, 0, 0


date, kospi_return = get_kospi_return()
df = get_top100_kospi()

etf_keywords = [
    "KODEX",
    "TIGER",
    "KOSEF",
    "KBSTAR",
    "ARIRANG",
    "HANARO",
    "SOL",
    "ACE"
]

for keyword in etf_keywords:
    df = df[
        ~df["종목명"]
        .str.contains(keyword, na=False)
    ]

df["초과수익률"] = df["등락률"] - kospi_return

result = df[
    df["등락률"] > kospi_return
]

result = result.sort_values(
    "초과수익률",
    ascending=False
)

flows = result["종목코드"].apply(
    lambda code: get_investor_flow(code, date)
)

result["개인순매수"] = [x[0] for x in flows]
result["외국인순매수"] = [x[1] for x in flows]
result["기관순매수"] = [x[2] for x in flows]

rows_html = ""

for i, row in enumerate(result.itertuples(), 1):
    rows_html += f"""
    <tr>
        <td>{i}</td>
        <td>{row.종목명}</td>
        <td>{row.현재가:,}</td>
        <td>{row.등락률:+.2f}%</td>
        <td>{row.초과수익률:+.2f}%p</td>
        <td>{row.개인순매수:,}</td>
        <td>{row.외국인순매수:,}</td>
        <td>{row.기관순매수:,}</td>
    </tr>
    """

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
<th>초과수익률</th>
<th>개인순매수</th>
<th>외국인순매수</th>
<th>기관순매수</th>
</tr>

{rows_html}

</table>

<br>

<p><b>선별 기준</b></p>
<ul>
<li>KOSPI 상승일 : 종목 등락률 &gt; KOSPI 등락률</li>
<li>KOSPI 하락일 : KOSPI보다 덜 하락했거나 상승</li>
</ul>

<p>※ 개인/외국인/기관 순매수는 네이버 금융 종목별 투자자 매매동향 기준입니다.</p>
<p>※ 데이터 출처 : 네이버 금융</p>
<p>※ 투자 참고용 자료입니다.</p>

</body>
</html>
"""

msg = MIMEText(
    html_body,
    "html",
    _charset="utf-8"
)

msg["Subject"] = f"[KOSPI 상대강세] {date}"
msg["From"] = os.environ["EMAIL_ADDRESS"]
msg["To"] = os.environ["RECEIVER_EMAIL"]

server = smtplib.SMTP_SSL(
    "smtp.gmail.com",
    465
)

server.login(
    os.environ["EMAIL_ADDRESS"],
    os.environ["EMAIL_PASSWORD"]
)

server.send_message(msg)
server.quit()
