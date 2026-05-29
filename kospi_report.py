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
        s = str(x).strip()
        s = s.split()[0]
        s = s.replace(",", "")
        s = s.replace("+", "")
        s = s.replace("상한가", "")
        s = s.replace("하한가", "")
        s = s.replace("보합", "")

        return int(float(s))

    except:
        return 0

        return int(digits)

    except:
        return 0


def get_kospi_return():
    url = "https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page=1"
    html = get_html(url)
    df = pd.read_html(StringIO(html))[0].dropna()
    latest = df.iloc[0]

    return str(latest["날짜"]), to_float_pct(latest["등락률"])


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


date, kospi_return = get_kospi_return()
df = get_top100_kospi()

etf_keywords = [
    "KODEX", "TIGER", "KOSEF", "KBSTAR",
    "ARIRANG", "HANARO", "SOL", "ACE"
]

for keyword in etf_keywords:
    df = df[~df["종목명"].str.contains(keyword, na=False)]

df["초과수익률"] = df["등락률"] - kospi_return

result = df[df["등락률"] > kospi_return]
result = result.sort_values("초과수익률", ascending=False)

rows_html = ""

for i, row in enumerate(result.itertuples(), 1):
    rows_html += f"""
    <tr>
        <td>{i}</td>
        <td>{row.종목명}</td>
        <td>{row.현재가:,}</td>
        <td>{row.등락률:+.2f}%</td>
        <td>{row.초과수익률:+.2f}%p</td>
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
</tr>

{rows_html}

</table>

<br>

<p><b>선별 기준</b></p>
<ul>
<li>KOSPI 상승일 : 종목 등락률 &gt; KOSPI 등락률</li>
<li>KOSPI 하락일 : KOSPI보다 덜 하락했거나 상승</li>
</ul>

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
