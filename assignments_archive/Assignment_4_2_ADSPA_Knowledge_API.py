"""
Assignment 4.2 — Knowledge Representation and Adaptive API Integration
Agent: Academic Deadline & Study Planning Agent (ADSPA)

Live endpoint: Open-Meteo forecast API (no API key required).
The agent treats severe weather as an environmental disruption that can
change its study plan from library-based study to an online/offline fallback.
A deterministic demo mode is included so behavior can be tested without
network access. Run with --live to query the real endpoint.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import argparse
import json
import sys


# 1) Structured knowledge representation: domain rules and mappings in JSON-like dictionaries.
KNOWLEDGE_BASE: Dict[str, Any] = {
    "agent": {
        "name": "Academic Deadline & Study Planning Agent (ADSPA)",
        "domain": "academic planning",
        "version": "4.2"
    },
    "weather_policy": {
        "severe_weather_codes": [65, 67, 75, 82, 95, 96, 99],
        "moderate_weather_codes": [51, 53, 55, 61, 63, 66, 71, 73, 77, 80, 81, 85, 86],
        "severe_wind_speed_kmh": 50,
        "precipitation_probability_threshold": 70,
        "precipitation_mm_threshold": 10,
        "actions": {
            "severe": "avoid_travel_use_online_study",
            "moderate": "prefer_online_study",
            "clear": "library_study_allowed",
            "unknown": "use_safe_fallback"
        }
    },
    "plan_templates": {
        "library_study_plan": [
            "Review the assignment brief and rubric",
            "Travel to the library if conditions are safe",
            "Complete a focused study session",
            "Check the rubric and submit"
        ],
        "online_study_plan": [
            "Open course materials and the assignment rubric online",
            "Set up a focused study session at home",
            "Complete the required work",
            "Check the rubric and submit"
        ],
        "offline_recovery_plan": [
            "Open downloaded assignment instructions and course notes",
            "Complete the highest-priority work using offline resources",
            "Reconnect and submit when service is available"
        ]
    }
}

# Open-Meteo weather code descriptions (simplified, sufficient for this policy).
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog", 51: "light drizzle",
    53: "moderate drizzle", 55: "dense drizzle", 56: "freezing drizzle",
    57: "dense freezing drizzle", 61: "slight rain", 63: "moderate rain",
    65: "heavy rain", 66: "freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    77: "snow grains", 80: "slight rain showers", 81: "moderate rain showers",
    82: "violent rain showers", 85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail"
}


@dataclass
class LiveWeather:
    latitude: float
    longitude: float
    timezone_name: str
    time: str
    temperature_c: float
    precipitation_probability: Optional[int]
    precipitation_mm: float
    wind_speed_kmh: float
    weather_code: int
    weather_description: str
    source: str = "Open-Meteo REST API"
    fetched_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AgentState:
    beliefs: Dict[str, Any] = field(default_factory=dict)
    current_plan: str = "library_study_plan"
    plan_steps: list = field(default_factory=list)
    last_update_source: str = "initial"
    last_reason: str = "Initial default plan"


class OpenMeteoClient:
    """Fetches current conditions from the public Open-Meteo forecast endpoint."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    def fetch_current_weather(self, latitude: float, longitude: float) -> LiveWeather:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,showers,snowfall,weather_code,wind_speed_10m",
            "hourly": "precipitation_probability",
            "forecast_days": 1,
            "timezone": "auto"
        }
        url = self.BASE_URL + "?" + urlencode(params)
        request = Request(url, headers={"User-Agent": "ADSPA-Assignment-4.2/1.0"})
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        current = payload.get("current")
        if not isinstance(current, dict):
            raise ValueError("API response did not contain a current-weather object.")

        probability = None
        hourly = payload.get("hourly", {})
        hourly_times = hourly.get("time", [])
        probabilities = hourly.get("precipitation_probability", [])
        if current.get("time") in hourly_times:
            index = hourly_times.index(current["time"])
            if index < len(probabilities) and probabilities[index] is not None:
                probability = int(probabilities[index])

        code = int(current.get("weather_code", -1))
        return LiveWeather(
            latitude=float(payload.get("latitude", latitude)),
            longitude=float(payload.get("longitude", longitude)),
            timezone_name=str(payload.get("timezone", "unknown")),
            time=str(current.get("time", "unknown")),
            temperature_c=float(current.get("temperature_2m", 0)),
            precipitation_probability=probability,
            precipitation_mm=float(current.get("precipitation", 0)),
            wind_speed_kmh=float(current.get("wind_speed_10m", 0)),
            weather_code=code,
            weather_description=WEATHER_CODES.get(code, "unknown weather condition")
        )


class ADSPAAdaptiveAgent:
    def __init__(self, knowledge_base: Dict[str, Any] = None):
        self.knowledge = knowledge_base or KNOWLEDGE_BASE
        self.state = AgentState(
            beliefs={
                "weather_condition": "not_fetched",
                "severe_weather": False,
                "travel_advised": True
            },
            current_plan="library_study_plan",
            plan_steps=list(self.knowledge["plan_templates"]["library_study_plan"])
        )
        self.history = []

    def parse_weather_payload(self, weather: LiveWeather) -> Dict[str, Any]:
        """Convert external API values into normalized internal beliefs."""
        policy = self.knowledge["weather_policy"]
        severe_by_code = weather.weather_code in policy["severe_weather_codes"]
        severe_by_wind = weather.wind_speed_kmh >= policy["severe_wind_speed_kmh"]
        severe_by_precip = weather.precipitation_mm >= policy["precipitation_mm_threshold"]
        moderate_by_code = weather.weather_code in policy["moderate_weather_codes"]
        high_probability = (
            weather.precipitation_probability is not None and
            weather.precipitation_probability >= policy["precipitation_probability_threshold"]
        )
        severe = severe_by_code or severe_by_wind or severe_by_precip
        moderate = moderate_by_code or high_probability

        if severe:
            condition = "severe"
        elif moderate:
            condition = "moderate"
        else:
            condition = "clear_or_low_risk"

        return {
            "weather_condition": condition,
            "weather_code": weather.weather_code,
            "weather_description": weather.weather_description,
            "temperature_c": weather.temperature_c,
            "precipitation_probability": weather.precipitation_probability,
            "precipitation_mm": weather.precipitation_mm,
            "wind_speed_kmh": weather.wind_speed_kmh,
            "severe_weather": severe,
            "travel_advised": not severe,
            "weather_time": weather.time,
            "coordinates": {"latitude": weather.latitude, "longitude": weather.longitude},
            "data_source": weather.source,
            "fetched_at_utc": weather.fetched_at_utc
        }

    def adapt_plan(self, beliefs: Dict[str, Any], source: str = "live_api") -> AgentState:
        """Update beliefs and instantly select a plan using structured policy."""
        self.state.beliefs.update(beliefs)
        condition = self.state.beliefs.get("weather_condition", "unknown")
        if condition == "severe":
            selected = "offline_recovery_plan" if not self.state.beliefs.get("internet_available", True) else "online_study_plan"
            reason = "Severe weather detected; avoid unnecessary travel and study remotely."
        elif condition == "moderate":
            selected = "online_study_plan"
            reason = "Weather risk is elevated; prefer studying remotely."
        else:
            selected = "library_study_plan"
            reason = "No severe weather signal; library travel remains an option."

        old_plan = self.state.current_plan
        self.state.current_plan = selected
        self.state.plan_steps = list(self.knowledge["plan_templates"][selected])
        self.state.last_update_source = source
        self.state.last_reason = reason
        event = {
            "source": source,
            "previous_plan": old_plan,
            "new_plan": selected,
            "reason": reason,
            "beliefs": dict(self.state.beliefs),
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        self.history.append(event)
        print("[ADAPTATION] " + json.dumps({
            "source": source, "previous_plan": old_plan, "new_plan": selected,
            "reason": reason, "weather_condition": condition,
            "travel_advised": self.state.beliefs.get("travel_advised")
        }, sort_keys=True))
        return self.state

    def ingest_live_weather(self, weather: LiveWeather) -> AgentState:
        beliefs = self.parse_weather_payload(weather)
        return self.adapt_plan(beliefs, source="Open-Meteo live REST API")


def run_demo():
    print("=== ADSPA Assignment 4.2: Knowledge + Adaptive API ===")
    agent = ADSPAAdaptiveAgent()
    print("Knowledge base loaded: " + agent.knowledge["agent"]["name"])
    print("Initial plan: " + agent.state.current_plan)

    # Deterministic verification ensures adaptation is demonstrated in any environment.
    print("\n--- Verification test: simulated severe-weather feed ---")
    fake_severe = LiveWeather(
        latitude=13.0827, longitude=80.2707, timezone_name="Asia/Kolkata",
        time="test-time", temperature_c=29.0, precipitation_probability=90,
        precipitation_mm=12.0, wind_speed_kmh=18.0, weather_code=65,
        weather_description=WEATHER_CODES[65], source="deterministic test fixture"
    )
    agent.ingest_live_weather(fake_severe)
    assert agent.state.current_plan == "online_study_plan"

    print("\n--- Verification test: simulated clear-weather feed ---")
    fake_clear = LiveWeather(
        latitude=13.0827, longitude=80.2707, timezone_name="Asia/Kolkata",
        time="test-time", temperature_c=30.0, precipitation_probability=10,
        precipitation_mm=0.0, wind_speed_kmh=12.0, weather_code=1,
        weather_description=WEATHER_CODES[1], source="deterministic test fixture"
    )
    agent.ingest_live_weather(fake_clear)
    assert agent.state.current_plan == "library_study_plan"

    print("\n=== DEMO SUMMARY ===")
    print("Knowledge format: structured Python dictionaries (JSON-compatible)")
    print("Plans observed: online_study_plan -> library_study_plan")
    print("ADAPTIVE_BEHAVIOR_VERIFIED=True")
    print("ALL_ASSERTIONS_PASSED=True")


def run_live(latitude: float, longitude: float):
    print("=== ADSPA Assignment 4.2: LIVE Open-Meteo API run ===")
    agent = ADSPAAdaptiveAgent()
    client = OpenMeteoClient()
    print(f"Fetching live weather for latitude={latitude}, longitude={longitude} ...")
    try:
        weather = client.fetch_current_weather(latitude, longitude)
        print("[LIVE_WEATHER] " + json.dumps({
            "source": weather.source, "time": weather.time,
            "temperature_c": weather.temperature_c,
            "weather_code": weather.weather_code,
            "weather_description": weather.weather_description,
            "precipitation_probability": weather.precipitation_probability,
            "precipitation_mm": weather.precipitation_mm,
            "wind_speed_kmh": weather.wind_speed_kmh,
            "coordinates": {"latitude": weather.latitude, "longitude": weather.longitude}
        }, sort_keys=True))
        agent.ingest_live_weather(weather)
        print("[FINAL_AGENT_STATE] " + json.dumps({
            "beliefs": agent.state.beliefs,
            "current_plan": agent.state.current_plan,
            "plan_steps": agent.state.plan_steps,
            "last_reason": agent.state.last_reason
        }, sort_keys=True))
        print("LIVE_API_FETCH_SUCCEEDED=True")
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(f"LIVE_API_FETCH_SUCCEEDED=False")
        print(f"API_ERROR={type(exc).__name__}: {exc}")
        print("The endpoint could not be reached in this environment. Run --live again with network access.")
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="ADSPA structured knowledge and adaptive Open-Meteo integration")
    parser.add_argument("--live", action="store_true", help="Fetch real current weather from Open-Meteo")
    parser.add_argument("--latitude", type=float, default=13.0827, help="Location latitude (default: Chennai)")
    parser.add_argument("--longitude", type=float, default=80.2707, help="Location longitude (default: Chennai)")
    args, unknown = parser.parse_known_args()
    if args.live:
        run_live(args.latitude, args.longitude)
    else:
        run_demo()


if __name__ == "__main__":
    main()
