import pytest
from unittest.mock import patch, MagicMock
from safety.alerts import AlertDispatcher, AlertConfig
from safety.types import AlertEvent


@pytest.fixture()
def console_only_config():
    return AlertConfig(console=True, email=False)


@pytest.fixture()
def email_config():
    return AlertConfig(
        console=True,
        email=True,
        smtp_host="localhost",
        smtp_port=1025,
        smtp_from="alerts@nautilus-plus.local",
        smtp_to=["trader@example.com"],
    )


def test_dispatch_logs_to_console(console_only_config, caplog):
    import logging
    dispatcher = AlertDispatcher(config=console_only_config)
    event = AlertEvent(level="CRITICAL", message="Orphan position detected", context={"ticker": "KXBTC15M-X"})
    with caplog.at_level(logging.CRITICAL, logger="safety.alerts"):
        dispatcher.dispatch(event)
    assert "Orphan position detected" in caplog.text


def test_dispatch_sends_email_when_configured(email_config):
    dispatcher = AlertDispatcher(config=email_config)
    event = AlertEvent(level="CRITICAL", message="Halt: unresolvable reconciliation gap", context={})
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        dispatcher.dispatch(event)
    mock_smtp_class.assert_called_once_with("localhost", 1025)


def test_dispatch_skips_email_when_not_configured(console_only_config):
    dispatcher = AlertDispatcher(config=console_only_config)
    event = AlertEvent(level="WARNING", message="test", context={})
    with patch("smtplib.SMTP") as mock_smtp_class:
        dispatcher.dispatch(event)
    mock_smtp_class.assert_not_called()


def test_critical_alert_raises_if_halt_on_critical(email_config):
    email_config = AlertConfig(
        console=True,
        email=False,
        halt_on_critical=True,
    )
    dispatcher = AlertDispatcher(config=email_config)
    event = AlertEvent(level="CRITICAL", message="Halt required", context={})
    with pytest.raises(SystemExit):
        dispatcher.dispatch(event)
