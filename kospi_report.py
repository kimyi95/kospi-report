from datetime import datetime
from email.mime.text import MIMEText
import os
import smtplib

msg = MIMEText(
    f"""
KOSPI 상대강세 리포트

생성일시:
{datetime.now()}

(테스트 메일)

이메일 자동 발송이 정상 동작합니다.
"""
)

msg["Subject"] = "KOSPI 리포트 테스트"
msg["From"] = os.environ["EMAIL_ADDRESS"]
msg["To"] = os.environ["RECEIVER_EMAIL"]

server = smtplib.SMTP_SSL("smtp.gmail.com", 465)

server.login(
    os.environ["EMAIL_ADDRESS"],
    os.environ["EMAIL_PASSWORD"]
)

server.send_message(msg)
server.quit()
