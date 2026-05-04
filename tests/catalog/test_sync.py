import pytest
from catalog.sync import (
    parse_ts_ns,
    interval_minutes_to_bar_spec,
    taker_side_to_aggressor,
)
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.enums import BarAggregation, PriceType, AggressorSide


def test_parse_ts_ns_iso8601():
    ts = parse_ts_ns("2026-03-25T23:47:43.556733Z")
    # Microseconds preserved, sub-microsecond zeroed
    assert ts == 1_774_482_463_556_733_000


def test_parse_ts_ns_unix_seconds():
    # end_period_ts in candlesticks is Unix seconds int
    ts = parse_ts_ns(1_774_274_400)
    assert ts == 1_774_274_400 * 1_000_000_000


def test_parse_ts_ns_unix_milliseconds():
    # open_time in crypto_bars is Unix milliseconds
    ts = parse_ts_ns(1_771_218_000_000, unit="ms")
    assert ts == 1_771_218_000_000 * 1_000_000


def test_interval_minutes_to_bar_spec_60():
    spec = interval_minutes_to_bar_spec(60)
    assert spec == BarSpecification(1, BarAggregation.HOUR, PriceType.LAST)


def test_interval_minutes_to_bar_spec_1():
    spec = interval_minutes_to_bar_spec(1)
    assert spec == BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)


def test_interval_minutes_to_bar_spec_30():
    spec = interval_minutes_to_bar_spec(30)
    assert spec == BarSpecification(30, BarAggregation.MINUTE, PriceType.LAST)


def test_taker_side_yes_is_buyer():
    assert taker_side_to_aggressor("yes") == AggressorSide.BUYER


def test_taker_side_no_is_seller():
    assert taker_side_to_aggressor("no") == AggressorSide.SELLER


def test_interval_minutes_to_bar_spec_invalid():
    with pytest.raises(ValueError, match="Unsupported interval_minutes=7"):
        interval_minutes_to_bar_spec(7)


def test_taker_side_to_aggressor_invalid():
    with pytest.raises(ValueError, match="Unknown taker_side"):
        taker_side_to_aggressor("invalid")
