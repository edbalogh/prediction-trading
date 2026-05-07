from __future__ import annotations

import pytest
import respx
import httpx
from adapters.mlb_stats.client import MLBStatsClient


SCHEDULE_RESPONSE = {
    "dates": [
        {
            "date": "2026-05-07",
            "games": [
                {
                    "gamePk": 12345,
                    "teams": {
                        "home": {
                            "team": {
                                "id": 109,
                                "name": "Arizona Diamondbacks",
                                "locationName": "Arizona",
                            }
                        },
                        "away": {
                            "team": {
                                "id": 121,
                                "name": "New York Mets",
                                "locationName": "New York",
                            }
                        },
                    },
                }
            ],
        }
    ]
}

FEED_LIVE_RESPONSE = {
    "gameData": {
        "status": {"abstractGameState": "Live"},
    },
    "liveData": {
        "linescore": {
            "currentInning": 3,
            "inningHalf": "Bottom",
        },
        "plays": {
            "allPlays": [
                {
                    "about": {
                        "endTime": "2026-05-07T20:10:00Z",
                        "isScoringPlay": True,
                    },
                    "result": {"event": "Home Run"},
                },
                {
                    "about": {
                        "endTime": "2026-05-07T20:30:00Z",
                        "isScoringPlay": True,
                    },
                    "result": {"event": "Single"},
                },
            ],
            "scoringPlays": [0, 1],
        },
    },
}


@respx.mock
def test_get_schedule_returns_games():
    respx.get("https://statsapi.mlb.com/api/v1/schedule").mock(
        return_value=httpx.Response(200, json=SCHEDULE_RESPONSE)
    )
    client = MLBStatsClient()
    games = client.get_schedule("2026-05-07")
    client.close()
    assert len(games) == 1
    assert games[0]["gamePk"] == 12345
    assert games[0]["home_city"] == "Arizona"
    assert games[0]["home_name"] == "Arizona Diamondbacks"
    assert games[0]["away_city"] == "New York"
    assert games[0]["away_name"] == "New York Mets"


@respx.mock
def test_get_schedule_empty_on_no_dates():
    respx.get("https://statsapi.mlb.com/api/v1/schedule").mock(
        return_value=httpx.Response(200, json={"dates": []})
    )
    client = MLBStatsClient()
    games = client.get_schedule("2026-05-07")
    client.close()
    assert games == []


@respx.mock
def test_get_game_state_returns_inning_and_half():
    respx.get("https://statsapi.mlb.com/api/v1.1/game/12345/feed/live").mock(
        return_value=httpx.Response(200, json=FEED_LIVE_RESPONSE)
    )
    client = MLBStatsClient()
    state = client.get_game_state(12345)
    client.close()
    assert state["inning"] == 3
    assert state["half"] == "bottom"
    assert state["status"] == "Live"


@respx.mock
def test_get_scoring_plays_all_in_window():
    respx.get("https://statsapi.mlb.com/api/v1.1/game/12345/feed/live").mock(
        return_value=httpx.Response(200, json=FEED_LIVE_RESPONSE)
    )
    client = MLBStatsClient()
    plays = client.get_scoring_plays(12345, since_ns=0, until_ns=10**19)
    client.close()
    assert len(plays) == 2


@respx.mock
def test_get_scoring_plays_none_in_window():
    respx.get("https://statsapi.mlb.com/api/v1.1/game/12345/feed/live").mock(
        return_value=httpx.Response(200, json=FEED_LIVE_RESPONSE)
    )
    client = MLBStatsClient()
    plays = client.get_scoring_plays(12345, since_ns=0, until_ns=1)
    client.close()
    assert plays == []


@respx.mock
def test_get_scoring_plays_returns_empty_on_no_scoring_plays():
    response = {
        "gameData": {"status": {"abstractGameState": "Live"}},
        "liveData": {
            "linescore": {"currentInning": 1, "inningHalf": "Top"},
            "plays": {"allPlays": [], "scoringPlays": []},
        },
    }
    respx.get("https://statsapi.mlb.com/api/v1.1/game/99999/feed/live").mock(
        return_value=httpx.Response(200, json=response)
    )
    client = MLBStatsClient()
    plays = client.get_scoring_plays(99999, since_ns=0, until_ns=10**19)
    client.close()
    assert plays == []


@respx.mock
def test_http_error_propagates():
    respx.get("https://statsapi.mlb.com/api/v1/schedule").mock(
        return_value=httpx.Response(500)
    )
    client = MLBStatsClient()
    with pytest.raises(httpx.HTTPStatusError):
        client.get_schedule("2026-05-07")
    client.close()


@pytest.mark.asyncio
@respx.mock
async def test_async_get_schedule():
    respx.get("https://statsapi.mlb.com/api/v1/schedule").mock(
        return_value=httpx.Response(200, json=SCHEDULE_RESPONSE)
    )
    client = MLBStatsClient()
    games = await client.async_get_schedule("2026-05-07")
    client.close()
    assert len(games) == 1
    assert games[0]["gamePk"] == 12345


@pytest.mark.asyncio
@respx.mock
async def test_async_get_game_state():
    respx.get("https://statsapi.mlb.com/api/v1.1/game/12345/feed/live").mock(
        return_value=httpx.Response(200, json=FEED_LIVE_RESPONSE)
    )
    client = MLBStatsClient()
    state = await client.async_get_game_state(12345)
    client.close()
    assert state["half"] == "bottom"


@pytest.mark.asyncio
@respx.mock
async def test_async_get_scoring_plays():
    respx.get("https://statsapi.mlb.com/api/v1.1/game/12345/feed/live").mock(
        return_value=httpx.Response(200, json=FEED_LIVE_RESPONSE)
    )
    client = MLBStatsClient()
    plays = await client.async_get_scoring_plays(12345, since_ns=0, until_ns=10**19)
    client.close()
    assert len(plays) == 2
