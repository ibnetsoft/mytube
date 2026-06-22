# -*- coding: utf-8 -*-
"""
SMTP 이메일 발송 서비스 (Gmail)
Python 내장 smtplib 사용 — 추가 패키지 불필요
"""

import os
import smtplib
import random
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def _send_email(to: str, subject: str, html_body: str) -> bool:
    """기본 SMTP 발송 함수"""
    if not SMTP_USER or not SMTP_PASS:
        print("[EmailService] SMTP 설정이 없습니다.")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, to, msg.as_string())
        print(f"[EmailService] 발송 완료 → {to}")
        return True
    except Exception as e:
        print(f"[EmailService] 발송 실패: {e}")
        return False


def generate_temp_password(length: int = 10) -> str:
    """대소문자+숫자+특수문자 조합 임시 비밀번호 생성"""
    chars = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pw = "".join(random.choices(chars, k=length))
        if (
            any(c.isupper() for c in pw)
            and any(c.islower() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in "!@#$%" for c in pw)
        ):
            return pw


def generate_verify_code() -> str:
    """6자리 숫자 인증 코드 생성"""
    return str(random.randint(100000, 999999))


def send_temp_password(to: str, temp_pw: str) -> bool:
    """임시 비밀번호 이메일 발송"""
    subject = "[Picadilly Studio] 임시 비밀번호 안내"
    html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0b0f19;font-family:'Noto Sans KR',sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#1e293b;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);">
    <div style="background:linear-gradient(135deg,#1e40af,#3b82f6);padding:32px;text-align:center;">
      <div style="display:inline-flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span style="width:10px;height:10px;border-radius:50%;background:#60a5fa;display:inline-block;"></span>
        <span style="color:#bfdbfe;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;">PICADILLY STUDIO</span>
      </div>
      <h1 style="color:#fff;font-size:22px;font-weight:900;margin:0;">임시 비밀번호 안내</h1>
    </div>
    <div style="padding:32px;">
      <p style="color:#94a3b8;font-size:14px;line-height:1.7;margin:0 0 24px;">
        안녕하세요.<br>
        비밀번호 재설정 요청이 접수되어 임시 비밀번호를 발급해 드립니다.
      </p>
      <div style="background:#0f172a;border:1px solid rgba(59,130,246,0.3);border-radius:12px;padding:20px;text-align:center;margin-bottom:24px;">
        <p style="color:#94a3b8;font-size:12px;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">임시 비밀번호</p>
        <p style="color:#60a5fa;font-size:28px;font-weight:900;letter-spacing:4px;margin:0;font-family:monospace;">{temp_pw}</p>
      </div>
      <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:8px;padding:14px;margin-bottom:24px;">
        <p style="color:#fbbf24;font-size:12px;margin:0;">
          ⚠️ 로그인 후 반드시 설정 페이지에서 비밀번호를 변경해 주세요.<br>
          본인이 요청하지 않은 경우 즉시 관리자에게 문의하세요.
        </p>
      </div>
      <p style="color:#475569;font-size:11px;text-align:center;margin:0;">
        이 메일은 발신 전용입니다. 회신하지 마세요.
      </p>
    </div>
  </div>
</body>
</html>
"""
    return _send_email(to, subject, html)


def send_verify_code(to: str, code: str) -> bool:
    """이메일 인증 코드 발송"""
    subject = "[Picadilly Studio] 이메일 인증 코드"
    html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0b0f19;font-family:'Noto Sans KR',sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#1e293b;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);">
    <div style="background:linear-gradient(135deg,#1e40af,#3b82f6);padding:32px;text-align:center;">
      <div style="display:inline-flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span style="width:10px;height:10px;border-radius:50%;background:#60a5fa;display:inline-block;"></span>
        <span style="color:#bfdbfe;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;">PICADILLY STUDIO</span>
      </div>
      <h1 style="color:#fff;font-size:22px;font-weight:900;margin:0;">이메일 인증 코드</h1>
    </div>
    <div style="padding:32px;">
      <p style="color:#94a3b8;font-size:14px;line-height:1.7;margin:0 0 24px;">
        안녕하세요.<br>
        회원가입 이메일 인증 코드를 안내해 드립니다.
      </p>
      <div style="background:#0f172a;border:1px solid rgba(59,130,246,0.3);border-radius:12px;padding:20px;text-align:center;margin-bottom:24px;">
        <p style="color:#94a3b8;font-size:12px;margin:0 0 8px;text-transform:uppercase;letter-spacing:1px;">인증 코드 (10분 유효)</p>
        <p style="color:#60a5fa;font-size:40px;font-weight:900;letter-spacing:8px;margin:0;font-family:monospace;">{code}</p>
      </div>
      <div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:8px;padding:14px;margin-bottom:24px;">
        <p style="color:#f87171;font-size:12px;margin:0;">
          ⏱️ 이 코드는 발송 후 10분간만 유효합니다.<br>
          본인이 요청하지 않은 경우 이 메일을 무시해 주세요.
        </p>
      </div>
      <p style="color:#475569;font-size:11px;text-align:center;margin:0;">
        이 메일은 발신 전용입니다. 회신하지 마세요.
      </p>
    </div>
  </div>
</body>
</html>
"""
    return _send_email(to, subject, html)


def send_withdrawal_email(to: str) -> bool:
    """회원 탈퇴 완료 이메일 발송"""
    subject = "[Picadilly Studio] 회원 탈퇴 처리 완료 안내"
    html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0b0f19;font-family:'Noto Sans KR',sans-serif;">
  <div style="max-width:480px;margin:40px auto;background:#1e293b;border-radius:16px;overflow:hidden;border:1px solid rgba(255,255,255,0.08);">
    <div style="background:linear-gradient(135deg,#ef4444,#dc2626);padding:32px;text-align:center;">
      <div style="display:inline-flex;align-items:center;gap:8px;margin-bottom:8px;">
        <span style="width:10px;height:10px;border-radius:50%;background:#f87171;display:inline-block;"></span>
        <span style="color:#fee2e2;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;">PICADILLY STUDIO</span>
      </div>
      <h1 style="color:#fff;font-size:22px;font-weight:900;margin:0;">회원 탈퇴 완료</h1>
    </div>
    <div style="padding:32px;">
      <p style="color:#94a3b8;font-size:14px;line-height:1.7;margin:0 0 24px;">
        안녕하세요.<br>
        요청하신 회원 탈퇴 처리가 완료되었습니다.
      </p>
      <div style="background:#0f172a;border:1px solid rgba(239,68,68,0.3);border-radius:12px;padding:20px;margin-bottom:24px;">
        <p style="color:#f87171;font-size:13px;font-weight:bold;margin:0 0 8px;">삭제 완료된 데이터 내역</p>
        <ul style="color:#94a3b8;font-size:12px;margin:0;padding-left:20px;line-height:1.6;">
          <li>작업했던 모든 프로젝트 및 설정 내역</li>
          <li>수당 내역 및 정산 정보</li>
          <li>지갑 정보 및 추천인 혜택</li>
        </ul>
      </div>
      <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:8px;padding:14px;margin-bottom:24px;">
        <p style="color:#fbbf24;font-size:12px;margin:0;">
          ⚠️ 탈퇴된 계정의 데이터는 즉시 파기되며, 영구적으로 복구할 수 없습니다.
        </p>
      </div>
      <p style="color:#475569;font-size:11px;text-align:center;margin:0;">
        이 메일은 발신 전용입니다. 회신하지 마세요.
      </p>
    </div>
  </div>
</body>
</html>
"""
    return _send_email(to, subject, html)

