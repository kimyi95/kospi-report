from datetime import datetime, timedelta
from email.mime.text import MIMEText
import os
import smtplib

from pykrx import stock


def fmt_pct(x):
    return f"{x:+.2f}%"


today_dt = datetime.now()

date = None
kospi = None

for i in range(10):
    check_date = (today_dt - timedelta(days=i)).strftime("%Y%m%d")

    try:
        temp = stock.get_index_ohlcv_by_date(
            check_date,
            check_date,
            "1001"
        )

        if not temp.empty:
            date = check_date
            kospi = temp
            break

    except Exception:
        pass

if date is None:
    raise Exception("최근 10일 내 KOSPI 데이터를 찾지 못했습니다.")

kospi_return = float(kospi["등락률"].iloc[-1])

cap = stock.get_market_cap_by_ticker(date, market="KOSPI")
price = stock.get_market_ohlcv_by_ticker(date, market="KOSPI")

df = cap.join(price[["등락률"]])

df = (
    df.sort_values("시가총액", ascending=False)
    .head(100)
)

df["종목명"] = [
    stock.get_market_ticker_name(ticker)
    for ticker in df.index
]

df["초과수익률"] = df["등락률"] - kospi_return

result = df[df["등락률"] > kospi_return]

result = result.sort_values(
    "초과수익률",
    ascending=False
)

body = f"""
KOSPI 상대강세 리포트

기준일 : {date}

KOSPI 등락률 : {fmt_pct(kospi_return)}

시총 상위 100개 중
상대강세 종목 수 : {len(result)}개

"""

if result.empty:
    body += "조건을 만족하는 종목이 없습니다.\n"

else:
    for i, (_, row) in enumerate(
        result.iterrows(),
        1
    ):
        body += (
            f"{i}. {row['종목명']} "
            f"/ 등락률 {fmt_pct(row['등락률'])} "
            f"/ 초과수익률 {fmt_pct(row['초과수익률'])}p\n"
        )

body += """

※ KOSPI 상승일 :
종목 등락률 > KOSPI 등락률

※ KOSPI 하락일 :
KOSPI보다 덜 하락했거나 상승한 종목

※ 투자 참고용 자료입니다.
"""

msg = MIMEText(
    body,
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
