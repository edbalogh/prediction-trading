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


import os
import pandas as pd
from catalog.sync import CatalogBuilder


@pytest.fixture()
def tmp_catalog(tmp_path):
    catalog_path = str(tmp_path / "catalog")
    ingestion_dir = str(tmp_path / "ingestion")
    os.makedirs(catalog_path)
    os.makedirs(ingestion_dir)
    return CatalogBuilder(ingestion_data_dir=ingestion_dir, catalog_path=catalog_path)


def _write_trades_parquet(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_sync_trades_file_writes_trade_ticks(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "trades" / "series=KXBTC15M" / "date=2026-03-25" / "part.parquet")
    _write_trades_parquet(parquet_path, [
        {
            "trade_id": "trade-001",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "10.00",
            "yes_price_dollars": "0.55",
            "no_price_dollars": "0.45",
            "taker_side": "yes",
            "created_time": "2026-03-25T10:00:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
        {
            "trade_id": "trade-002",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "5.00",
            "yes_price_dollars": "0.56",
            "no_price_dollars": "0.44",
            "taker_side": "no",
            "created_time": "2026-03-25T10:01:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
    ])
    count = tmp_catalog.sync_trades_file(parquet_path)
    assert count == 2

    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    ticks = catalog.trade_ticks(instrument_ids=["KXBTC15M-TEST.KALSHI"])
    assert len(ticks) == 2
    assert str(ticks[0].price) == "0.55"
    assert str(ticks[1].price) == "0.56"


def test_sync_trades_file_skips_rows_with_missing_price(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "trades" / "series=KXBTC15M" / "date=2026-03-26" / "part.parquet")
    _write_trades_parquet(parquet_path, [
        {
            "trade_id": "trade-003",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "10.00",
            "yes_price_dollars": None,
            "no_price_dollars": None,
            "taker_side": "yes",
            "created_time": "2026-03-26T10:00:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
        {
            "trade_id": "trade-004",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "3.00",
            "yes_price_dollars": "0.60",
            "no_price_dollars": "0.40",
            "taker_side": "yes",
            "created_time": "2026-03-26T10:01:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
    ])
    count = tmp_catalog.sync_trades_file(parquet_path)
    assert count == 1


def test_sync_trades_no_is_seller(tmp_catalog, tmp_path):
    from nautilus_trader.model.enums import AggressorSide
    parquet_path = str(tmp_path / "ingestion" / "trades" / "series=KXBTC15M" / "date=2026-03-27" / "part.parquet")
    _write_trades_parquet(parquet_path, [{
        "trade_id": "trade-005",
        "ticker": "KXBTC15M-TEST",
        "count_fp": "2.00",
        "yes_price_dollars": "0.40",
        "no_price_dollars": "0.60",
        "taker_side": "no",
        "created_time": "2026-03-27T10:00:00.000000Z",
        "series_ticker": "KXBTC15M",
    }])
    tmp_catalog.sync_trades_file(parquet_path)
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    ticks = catalog.trade_ticks(instrument_ids=["KXBTC15M-TEST.KALSHI"])
    assert ticks[0].aggressor_side == AggressorSide.SELLER


def test_sync_marks_file_as_synced(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "trades" / "series=KXBTC15M" / "date=2026-03-30" / "part.parquet")
    _write_trades_parquet(parquet_path, [{
        "trade_id": "t-state",
        "ticker": "KXBTC15M-STATE",
        "count_fp": "1.00",
        "yes_price_dollars": "0.50",
        "no_price_dollars": "0.50",
        "taker_side": "yes",
        "created_time": "2026-03-30T10:00:00.000000Z",
        "series_ticker": "KXBTC15M",
    }])
    tmp_catalog.sync_trades_file(parquet_path)
    assert tmp_catalog.is_synced(parquet_path) is True
    # Verify state survives reconstruction
    rebuilt = CatalogBuilder(
        ingestion_data_dir=str(tmp_path / "ingestion"),
        catalog_path=tmp_catalog._catalog_path,
    )
    assert rebuilt.is_synced(parquet_path) is True


def _write_candlesticks_parquet(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_sync_candlesticks_file_writes_bars(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "candlesticks" / "interval=60m" / "series=KXBTC15M" / "date=2026-03-25" / "part.parquet")
    _write_candlesticks_parquet(parquet_path, [
        {
            "end_period_ts": 1_774_274_400,   # Unix seconds
            "ticker": "KXBTC15M-TEST",
            "interval_minutes": 60,
            "price_open": "0.50",
            "price_high": "0.60",
            "price_low": "0.48",
            "price_close": "0.55",
            "volume": "100.00",
        },
    ])
    count = tmp_catalog.sync_candlesticks_file(parquet_path)
    assert count == 1

    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["KXBTC15M-TEST.KALSHI"])
    assert len(bars) == 1
    assert str(bars[0].open) == "0.50"
    assert str(bars[0].close) == "0.55"


def test_sync_candlesticks_file_skips_null_ohlc(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "candlesticks" / "interval=60m" / "series=KXBTC15M" / "date=2026-03-26" / "part.parquet")
    _write_candlesticks_parquet(parquet_path, [
        {   # Null OHLC — should be skipped
            "end_period_ts": 1_774_278_000,
            "ticker": "KXBTC15M-TEST",
            "interval_minutes": 60,
            "price_open": None,
            "price_high": None,
            "price_low": None,
            "price_close": None,
            "volume": "0.00",
        },
        {   # Valid — should be written
            "end_period_ts": 1_774_281_600,
            "ticker": "KXBTC15M-TEST",
            "interval_minutes": 60,
            "price_open": "0.53",
            "price_high": "0.58",
            "price_low": "0.51",
            "price_close": "0.56",
            "volume": "50.00",
        },
    ])
    count = tmp_catalog.sync_candlesticks_file(parquet_path)
    assert count == 1


def test_sync_candlesticks_bar_type_uses_hour_for_60min(tmp_catalog, tmp_path):
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    parquet_path = str(tmp_path / "ingestion" / "candlesticks" / "interval=60m" / "series=KXBTC15M" / "date=2026-03-27" / "part.parquet")
    _write_candlesticks_parquet(parquet_path, [{
        "end_period_ts": 1_774_285_200,
        "ticker": "KXBTC15M-HOURTEST",
        "interval_minutes": 60,
        "price_open": "0.40",
        "price_high": "0.45",
        "price_low": "0.38",
        "price_close": "0.42",
        "volume": "20.00",
    }])
    tmp_catalog.sync_candlesticks_file(parquet_path)
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["KXBTC15M-HOURTEST.KALSHI"])
    assert len(bars) == 1
    # Bar type string should contain "HOUR" not "MINUTE"
    assert "HOUR" in str(bars[0].bar_type)


def test_sync_candlesticks_marks_file_as_synced(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "candlesticks" / "interval=60m" / "series=KXBTC15M" / "date=2026-03-28" / "part.parquet")
    _write_candlesticks_parquet(parquet_path, [{
        "end_period_ts": 1_774_288_800,
        "ticker": "KXBTC15M-SYNCTEST",
        "interval_minutes": 60,
        "price_open": "0.50",
        "price_high": "0.55",
        "price_low": "0.48",
        "price_close": "0.52",
        "volume": "10.00",
    }])
    tmp_catalog.sync_candlesticks_file(parquet_path)
    assert tmp_catalog.is_synced(parquet_path) is True
    rebuilt = CatalogBuilder(
        ingestion_data_dir=str(tmp_path / "ingestion"),
        catalog_path=tmp_catalog._catalog_path,
    )
    assert rebuilt.is_synced(parquet_path) is True
