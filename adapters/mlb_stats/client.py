from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

_MLB_SPORT_ID = 1  # MLB's sportId in the Stats API


class MLBStatsClient:
    BASE_URL = "https://statsapi.mlb.com"

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._session = httpx.Client(timeout=timeout, base_url=self.BASE_URL)

    def close(self) -> None:
        self._session.close()

    def get_schedule(self, date: str) -> list[dict]:
        """date: YYYY-MM-DD. Returns list of game dicts with gamePk, home/away city and name."""
        resp = self._session.get("/api/v1/schedule", params={"sportId": _MLB_SPORT_ID, "date": date})
        resp.raise_for_status()
        data = resp.json()
        games = []
        for date_entry in data.get("dates", []):
            for game in date_entry.get("games", []):
                home = game.get("teams", {}).get("home", {}).get("team", {})
                away = game.get("teams", {}).get("away", {}).get("team", {})
                games.append({
                    "gamePk": game["gamePk"],
                    "home_city": home.get("locationName", ""),
                    "home_name": home.get("name", ""),
                    "away_city": away.get("locationName", ""),
                    "away_name": away.get("name", ""),
                })
        return games

    def get_game_state(self, game_pk: int) -> dict:
        """Returns dict with 'inning', 'half' (lowercase 'top'/'bottom'), 'status'."""
        resp = self._session.get(f"/api/v1.1/game/{game_pk}/feed/live")
        resp.raise_for_status()
        data = resp.json()
        linescore = data.get("liveData", {}).get("linescore", {})
        return {
            "inning": linescore.get("currentInning", 0),
            "half": linescore.get("inningHalf", "").lower(),
            "status": data.get("gameData", {}).get("status", {}).get("abstractGameState", ""),
        }

    def get_scoring_plays(self, game_pk: int, since_ns: int, until_ns: int) -> list[dict]:
        """Returns scoring plays with endTime between since_ns and until_ns (nanoseconds)."""
        resp = self._session.get(f"/api/v1.1/game/{game_pk}/feed/live")
        resp.raise_for_status()
        data = resp.json()
        plays_data = data.get("liveData", {}).get("plays", {})
        all_plays = plays_data.get("allPlays", [])
        scoring_indices = plays_data.get("scoringPlays", [])
        result = []
        for idx in scoring_indices:
            if idx >= len(all_plays):
                continue
            play = all_plays[idx]
            end_time = play.get("about", {}).get("endTime", "")
            if not end_time:
                continue
            dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                continue
            play_ns = int(dt.timestamp()) * 1_000_000_000 + dt.microsecond * 1_000
            if since_ns <= play_ns <= until_ns:
                result.append(play)
        return result

    async def async_get_schedule(self, date: str) -> list[dict]:
        return await asyncio.to_thread(self.get_schedule, date)

    async def async_get_game_state(self, game_pk: int) -> dict:
        return await asyncio.to_thread(self.get_game_state, game_pk)

    async def async_get_scoring_plays(self, game_pk: int, since_ns: int, until_ns: int) -> list[dict]:
        return await asyncio.to_thread(self.get_scoring_plays, game_pk, since_ns, until_ns)
