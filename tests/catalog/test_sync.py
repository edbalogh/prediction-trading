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


def _write_crypto_bars_parquet(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_sync_crypto_bars_file_writes_bars(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=BTC-USD" / "date=2026-02-16" / "part.parquet")
    _write_crypto_bars_parquet(parquet_path, [
        {
            "open_time": 1_771_218_000_000,   # Unix milliseconds
            "open": 68830.14,
            "high": 68863.96,
            "low": 68802.66,
            "close": 68802.66,
            "volume": 6.364871,
            "close_time": 1_771_218_060_000,
            "quote_volume": 437920.060861,
            "symbol": "BTC-USD",
        },
        {
            "open_time": 1_771_218_060_000,
            "open": 68802.66,
            "high": 68834.97,
            "low": 68806.68,
            "close": 68830.14,
            "volume": 2.123524,
            "close_time": 1_771_218_120_000,
            "quote_volume": 146162.488628,
            "symbol": "BTC-USD",
        },
    ])
    count = tmp_catalog.sync_crypto_bars_file(parquet_path)
    assert count == 2

    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["BTC-USD.CRYPTO"])
    assert len(bars) == 2
    # Price precision is 2
    assert str(bars[0].open) == "68830.14"


def test_sync_crypto_bars_uses_crypto_venue(tmp_catalog, tmp_path):
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=ETH-USD" / "date=2026-02-16" / "part.parquet")
    _write_crypto_bars_parquet(parquet_path, [{
        "open_time": 1_771_218_000_000,
        "open": 3000.50,
        "high": 3010.00,
        "low": 2990.00,
        "close": 3005.00,
        "volume": 100.5,
        "close_time": 1_771_218_060_000,
        "quote_volume": 301500.0,
        "symbol": "ETH-USD",
    }])
    tmp_catalog.sync_crypto_bars_file(parquet_path)
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["ETH-USD.CRYPTO"])
    assert len(bars) == 1
    assert "CRYPTO" in str(bars[0].bar_type)


def test_sync_crypto_bars_uses_1_minute_spec(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=BTC-USD" / "date=2026-02-17" / "part.parquet")
    _write_crypto_bars_parquet(parquet_path, [{
        "open_time": 1_771_300_000_000,
        "open": 70000.0,
        "high": 70100.0,
        "low": 69900.0,
        "close": 70050.0,
        "volume": 5.0,
        "close_time": 1_771_300_060_000,
        "quote_volume": 350250.0,
        "symbol": "BTC-USD",
    }])
    tmp_catalog.sync_crypto_bars_file(parquet_path)
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["BTC-USD.CRYPTO"])
    assert "MINUTE" in str(bars[0].bar_type)


def test_sync_crypto_bars_marks_file_as_synced(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=BTC-USD" / "date=2026-02-18" / "part.parquet")
    _write_crypto_bars_parquet(parquet_path, [{
        "open_time": 1_771_400_000_000,
        "open": 71000.0,
        "high": 71100.0,
        "low": 70900.0,
        "close": 71050.0,
        "volume": 3.0,
        "close_time": 1_771_400_060_000,
        "quote_volume": 213150.0,
        "symbol": "BTC-USD",
    }])
    tmp_catalog.sync_crypto_bars_file(parquet_path)
    assert tmp_catalog.is_synced(parquet_path) is True
    rebuilt = CatalogBuilder(
        ingestion_data_dir=str(tmp_path / "ingestion"),
        catalog_path=tmp_catalog._catalog_path,
    )
    assert rebuilt.is_synced(parquet_path) is True


def test_sync_crypto_bars_clamps_ohlc_invariants(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=BTC-USD" / "date=2026-02-19" / "part.parquet")
    # This bar has low > open which violates the OHLC invariant
    _write_crypto_bars_parquet(parquet_path, [{
        "open_time": 1_771_500_000_000,
        "open": 68800.00,
        "high": 68900.00,
        "low": 68850.00,   # low > open — violates invariant
        "close": 68870.00,
        "volume": 1.5,
        "close_time": 1_771_500_060_000,
        "quote_volume": 103305.0,
        "symbol": "BTC-USD",
    }])
    # Should not raise — clamping should handle this
    count = tmp_catalog.sync_crypto_bars_file(parquet_path)
    assert count == 1
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["BTC-USD.CRYPTO"])
    # After clamping: low should be <= open
    assert float(str(bars[-1].low)) <= float(str(bars[-1].open))


def test_sync_trades_discovers_and_syncs_all_files(tmp_catalog, tmp_path):
    ingestion_dir = str(tmp_path / "ingestion")
    for series, date in [("KXBTC15M", "2026-03-25"), ("KXBTC15M", "2026-03-26")]:
        path = os.path.join(ingestion_dir, "trades", f"series={series}", f"date={date}", "part.parquet")
        _write_trades_parquet(path, [{
            "trade_id": f"t-{date}",
            "ticker": f"{series}-TEST",
            "count_fp": "1.00",
            "yes_price_dollars": "0.50",
            "no_price_dollars": "0.50",
            "taker_side": "yes",
            "created_time": f"{date}T10:00:00.000000Z",
            "series_ticker": series,
        }])
    total = tmp_catalog.sync_trades()
    assert total == 2


def test_idempotency_does_not_double_write(tmp_catalog, tmp_path):
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    ingestion_dir = str(tmp_path / "ingestion")
    path = os.path.join(ingestion_dir, "trades", "series=KXBTC15M", "date=2026-03-28", "part.parquet")
    _write_trades_parquet(path, [{
        "trade_id": "t-idempotent",
        "ticker": "KXBTC15M-IDEM",
        "count_fp": "1.00",
        "yes_price_dollars": "0.50",
        "no_price_dollars": "0.50",
        "taker_side": "yes",
        "created_time": "2026-03-28T10:00:00.000000Z",
        "series_ticker": "KXBTC15M",
    }])
    # First sync
    tmp_catalog.sync_trades()
    # Second sync — file already marked as synced, should skip
    count = tmp_catalog.sync_trades()
    assert count == 0

    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    ticks = catalog.trade_ticks(instrument_ids=["KXBTC15M-IDEM.KALSHI"])
    assert len(ticks) == 1   # Not duplicated


def test_sync_all_returns_summary(tmp_catalog, tmp_path):
    ingestion_dir = str(tmp_path / "ingestion")
    path = os.path.join(ingestion_dir, "trades", "series=KXBTC15M", "date=2026-03-29", "part.parquet")
    _write_trades_parquet(path, [{
        "trade_id": "t-all",
        "ticker": "KXBTC15M-ALL",
        "count_fp": "1.00",
        "yes_price_dollars": "0.50",
        "no_price_dollars": "0.50",
        "taker_side": "yes",
        "created_time": "2026-03-29T10:00:00.000000Z",
        "series_ticker": "KXBTC15M",
    }])
    summary = tmp_catalog.sync_all()
    assert "trades" in summary
    assert summary["trades"] >= 1
