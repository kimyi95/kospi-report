from datetime import datetime
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


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.encoding = "utf-8"
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


def get_kospi_return():

    url = (
        "https://finance.naver.com/"
        "sise/sise_index_day.naver?code=KOSPI&page=1"
    )

    html = requests.get(
        url,
        headers=HEADERS,
        timeout=20
    )

    html.encoding = "euc-kr"

    tables = pd.read_html(StringIO(html.text))

    df = tables[0].dropna()

    latest = df.iloc[0]

    return (
        str(latest["날짜"]),
        to_float_pct(latest["등락률"])
    )


def get_top100_kospi():

    dfs = []

    for page in [1, 2]:

        url = (
            "https://finance.naver.com/"
            f"sise/sise_market_sum.naver?sosok=0&page={page}"
        )

        html = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        html.encoding = "euc-kr"

        tables = pd.read_html(
            StringIO(html.text)
        )

        df = tables[1]

        df = df.dropna(
            subset=["종목명"]
        )

        dfs.append(df)

    df = pd.concat(
        dfs,
        ignore_index=True
    )

    df = df.head(100)

    df["등락률"] = df["등락률"].apply(
        to_float_pct
    )

    return df


def get_news(stock_name):

    try:

        url = (
            "https://search.naver.com/search.naver?"
            f"where=news&query={stock_name}"
        )

        html = get_html(url)

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        news = soup.select_one(
            "a.news_tit"
        )

        if news:
            return news.get_text(
                strip=True
            )

    except:
        pass

    return "관련 뉴스 없음"


date, kospi_return = get_kospi_return()

df = get_top100_kospi()

# ETF 제거
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
        ~df["종목명"].str.contains(
            keyword,
            na=False
        )
    ]

df["초과수익률"] = (
    df["등락률"] - kospi_return
)

result = df[
    df["등락률"] > kospi_return
]

result = result.sort_values(
    "초과수익률",
    ascending=False
)

body = f"""
KOSPI 상대강세 리포트

기준일 : {date}

KOSPI 등락률 : {kospi_return:+.2f}%

시총 상위 100개 기준
상대강세 종목 수 : {len(result)}개

TOP 10

"""

top10 = result.head(10)

for i, row in enumerate(
    top10.itertuples(),
    1
):

    news = get_news(
        row.종목명
    )

    body += (
        f"{i}. {row.종목명}\n"
        f"등락률 : {row.등락률:+.2f}%\n"
        f"초과수익률 : {row.초과수익률:+.2f}%p\n"
        f"뉴스 : {news}\n\n"
    )

body += """
선별 기준

- KOSPI 상승일 :
  종목 등락률 > KOSPI 등락률

- KOSPI 하락일 :
  KOSPI보다 덜 하락했거나 상승

※ 데이터 출처 : 네이버 금융
※ 투자 참고용 자료입니다.
"""

msg = MIMEText(
    body,
    _charset="utf-8"
)

msg["Subject"] = (
    f"[KOSPI 상대강세] {date}"
)

msg["From"] = os.environ[
    "EMAIL_ADDRESS"
]

msg["To"] = os.environ[
    "RECEIVER_EMAIL"
]

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
