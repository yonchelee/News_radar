"""이메일 발송 모듈.

Gmail App Password 방식으로 HTML 리포트를 발송한다.
환경변수(.env)에서 SMTP 설정을 읽는다.
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from analyst import AnalysisSummary, ArticleAnalysis

# .env 파일이 있으면 자동 로드
load_dotenv(Path(__file__).parent / ".env", override=False)


# ─────────────────────────────────────────────
# 이메일 설정 데이터클래스
# ─────────────────────────────────────────────
@dataclass
class EmailConfig:
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    sender_name: str = "뉴스레이더 자동발송"
    recipients: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "EmailConfig":
        recipients_raw = os.getenv("EMAIL_RECIPIENTS", "")
        recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
        return cls(
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            sender_name=os.getenv("EMAIL_SENDER_NAME", "뉴스레이더 자동발송"),
            recipients=recipients,
        )

    def is_valid(self) -> bool:
        return bool(self.smtp_user and self.smtp_password and self.recipients)


# ─────────────────────────────────────────────
# HTML 이메일 템플릿
# ─────────────────────────────────────────────
_SENTIMENT_COLOR = {
    "positive": ("#064E3B", "#6EE7B7", "▲ 긍정"),
    "negative": ("#7F1D1D", "#FCA5A5", "▼ 부정"),
    "neutral":  ("#1E3A5F", "#93C5FD", "● 중립"),
}

_PRIORITY_BADGE = {
    "urgent": ('<span style="background:#DC2626;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">🚨 긴급</span>', ),
    "high":   ('<span style="background:#D97706;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">⚠️ 중요</span>', ),
    "normal": ('<span style="background:#374151;color:#D1D5DB;padding:2px 8px;border-radius:4px;font-size:11px;">📄 일반</span>', ),
}


def _article_card_html(analysis: ArticleAnalysis, rank: int | None = None) -> str:
    bg, fg, label = _SENTIMENT_COLOR.get(
        analysis.sentiment, ("#1E3A5F", "#93C5FD", "● 중립")
    )
    priority_badge = _PRIORITY_BADGE.get(analysis.priority, _PRIORITY_BADGE["normal"])[0]
    rank_str = f"<span style='color:#94A3B8;font-size:13px;margin-right:8px;'>#{rank}</span>" if rank else ""

    pos_tags = "".join(
        f"<span style='background:#064E3B;color:#6EE7B7;padding:1px 6px;"
        f"border-radius:3px;font-size:11px;margin:2px;display:inline-block;'>{kw}</span>"
        for kw in analysis.matched_pos[:3]
    )
    neg_tags = "".join(
        f"<span style='background:#7F1D1D;color:#FCA5A5;padding:1px 6px;"
        f"border-radius:3px;font-size:11px;margin:2px;display:inline-block;'>{kw}</span>"
        for kw in analysis.matched_neg[:3]
    )

    return f"""
    <div style="background:#1E293B;border-left:4px solid {fg};border-radius:8px;
                padding:14px 16px;margin:10px 0;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
        {rank_str}{priority_badge}
        <span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;
                     font-size:11px;font-weight:600;">{label}</span>
        <span style="color:#64748B;font-size:11px;">{analysis.article.source or ''}</span>
      </div>
      <div style="color:#E2E8F0;font-size:14px;font-weight:600;line-height:1.5;margin-bottom:8px;">
        <a href="{analysis.article.link}" style="color:#E2E8F0;text-decoration:none;"
           target="_blank">{analysis.article.title}</a>
      </div>
      <div style="color:#94A3B8;font-size:12px;margin-bottom:8px;line-height:1.4;">
        {analysis.article.summary_raw[:200] + '…' if len(analysis.article.summary_raw) > 200 else analysis.article.summary_raw}
      </div>
      <div>{pos_tags}{neg_tags}</div>
      <div style="color:#475569;font-size:11px;margin-top:6px;">
        키워드: {analysis.article.matched_keyword} &nbsp;·&nbsp; {analysis.article.published}
      </div>
    </div>
    """


def build_html_report(
    summary: AnalysisSummary,
    report_type: str = "scheduled",
    trigger_keyword: str | None = None,
) -> str:
    """HTML 이메일 본문 생성."""
    now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    pos_pct = int(summary.positive_ratio * 100)
    neg_pct = int(summary.negative_ratio * 100)
    neu_pct = 100 - pos_pct - neg_pct

    if report_type == "urgent":
        subject_prefix = "🚨 [긴급 알림]"
        banner_color = "#7F1D1D"
        banner_msg = (
            f"긴급 트리거 키워드 <strong>'{trigger_keyword}'</strong> 가 감지되었습니다."
            if trigger_keyword else "긴급 키워드가 감지되어 즉시 발송합니다."
        )
    else:
        subject_prefix = "📊 [정기 리포트]"
        banner_color = "#0B1F3A"
        banner_msg = f"{now_str} 기준 정기 뉴스 분석 리포트입니다."

    # 감성 비율 바
    ratio_bar = f"""
    <div style="margin:16px 0;">
      <div style="display:flex;border-radius:6px;overflow:hidden;height:20px;">
        <div style="width:{pos_pct}%;background:#059669;"></div>
        <div style="width:{neg_pct}%;background:#DC2626;"></div>
        <div style="width:{neu_pct}%;background:#374151;"></div>
      </div>
      <div style="display:flex;gap:16px;margin-top:6px;font-size:12px;">
        <span style="color:#6EE7B7;">▲ 긍정 {pos_pct}% ({summary.positive_count}건)</span>
        <span style="color:#FCA5A5;">▼ 부정 {neg_pct}% ({summary.negative_count}건)</span>
        <span style="color:#93C5FD;">● 중립 {neu_pct}% ({summary.neutral_count}건)</span>
      </div>
    </div>
    """

    top_cards = "".join(
        _article_card_html(a, rank=i + 1) for i, a in enumerate(summary.top_articles)
    )

    urgent_section = ""
    if summary.urgent_articles:
        urgent_cards = "".join(_article_card_html(a) for a in summary.urgent_articles)
        urgent_section = f"""
        <div style="background:#450A0A;border:1px solid #DC2626;border-radius:10px;
                    padding:16px;margin:20px 0;">
          <h3 style="color:#FCA5A5;margin:0 0 12px;">🚨 긴급 모니터링 기사
              ({len(summary.urgent_articles)}건)</h3>
          {urgent_cards}
        </div>
        """

    return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>뉴스 레이더 리포트</title>
</head>
<body style="margin:0;padding:0;background:#0F172A;font-family:'Malgun Gothic',
             'Apple SD Gothic Neo',sans-serif;color:#E2E8F0;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:24px 16px;">
      <table width="640" cellpadding="0" cellspacing="0"
             style="max-width:640px;width:100%;">

        <!-- 헤더 -->
        <tr><td style="background:linear-gradient(90deg,{banner_color} 0%,#1F6FEB 100%);
                        padding:24px 28px;border-radius:12px 12px 0 0;">
          <div style="color:#fff;font-size:22px;font-weight:700;margin-bottom:4px;">
            📡 선행기구개발그룹 뉴스 레이더
          </div>
          <div style="color:rgba(255,255,255,0.8);font-size:13px;">
            {subject_prefix} &nbsp;·&nbsp; {banner_msg}
          </div>
        </td></tr>

        <!-- 본문 -->
        <tr><td style="background:#1E293B;padding:24px 28px;
                        border-radius:0 0 12px 12px;">

          <!-- 통계 카드 -->
          <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;">
            <div style="flex:1;min-width:100px;background:#0F172A;border-radius:8px;
                        padding:12px 16px;text-align:center;">
              <div style="font-size:24px;font-weight:700;color:#22D3EE;">
                {summary.total}
              </div>
              <div style="font-size:11px;color:#64748B;margin-top:2px;">수집 기사</div>
            </div>
            <div style="flex:1;min-width:100px;background:#0F172A;border-radius:8px;
                        padding:12px 16px;text-align:center;">
              <div style="font-size:24px;font-weight:700;color:#6EE7B7;">
                {summary.positive_count}
              </div>
              <div style="font-size:11px;color:#64748B;margin-top:2px;">긍정 기사</div>
            </div>
            <div style="flex:1;min-width:100px;background:#0F172A;border-radius:8px;
                        padding:12px 16px;text-align:center;">
              <div style="font-size:24px;font-weight:700;color:#FCA5A5;">
                {summary.negative_count}
              </div>
              <div style="font-size:11px;color:#64748B;margin-top:2px;">부정 기사</div>
            </div>
            <div style="flex:1;min-width:100px;background:#0F172A;border-radius:8px;
                        padding:12px 16px;text-align:center;">
              <div style="font-size:24px;font-weight:700;color:#F87171;">
                {summary.urgent_count}
              </div>
              <div style="font-size:11px;color:#64748B;margin-top:2px;">긴급 기사</div>
            </div>
          </div>

          <!-- 감성 비율 바 -->
          <div style="background:#0F172A;border-radius:8px;padding:14px 16px;
                      margin-bottom:20px;">
            <div style="font-size:13px;font-weight:600;color:#94A3B8;
                        margin-bottom:8px;">감성 분포</div>
            {ratio_bar}
          </div>

          <!-- 긴급 기사 -->
          {urgent_section}

          <!-- TOP 기사 -->
          <h3 style="color:#22D3EE;font-size:15px;margin:20px 0 10px;
                     border-bottom:1px solid #334155;padding-bottom:8px;">
            🔥 주요 기사 TOP {len(summary.top_articles)}
          </h3>
          {top_cards}

          <!-- 푸터 -->
          <div style="margin-top:28px;padding-top:16px;border-top:1px solid #334155;
                      color:#475569;font-size:11px;text-align:center;line-height:1.6;">
            본 메일은 선행기구개발그룹 뉴스 레이더 시스템에 의해 자동 발송되었습니다.<br>
            발송 시각: {now_str} (KST) &nbsp;·&nbsp;
            Google News RSS 기반 수집
          </div>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


# ─────────────────────────────────────────────
# 발송 함수
# ─────────────────────────────────────────────
def send_report(
    summary: AnalysisSummary,
    config: EmailConfig,
    report_type: str = "scheduled",
    trigger_keyword: str | None = None,
    extra_recipients: list[str] | None = None,
) -> tuple[bool, str]:
    """HTML 리포트 이메일 발송.

    Returns:
        (success, message) 튜플
    """
    if not config.is_valid():
        return False, "이메일 설정이 불완전합니다. SMTP 계정과 수신자를 확인하세요."

    recipients = list(config.recipients)
    if extra_recipients:
        recipients += [r for r in extra_recipients if r not in recipients]
    if not recipients:
        return False, "수신자 목록이 비어 있습니다."

    html_body = build_html_report(summary, report_type, trigger_keyword)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if report_type == "urgent":
        subject = f"🚨 [긴급] 뉴스 레이더 알림 - {trigger_keyword or '키워드 감지'} ({now_str})"
    else:
        subject = f"📊 [정기] 선행기구개발그룹 뉴스 레이더 리포트 ({now_str})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config.sender_name} <{config.smtp_user}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(config.smtp_user, config.smtp_password)
            server.sendmail(config.smtp_user, recipients, msg.as_string())
        return True, f"발송 완료 → {', '.join(recipients)}"
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP 인증 실패. Gmail App Password를 확인하세요."
    except smtplib.SMTPException as exc:
        return False, f"SMTP 오류: {exc}"
    except Exception as exc:
        return False, f"발송 실패: {exc}"


def send_test_email(
    to_address: str,
    config: EmailConfig,
) -> tuple[bool, str]:
    """테스트 이메일 발송 (더미 데이터 사용)."""
    from analyst import AnalysisSummary, ArticleAnalysis
    from news_crawler import Article

    dummy_article = Article(
        title="[테스트] 삼성전자 차세대 폴더블 힌지 양산 공정 개선",
        link="https://example.com",
        source="테스트 뉴스",
        published="Mon, 01 Jan 2025 09:00:00 GMT",
        summary_raw="삼성전자가 갤럭시 Z폴드 시리즈의 힌지 내구성을 30% 개선한 "
                    "차세대 힌지 모듈을 2026년 상반기 양산 목표로 개발 중이다.",
        matched_keyword="갤럭시 폴드 힌지",
    )
    from analyst import ArticleAnalysis as AA
    dummy_analysis = AA(
        article=dummy_article,
        sentiment="positive",
        sentiment_score=0.7,
        priority="high",
        matched_pos=["양산", "개선"],
        matched_neg=[],
        is_urgent=False,
    )
    dummy_summary = AnalysisSummary(
        total=10,
        positive_count=6,
        negative_count=2,
        neutral_count=2,
        urgent_count=0,
        top_articles=[dummy_analysis],
        urgent_articles=[],
    )

    test_config = EmailConfig(
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password=config.smtp_password,
        sender_name=config.sender_name,
        recipients=[to_address],
    )

    return send_report(dummy_summary, test_config, report_type="scheduled")


# ─────────────────────────────────────────────
# 스케줄 / 트리거 판별
# ─────────────────────────────────────────────
def should_send_scheduled(
    scheduled_hour: int,
    scheduled_minute: int,
    last_sent_ts: float | None,
) -> bool:
    """현재 시각이 발송 시각이고 마지막 발송 후 23시간 이상 경과했으면 True."""
    now = datetime.now()
    if now.hour != scheduled_hour or now.minute != scheduled_minute:
        return False
    if last_sent_ts is None:
        return True
    import time
    return (time.time() - last_sent_ts) > 23 * 3600
