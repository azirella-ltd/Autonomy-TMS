"""Utility helpers for manually starting a Beer Game instance during debugging.

This module mirrors the minimal snippet shared with QA for reproducing the
frontend "Start" button behaviour, but adds a convenience function to resolve a
`game_id` from a human-readable name.
"""

from __future__ import annotations

from typing import Optional

import requests


BASE_URL = "http://localhost:8000/api/v1"
EMAIL = "admin@example.com"
PASSWORD = "Admin123!"
DEFAULT_GAME_NAME = "Naive Agent Showcase"


class BackendError(RuntimeError):
    """Raised when the Beer Game backend responds with an error."""


def _raise_for_status(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - convenience wrapper
        detail = exc.response.text if exc.response is not None else "<no body>"
        raise BackendError(f"Backend request failed: {exc}\n{detail}") from exc


def login(email: str = EMAIL, password: str = PASSWORD) -> str:
    """Authenticate against the backend and return a bearer token."""

    response = requests.post(
        f"{BASE_URL}/auth/token",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    _raise_for_status(response)
    payload = response.json()
    return payload["access_token"]


def find_game_id(game_name: str, *, token: str) -> Optional[int]:
    """Return the numeric ``game_id`` matching ``game_name`` if it exists."""

    response = requests.get(
        f"{BASE_URL}/games",
        headers={"Authorization": f"Bearer {token}"},
        params={"skip": 0, "limit": 500},
        timeout=30,
    )
    _raise_for_status(response)
    games = response.json()

    for game in games:
        if game.get("name") == game_name:
            return int(game["id"])
    return None


def start_game(game_id: int, *, token: str) -> dict:
    """Trigger the backend to start the specified game."""

    response = requests.post(
        f"{BASE_URL}/games/{game_id}/start",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def main() -> None:
    """Authenticate, resolve the showcase game, and start it."""

    token = login()
    game_id = find_game_id(DEFAULT_GAME_NAME, token=token)
    if game_id is None:
        raise SystemExit(
            f"Could not locate a game named '{DEFAULT_GAME_NAME}'."
            " Ensure the database is seeded and try again."
        )

    payload = start_game(game_id, token=token)
    print(f"Started game {game_id} ({DEFAULT_GAME_NAME})")
    print(payload)


if __name__ == "__main__":
    main()
