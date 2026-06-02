from email.mime.text import MIMEText
from io import StringIO
import os
import smtplib

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0"}
HISTORY_FILE = "history.csv"


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


def fmt_pct(x):
    try:
        return f"{float(x):+.2f}%"
    except:
        return "-"


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


def get_stock_price_history(code, pages=10):
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
            if date in stock_returns and stock_returns[date] > kospi_ret:
                count += 1

        return count
    except:
        return "확인불가"


def get_high_status(code, current_price):
    try:
        df = get_stock_price_history(code, pages=10)

        if df.empty:
            return "확인불가"

        recent = df.head(100)

        if len(recent) < 40:
            return "확인불가"

        high_price = recent["종가"].max()

        if high_price <= 0 or current_price <= 0:
            return "확인불가"

        gap_pct = (current_price / high_price - 1) * 100

        if current_price >= high_price:
            return f"🚀 +{gap_pct:.1f}%"

        if current_price >= high_price * 0.97:
            return f"🔥 {gap_pct:.1f}%"

        return f"{gap_pct:.1f}%"
    except:
        return "확인불가"


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return pd.DataFrame()

    try:
        return pd.read_csv(HISTORY_FILE)
    except:
        return pd.DataFrame()


def get_yesterday_from_history(history, today):
    if history.empty or "날짜" not in history.columns:
        return pd.DataFrame()

    dates = sorted(history["날짜"].astype(str).unique())
    previous_dates = [d for d in dates if d != today]

    if not previous_dates:
        return pd.DataFrame()

    yesterday = previous_dates[-1]
    return history[history["날짜"].astype(str) == yesterday].copy()


def get_streak_count(stock_name, history, today_result):
    try:
        count = 0

        if stock_name in set(today_result["종목명"].astype(str)):
            count += 1
        else:
            return 0

        if history.empty or "날짜" not in history.columns:
            return count

        hist = history.copy()
        hist["날짜"] = hist["날짜"].astype(str)

        dates = sorted(hist["날짜"].unique(), reverse=True)

        for d in dates:
            day_names = set(hist[hist["날짜"] == d]["종목명"].astype(str))

            if stock_name in day_names:
                count += 1
            else:
                break

        return count
    except:
        return "확인불가"


def get_dropped_stocks(yesterday_df, today_all_df, today_result):
    if yesterday_df.empty:
        return pd.DataFrame()

    today_names = set(today_result["종목명"].astype(str))

    dropped = yesterday_df[
        ~yesterday_df["종목명"].astype(str).isin(today_names)
    ].copy()

    if dropped.empty:
        return dropped

    today_lookup = today_all_df[["종목명", "등락률"]].copy()
    today_lookup = today_lookup.rename(columns={"등락률": "오늘등락률"})

    dropped = dropped.merge(today_lookup, on="종목명", how="left")

    return dropped


def save_history(today, result):
    save_df = result[
        ["종목명", "등락률", "최근2주출현", "연속출현", "전고점상태"]
    ].copy()

    save_df.insert(0, "날짜", today)

    history = load_history()

    if not history.empty:
        history = history[history["날짜"].astype(str) != str(today)]
        history = pd.concat([history, save_df], ignore_index=True)
    else:
        history = save_df

    history.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")


def make_reason(row):
    reasons = []

    if isinstance(row.최근2주출현, int) and row.최근2주출현 >= 5:
        reasons.append(f"최근2주출현 {row.최근2주출현}회")

    if isinstance(row.연속출현, int) and row.연속출현 >= 2:
        reasons.append(f"연속출현 {row.연속출현}일")

    if "🚀" in str(row.전고점상태):
        reasons.append(f"전고점 돌파({row.전고점상태})")
    elif "🔥" in str(row.전고점상태):
        reasons.append(f"전고점 근접({row.전고점상태})")

    if not reasons:
        reasons.append("상대강세 유지")

    return ", ".join(reasons)


def is_meaningful_stock(name):
    exclude_keywords = [
        "LG전자", "LG씨엔에스", "LG이노텍", "LG", "LG디스플레이", "LG화학", "LG에너지솔루션",
        "삼성전기", "삼성에스디에스",
        "현대오토에버", "현대모비스", "현대차", "현대글로비스",
        "대덕전자", "NAVER"
    ]

    return not any(keyword == name for keyword in exclude_keywords)


date, kospi_return = get_kospi_return()
kospi_recent_returns = get_kospi_recent_returns()

df = get_top100_kospi()

etf_keywords = [
    "KODEX", "TIGER", "KOSEF", "KBSTAR",
    "ARIRANG", "HANARO", "SOL", "ACE"
]

for keyword in etf_keywords:
    df = df[~df["종목명"].str.contains(keyword, na=False)]

result = df[df["등락률"] > kospi_return].copy()
result = result.sort_values("등락률", ascending=False)

result["최근2주출현"] = result["종목코드"].apply(
    lambda code: get_recent_outperform_count(code, kospi_recent_returns, date)
)

result["전고점상태"] = result.apply(
    lambda row: get_high_status(row["종목코드"], row["현재가"]),
    axis=1
)

history = load_history()

result["연속출현"] = result["종목명"].apply(
    lambda name: get_streak_count(name, history, result)
)

yesterday_df = get_yesterday_from_history(history, date)
dropped = get_dropped_stocks(yesterday_df, df, result)


rows_html = ""

for i, row in enumerate(result.itertuples(), 1):
    recent_text = f"{row.최근2주출현}회" if isinstance(row.최근2주출현, int) else row.최근2주출현
    streak_text = f"{row.연속출현}일" if isinstance(row.연속출현, int) else row.연속출현

    rows_html += f"""
    <tr>
        <td>{i}</td>
        <td>{row.종목명}</td>
        <td>{row.현재가:,}</td>
        <td>{row.등락률:+.2f}%</td>
        <td>{recent_text}</td>
        <td>{streak_text}</td>
        <td>{row.전고점상태}</td>
    </tr>
    """


valid_counts = result[result["최근2주출현"].apply(lambda x: isinstance(x, int))]
valid_counts = valid_counts.sort_values("최근2주출현", ascending=False).head(5)

top5_html = ""

for i, row in enumerate(valid_counts.itertuples(), 1):
    streak_text = f"{row.연속출현}일" if isinstance(row.연속출현, int) else row.연속출현

    top5_html += f"""
    <tr>
        <td>{i}</td>
        <td>{row.종목명}</td>
        <td>{row.최근2주출현}회</td>
        <td>{streak_text}</td>
        <td>{row.전고점상태}</td>
    </tr>
    """


hidden = result.copy()
hidden = hidden[
    hidden["종목명"].apply(is_meaningful_stock)
]

hidden = hidden[
    hidden["최근2주출현"].apply(lambda x: isinstance(x, int) and x >= 4)
]

hidden = hidden.sort_values(["최근2주출현", "등락률"], ascending=False).head(3)

hidden_html = ""

if hidden.empty:
    hidden_html = """
    <tr>
        <td colspan="2">해당 종목 없음</td>
    </tr>
    """
else:
    for row in hidden.itertuples():
        hidden_html += f"""
        <tr>
            <td>{row.종목명}</td>
            <td>{make_reason(row)}</td>
        </tr>
        """


meaningful = result.copy()

median_return = result["등락률"].median()

meaningful = meaningful[
    meaningful["최근2주출현"].apply(lambda x: isinstance(x, int) and x >= 4)
]

meaningful = meaningful[
    meaningful["등락률"] <= median_return
]

meaningful = meaningful.sort_values(
    ["최근2주출현", "연속출현", "등락률"],
    ascending=False
).head(5)

meaningful_html = ""

if meaningful.empty:
    meaningful_html = """
    <tr>
        <td colspan="2">해당 종목 없음</td>
    </tr>
    """
else:
    for row in meaningful.itertuples():
        meaningful_html += f"""
        <tr>
            <td>{row.종목명}</td>
            <td>{make_reason(row)}</td>
        </tr>
        """


breakout = result[result["전고점상태"].astype(str).str.contains("🚀|🔥", na=False)]

breakout_html = ""

if breakout.empty:
    breakout_html = "<li>전고점 돌파/근접 종목 없음</li>"
else:
    for row in breakout.itertuples():
        breakout_html += f"<li>{row.종목명} - {row.전고점상태}</li>"


dropped_html = ""

if dropped.empty:
    dropped_html = """
    <tr>
        <td colspan="4">해당 종목 없음</td>
    </tr>
    """
else:
    for row in dropped.itertuples():
        yesterday_return = getattr(row, "등락률", None)
        today_return = getattr(row, "오늘등락률", None)
        recent_count = getattr(row, "최근2주출현", "-")

        recent_text = f"{recent_count}회" if isinstance(recent_count, int) else str(recent_count)

        dropped_html += f"""
        <tr>
            <td>{row.종목명}</td>
            <td>{fmt_pct(yesterday_return)}</td>
            <td>{fmt_pct(today_return)}</td>
            <td>{recent_text}</td>
        </tr>
        """


html_body = f"""
<html>
<body>

<h2>KOSPI 상대강세 리포트</h2>

<h3>1. 시장 요약</h3>
<p><b>기준일 :</b> {date}</p>
<p><b>KOSPI 등락률 :</b> {kospi_return:+.2f}%</p>
<p><b>상대강세 종목 수 :</b> {len(result)}개</p>

<h3>2. 상대강세 종목 전체표</h3>
<table border="1" cellpadding="5" cellspacing="0">
<tr>
<th>순위</th>
<th>종목명</th>
<th>현재가</th>
<th>등락률</th>
<th>최근2주출현</th>
<th>연속출현</th>
<th>전고점대비</th>
</tr>
{rows_html}
</table>

<br>

<h3>3. 최근2주 반복 출현 TOP5</h3>
<table border="1" cellpadding="5" cellspacing="0">
<tr>
<th>순위</th>
<th>종목명</th>
<th>최근2주출현</th>
<th>연속출현</th>
<th>전고점대비</th>
</tr>
{top5_html}
</table>

<br>

<h3>4. 오늘의 핵심</h3>
<ul>
<li><b>LG 그룹:</b> LG전자, LG씨엔에스, LG이노텍, LG 등 그룹주 강세 여부 확인</li>
<li><b>AI / IT 인프라:</b> 삼성전기, 삼성에스디에스, 대덕전자, NAVER 등 강세 여부 확인</li>
<li><b>자동차 전장:</b> 현대오토에버, 현대모비스, 현대차 등 강세 여부 확인</li>
<li><b>전고점 돌파:</b> 전고점 대비 플러스 종목이 많을수록 시장 에너지가 강한 것으로 해석</li>
</ul>

<h3>5. 숨은 강세주 TOP3</h3>
<table border="1" cellpadding="5" cellspacing="0">
<tr>
<th>종목명</th>
<th>선정 이유</th>
</tr>
{hidden_html}
</table>

<br>

<h3>6. 의미있는 강세주</h3>
<p>최근2주출현이 높지만 당일 급등 상위권은 아닌, 조용하게 강한 종목입니다.</p>
<table border="1" cellpadding="5" cellspacing="0">
<tr>
<th>종목명</th>
<th>선정 이유</th>
</tr>
{meaningful_html}
</table>

<br>

<h3>7. 다음 거래일 체크포인트</h3>
<ul>
<li>최근2주출현 TOP 종목이 다음 거래일에도 유지되는지 확인</li>
<li>연속출현이 증가하는 종목 우선 관찰</li>
<li>전고점 대비 플러스 종목이 돌파 후 버티는지 확인</li>
<li>의미있는 강세주가 계속 상대강세 목록에 남는지 확인</li>
<li>어제 있었지만 오늘 탈락한 종목은 강세 이탈 여부 확인</li>
</ul>

<h3>8. 어제 있었지만 오늘 탈락한 종목</h3>
<table border="1" cellpadding="5" cellspacing="0">
<tr>
<th>종목</th>
<th>어제 등락률</th>
<th>오늘 등락률</th>
<th>최근2주출현</th>
</tr>
{dropped_html}
</table>

<br>

<p><b>선별 기준</b></p>
<ul>
<li>KOSPI 상승일 : 종목 등락률 &gt; KOSPI 등락률</li>
<li>KOSPI 하락일 : KOSPI보다 덜 하락했거나 상승</li>
</ul>

<p>※ 최근2주출현 = 최근 10거래일 동안 KOSPI보다 강했던 횟수입니다.</p>
<p>※ 연속출현 = 직전 리포트부터 오늘까지 연속으로 상대강세 목록에 포함된 일수입니다.</p>
<p>※ 전고점대비 = 최근 약 100거래일 최고 종가 대비 현재가 위치입니다.</p>
<p>※ 의미있는 강세주 = 최근2주출현 4회 이상이면서 당일 등락률이 상대강세 종목 중간값 이하인 종목입니다.</p>
<p>※ 탈락 종목은 직전 리포트에는 있었으나 오늘 상대강세 조건을 만족하지 못한 종목입니다.</p>
<p>※ 데이터 출처 : 네이버 금융</p>
<p>※ 투자 참고용 자료입니다.</p>

</body>
</html>
"""

save_history(date, result)

msg = MIMEText(html_body, "html", _charset="utf-8")
msg["Subject"] = f"[KOSPI 상대강세] {date}"
msg["From"] = os.environ["EMAIL_ADDRESS"]
msg["To"] = os.environ["RECEIVER_EMAIL"]

server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
server.login(os.environ["EMAIL_ADDRESS"], os.environ["EMAIL_PASSWORD"])
server.send_message(msg)
server.quit()
