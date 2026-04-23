"""Utility helpers for manually starting a Beer Scenario scenario during debugging.

This module mirrors the minimal snippet shared with QA for reproducing the
frontend "Start" button behaviour, but adds a convenience function to resolve a
`scenario_id` from a human-readable name.
"""

from __future__ import annotations

from typing import Optional

import requests


BASE_URL = "http://localhost:8000/api/v1"
EMAIL = "admin@example.com"
PASSWORD = "Admin123!"
DEFAULT_SCENARIO_NAME = "Naive Agent Showcase"


class BackendError(RuntimeError):
    """Raised when the Beer Scenario backend responds with an error."""


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


def find_scenario_id(scenario_name: str, *, token: str) -> Optional[int]:
    """Return the numeric ``scenario_id`` matching ``scenario_name`` if it exists."""

    response = requests.get(
        f"{BASE_URL}/scenarios",
        headers={"Authorization": f"Bearer {token}"},
        params={"skip": 0, "limit": 500},
        timeout=30,
    )
    _raise_for_status(response)
    scenarios = response.json()

    for scenario in scenarios:
        if scenario.get("name") == scenario_name:
            return int(scenario["id"])
    return None


def start_scenario(scenario_id: int, *, token: str) -> dict:
    """Trigger the backend to start the specified scenario."""

    response = requests.post(
        f"{BASE_URL}/scenarios/{scenario_id}/start",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def main() -> None:
    """Authenticate, resolve the showcase scenario, and start it."""

    token = login()
    scenario_id = find_scenario_id(DEFAULT_SCENARIO_NAME, token=token)
    if scenario_id is None:
        raise SystemExit(
            f"Could not locate a scenario named '{DEFAULT_SCENARIO_NAME}'."
            " Ensure the database is seeded and try again."
        )

    payload = start_scenario(scenario_id, token=token)
    print(f"Started scenario {scenario_id} ({DEFAULT_SCENARIO_NAME})")
    print(payload)


if __name__ == "__main__":
    main()
