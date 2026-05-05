# NautilusTrader Integration

## LiveDataClient Contract

**Date:** 2026-05-05
**Context:** Understanding which NT methods are sync vs async.

`subscribe_*` and `unsubscribe_*` methods are **synchronous** — NT calls them from its message bus. Schedule async work with `self.create_task(coro)`. `_connect()` and `_disconnect()` are **async** — called by NT's lifecycle machinery. Use these for WS setup/teardown.

## OrderBookDelta.clear()

**Date:** 2026-05-05
**Context:** How to reset an order book.

`OrderBookDelta.clear(instrument_id, sequence=0, ts_event=ts, ts_init=ts)` is a static factory method on `OrderBookDelta`. It produces a delta with `BookAction.CLEAR`, which tells NT's order book engine to wipe all levels. Prepend one to every snapshot batch to ensure reconnect snapshots don't stack on stale data.

## BinaryOption Construction

**Date:** 2026-05-05
**Context:** `BinaryOption` requires `outcome` and `description` fields not on other instrument types.

The `outcome` field holds the human-readable contract description (e.g., "Will BTC be above $65,499.99 at 3pm?"). The `description` field is similar. Both are mapped from the Kalshi market `title` field. `min_quantity=Quantity(1, SIZE_PRECISION)` and `max_quantity=None` are the correct defaults for Kalshi binary options.

## Testing LiveDataClient Subclasses

**Date:** 2026-05-05
**Context:** NT's `LiveDataClient` constructor requires a full actor context (clock, msgbus, cache, config).

Use `MyClient.__new__(MyClient)` to bypass the constructor, then inject dependencies directly as attributes. Required attributes for `KalshiDataClient` tests: `_ws`, `_http`, `_subscribed_instruments` (set), `_handle_data` (callable), `create_task` (callable). This pattern avoids building a full NT test environment while still exercising real client logic.

## Cython Slot Restrictions

**Date:** 2026-05-05
**Context:** Attempted to set `client._log = MagicMock()` in tests.

NT's `Component` class is Cython-compiled. Some attributes are implemented as Cython slots and cannot be reassigned from Python. `_log` is one of these. Use a module-level `logging.getLogger` instead of relying on NT's `_log` attribute in adapter code, which allows normal test execution without needing to mock NT internals.

## pytest and homebrew Python

**Date:** 2026-05-05
**Context:** `python3.11 -m pytest` fails with `ModuleNotFoundError: No module named 'pkg_resources'`.

The `fugue_test` pytest plugin (a transitive dependency) uses `pkg_resources`, which is missing in homebrew Python 3.11. Fix: either run tests inside a virtualenv (where `setuptools` is installed), or use `python3.11 -c "import pytest; pytest.main([...])"` as a workaround for quick validation.
