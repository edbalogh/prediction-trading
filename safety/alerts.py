from __future__ import annotations

import logging
import smtplib
import sys
from dataclasses import dataclass, field
from email.mime.text import MIMEText

from safety.types import AlertEvent

_logger = logging.getLogger("safety.alerts")


@dataclass
class AlertConfig:
    console: bool = True
    email: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_from: str = "alerts@nautilus-plus.local"
    smtp_to: list[str] = field(default_factory=list)
    halt_on_critical: bool = False


class AlertDispatcher:
    def __init__(self, config: AlertConfig) -> None:
        self._config = config

    def dispatch(self, event: AlertEvent) -> None:
        if self._config.console:
            self._log(event)
        if self._config.email:
            self._send_email(event)
        if self._config.halt_on_critical and event.level == "CRITICAL":
            sys.exit(f"HALT: {event.message}")

    def _log(self, event: AlertEvent) -> None:
        level = getattr(logging, event.level, logging.WARNING)
        _logger.log(level, "[%s] %s | context=%s", event.level, event.message, event.context)

    def _send_email(self, event: AlertEvent) -> None:
        body = f"Level: {event.level}\nMessage: {event.message}\nContext: {event.context}\nTimestamp: {event.ts}"
        msg = MIMEText(body)
        msg["Subject"] = f"[nautilus-plus] {event.level}: {event.message[:80]}"
        msg["From"] = self._config.smtp_from
        msg["To"] = ", ".join(self._config.smtp_to)
        try:
            with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as smtp:
                smtp.sendmail(self._config.smtp_from, self._config.smtp_to, msg.as_string())
        except Exception:
            _logger.exception("failed to send alert email for event: %s", event.message)
