# Decision Log

Chronological record of significant decisions, findings, and changes.

---

## 2026-05-05 — KalshiDataClient WebSocket implementation

**What:** Implemented `KalshiWsConnection` and `KalshiDataClient` for live order book and trade streaming.

**Key decisions:**
- `KalshiWsConnection` holds no NautilusTrader types; it dispatches raw `dict` payloads to callbacks wired by `KalshiDataClient`. This keeps the WebSocket layer independently testable.
- `orderbook_snapshot_to_deltas` always prepends `BookAction.CLEAR` as the first delta. Without this, reconnect snapshots stack ADD deltas on top of stale levels, corrupting the book.
- HTTP orderbook snapshot fetch is wrapped with `asyncio.to_thread` because `httpx.Client` is synchronous and blocks the event loop.
- Subscription methods on `KalshiDataClient` are synchronous (NautilusTrader contract), so async WS/HTTP work is dispatched via `self.create_task()`.
- The NO side of the Kalshi order book is represented as SELL at the YES-equivalent price (`100 - no_price_cents`). Both sides are merged into a single price axis so NautilusTrader sees a unified book.

---

## 2026-05-05 — Knowledge base initialized

**What:** Created this knowledge base and the `/update-knowledge-base` skill.

**Why:** Capture architectural rationale and non-obvious patterns that are not visible in code or git history. The skill is wired to a `PreToolUse` hook so it runs before every `git push`, prompting evaluation of whether recent conversation/decisions warrant new KB entries.
