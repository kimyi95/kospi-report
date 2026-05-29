from datetime import datetime
from email.mime.text import MIMEText
from io import StringIO
import os
import smtplib
import requests
import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.encoding = "euc-kr"
    r.raise_for_status()
    return r.text


def to_float_pct(x):
    return float(str(x).replace("%", "").replace("+", "").strip())


def get_kospi_return():
    url = "https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page=1"
    html = get_html(url)
    tables = pd.read_html(StringIO(html))
    df = tables[0].dropna()
    latest = df.iloc[0]
    return str(latest["날짜"]), to_float_pct(latest["등락률"])


def get_top100_kospi():
    dfs = []

    for page in [1, 2]:
        url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page={page}"
        html = get_html(url)
        tables = pd.read_html(StringIO(html))
        df = tables[1]
        df = df.dropna(subset=["종목명"])
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True).head(100)
    df["등락률"] = df["등락률"].apply(to_float_pct)
    return df


date, kospi_return = get_kospi_return()
df = get_top100_kospi()

df["초과수익률"] = df["등락률"] - kospi_return

result = df[df["등락률"] > kospi_return]
result = result.sort_values("초과수익률", ascending=False)

body = f"""
KOSPI 상대강세 리포트

기준일: {date}
KOSPI 등락률: {kospi_return:+.2f}%

선별 기준:
- KOSPI 상승일: 종목 등락률 > KOSPI 등락률
- KOSPI 하락일: KOSPI보다 덜 하락했거나 상승한 종목

시총 상위 100개 중 상대강세 종목 수: {len(result)}개

"""

if result.empty:
    body += "조건을 만족하는 종목이 없습니다.\n"
else:
    for i, row in enumerate(result.itertuples(), 1):
        body += (
            f"{i}. {row.종목명} "
            f"/ 등락률 {row.등락률:+.2f}% "
            f"/ 초과수익률 {row.초과수익률:+.2f}%p\n"
        )

body += """

※ 데이터 출처: 네이버 금융
※ 주요 뉴스/이슈는 현재 버전에는 포함되지 않습니다.
※ 투자 참고용 자료이며 매수/매도 추천이 아닙니다.
"""

msg = MIMEText(body, _charset="utf-8")
msg["Subject"] = f"[KOSPI 상대강세] {date}"
msg["From"] = os.environ["EMAIL_ADDRESS"]
msg["To"] = os.environ["RECEIVER_EMAIL"]

server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
server.login(os.environ["EMAIL_ADDRESS"], os.environ["EMAIL_PASSWORD"])
server.send_message(msg)
server.quit()
