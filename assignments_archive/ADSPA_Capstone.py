#!/usr/bin/env python3
"""
ADSPA Capstone — Integrated Secure Autonomous Agent
Assignment 5.2: Capstone Project Consolidation and Secure Deployment Execution

Standard-library-only reference implementation integrating:
  Unit 1: Core event loop and task processing
  Unit 2: Concurrent worker thread and message queue (local socket-style messages)
  Unit 3: Agent cooperation and utility-based proposal negotiation
  Unit 4: Structured knowledge base and BDI belief/desire/intention planning
  Unit 5: HMAC-SHA256 authentication, trusted-host checks, nonce replay defense

Run:
  python ADSPA_Capstone.py
  python ADSPA_Capstone.py --live-weather --latitude 13.0827 --longitude 80.2707

The default run is deterministic and offline-friendly. Live weather is optional.
This is an educational capstone demonstration, not a production-certified security system.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import queue
import secrets
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

APP_NAME = "Academic Deadline & Study Planning Agent (ADSPA)"
DEMO_SECRET = b"ADSPA-CAPSTONE-DEMO-KEY-CHANGE-IN-PRODUCTION"
TRUSTED_HOSTS = {"adspa-coordinator-01": DEMO_SECRET}
ALLOWED_COMMANDS = {"ADD_STUDY_TASK", "SET_STUDY_MODE", "GET_STATUS"}
WEATHER_KNOWLEDGE = {
    "severe_codes": [65, 67, 95, 96, 99],
    "moderate_codes": [51, 53, 55, 61, 63, 80, 81, 82],
    "high_wind_kmh": 45,
    "high_precipitation_mm": 8,
    "plans": {
        "severe": ["Avoid travel", "Move study session online", "Notify study partner", "Review deadline queue"],
        "moderate": ["Prefer remote study", "Check deadline queue", "Reassess conditions before travel"],
        "clear": ["Choose library or home study", "Prioritize nearest deadline", "Record progress"]
    }
}
# Fix the code list in a readable JSON-compatible configuration.
WEATHER_KNOWLEDGE["severe_codes"] = [65, 67, 95, 96, 99]

class SecurityError(Exception):
    pass

def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def sign_payload(payload: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, canonical_bytes(payload), hashlib.sha256).hexdigest()

def signed_message(host_id: str, command: str, args: dict[str, Any], nonce: str | None = None) -> dict[str, Any]:
    payload = {
        "host_id": host_id, "timestamp": int(time.time()),
        "nonce": nonce or secrets.token_hex(16), "command": command, "args": args
    }
    return {"payload": payload, "signature": sign_payload(payload, TRUSTED_HOSTS[host_id])}

@dataclass
class Belief:
    key: str
    value: Any
    source: str
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class Desire:
    name: str
    priority: int
    condition: str

@dataclass
class Intention:
    name: str
    steps: list[str]
    reason: str
    status: str = "active"

class SecureCommandGate:
    def __init__(self, trusted_hosts=None):
        self.trusted_hosts = dict(trusted_hosts or TRUSTED_HOSTS)
        self.seen_nonces: set[tuple[str, str]] = set()
        self.events: list[dict[str, Any]] = []

    def verify(self, envelope: dict[str, Any]) -> dict[str, Any]:
        def reject(reason, host=None):
            event = {"event": "BLOCKED_UNAUTHORIZED_REQUEST", "reason": reason, "host_id": host}
            self.events.append(event)
            print("[SECURITY] BLOCKED_UNAUTHORIZED_REQUEST " + json.dumps(event, sort_keys=True))
            raise SecurityError(reason)
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
            reject("Malformed envelope")
        payload, signature = envelope["payload"], envelope["signature"]
        if not isinstance(payload, dict) or not isinstance(signature, str):
            reject("Malformed payload/signature")
        host = payload.get("host_id")
        if not isinstance(host, str) or host not in self.trusted_hosts:
            reject("Untrusted host", host if isinstance(host, str) else None)
        if set(payload) != {"host_id", "timestamp", "nonce", "command", "args"}:
            reject("Payload schema mismatch", host)
        if not hmac.compare_digest(signature, sign_payload(payload, self.trusted_hosts[host])):
            reject("Invalid HMAC signature", host)
        try:
            stamp = int(payload["timestamp"])
        except (TypeError, ValueError):
            reject("Invalid timestamp", host)
        if abs(int(time.time()) - stamp) > 300:
            reject("Expired/future payload", host)
        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or len(nonce) < 16:
            reject("Invalid nonce", host)
        if (host, nonce) in self.seen_nonces:
            reject("Replay detected", host)
        command = payload.get("command")
        if command not in ALLOWED_COMMANDS:
            reject("Command not allowlisted", host)
        if not isinstance(payload.get("args"), dict):
            reject("Arguments must be an object", host)
        self.seen_nonces.add((host, nonce))
        return payload

class OpenMeteoClient:
    """Optional live API adapter; no third-party dependency or API key."""
    def fetch(self, latitude: float, longitude: float) -> dict[str, Any]:
        query = urllib.parse.urlencode({
            "latitude": latitude, "longitude": longitude,
            "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
            "hourly": "precipitation_probability", "forecast_days": 1, "timezone": "auto"
        })
        url = "https://api.open-meteo.com/v1/forecast?" + query
        request = urllib.request.Request(url, headers={"User-Agent": "ADSPA-Capstone-Demo/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

def weather_beliefs(payload: dict[str, Any]) -> dict[str, Any]:
    current = payload.get("current", {})
    hourly = payload.get("hourly", {})
    probs = hourly.get("precipitation_probability", [])
    precip_prob = max(probs[:3]) if probs else 0
    code = int(current.get("weather_code", 0))
    wind = float(current.get("wind_speed_10m", 0))
    precip = float(current.get("precipitation", 0))
    if code in WEATHER_KNOWLEDGE["severe_codes"] or wind >= WEATHER_KNOWLEDGE["high_wind_kmh"] or precip >= WEATHER_KNOWLEDGE["high_precipitation_mm"]:
        condition = "severe"
    elif code in WEATHER_KNOWLEDGE["moderate_codes"] or precip_prob >= 60:
        condition = "moderate"
    else:
        condition = "clear"
    return {"weather_condition": condition, "weather_code": code, "wind_kmh": wind,
            "precipitation_mm": precip, "precipitation_probability": precip_prob,
            "temperature_c": current.get("temperature_2m")}

class ADSPACapstone:
    def __init__(self):
        self.gate = SecureCommandGate()
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._worker_loop, name="ADSPA-Worker", daemon=True)
        self.beliefs: dict[str, Belief] = {
            "internet_available": Belief("internet_available", True, "initial configuration"),
            "weather_condition": Belief("weather_condition", "clear", "default fixture"),
            "pending_tasks": Belief("pending_tasks", 0, "task store")
        }
        self.desires = [
            Desire("meet_deadlines", 10, "tasks should be completed before due dates"),
            Desire("study_safely", 9, "avoid unnecessary travel during severe weather"),
            Desire("collaborate", 6, "coordinate a realistic study plan with peer agent")
        ]
        self.intentions: list[Intention] = []
        self.state = {"study_mode": "library", "tasks": [], "last_action": None, "completed_steps": [], "adaptation_history": []}
        self.worker_results: list[dict[str, Any]] = []
        self.cooperation = {"partner": "StudySupport-Agent-B", "status": "not_started", "proposal": None, "agreement": None}
        self.started = False

    def start(self):
        self.worker.start()
        self.started = True
        self.log("CORE", "Core loop and worker started")

    def stop(self):
        self.stop_event.set()
        self.events.put({"type": "STOP"})
        if self.started:
            self.worker.join(timeout=2)
        self.log("CORE", "Worker stopped cleanly" if not self.worker.is_alive() else "Worker stop timed out")

    def log(self, component: str, message: str):
        print(f"[{component}] {message}")

    def _worker_loop(self):
        while not self.stop_event.is_set():
            try:
                event = self.events.get(timeout=0.2)
            except queue.Empty:
                continue
            if event.get("type") == "STOP":
                self.events.task_done()
                break
            # A worker handles task events independently of the main coordinator.
            if event.get("type") == "TASK":
                result = {"task": event["task"], "worker": threading.current_thread().name, "status": "processed"}
                self.worker_results.append(result)
                self.log("WORKER", json.dumps(result, sort_keys=True))
            self.events.task_done()

    def receive_secure_command(self, envelope):
        payload = self.gate.verify(envelope)
        command, args = payload["command"], payload["args"]
        if command == "SET_STUDY_MODE":
            mode = args.get("mode")
            if mode not in {"library", "online", "offline"}:
                raise SecurityError("Invalid mode argument")
            self.state["study_mode"] = mode
            return {"study_mode": mode}
        if command == "ADD_STUDY_TASK":
            title = args.get("title")
            if not isinstance(title, str) or not title.strip() or len(title) > 200:
                raise SecurityError("Invalid task title")
            task = {"title": title.strip(), "status": "pending"}
            self.state["tasks"].append(task)
            self.events.put({"type": "TASK", "task": task})
            self.beliefs["pending_tasks"] = Belief("pending_tasks", len(self.state["tasks"]), "task store")
            return {"task_added": task}
        if command == "GET_STATUS":
            return {"study_mode": self.state["study_mode"], "tasks": len(self.state["tasks"])}
        raise SecurityError("Unsupported command")

    def update_weather(self, weather: dict[str, Any], source: str):
        for key, value in weather.items():
            self.beliefs[key] = Belief(key, value, source)
        condition = weather["weather_condition"]
        previous = self.state["study_mode"]
        if condition == "severe":
            mode, plan_key = ("online", "severe") if self.beliefs["internet_available"].value else ("offline", "severe")
            reason = "Severe weather: avoid unnecessary travel."
        elif condition == "moderate":
            mode, plan_key, reason = "online", "moderate", "Moderate weather risk: prefer remote study."
        else:
            mode, plan_key, reason = "library", "clear", "Low weather risk: library study is an option."
        self.state["study_mode"] = mode
        self.state["last_action"] = f"set_study_mode:{mode}"
        intention = Intention(f"{plan_key}_weather_plan", list(WEATHER_KNOWLEDGE["plans"][plan_key]), reason)
        for old in self.intentions:
            if old.status == "active":
                old.status = "suspended"
        self.intentions.append(intention)
        history = {"from": previous, "to": mode, "condition": condition, "source": source, "reason": reason}
        self.state["adaptation_history"].append(history)
        self.log("BDI", f"Beliefs updated; adopted intention={intention.name}; mode {previous} -> {mode}")
        self.log("PLAN", json.dumps({"intention": intention.name, "steps": intention.steps, "reason": reason}, sort_keys=True))

    def negotiate_with_peer(self):
        # Lightweight simulated cooperative exchange with explicit utility checks.
        self.cooperation["status"] = "CFP_SENT"
        self.log("COOP", f"CFP sent to {self.cooperation['partner']}: propose 90-minute focused session")
        proposal = {"minutes": 90, "study_credits": 60, "quality": 8}
        utility_coordinator = round(0.45 * (proposal["quality"]/10) + 0.35 * (proposal["study_credits"]/100) + 0.20 * (1 - abs(proposal["minutes"]-90)/120), 3)
        utility_partner = round(0.50 * (proposal["quality"]/10) + 0.30 * (proposal["minutes"]/120) + 0.20 * (proposal["study_credits"]/100), 3)
        self.cooperation["proposal"] = proposal
        self.log("COOP", f"Proposal received; coordinator_utility={utility_coordinator}; partner_utility={utility_partner}")
        if utility_coordinator >= 0.60 and utility_partner >= 0.60:
            self.cooperation.update({"status": "AGREEMENT_REACHED", "agreement": proposal})
            self.log("COOP", "Agreement accepted and committed by both simulated agents")
        else:
            self.cooperation["status"] = "NO_AGREEMENT"
            self.log("COOP", "Proposal rejected: utility threshold not met")

    def complete_action_cycle(self):
        # Independently prioritize and mark a task complete for demonstration.
        if not self.state["tasks"]:
            task = {"title": "Review next academic deadline", "status": "pending"}
            self.state["tasks"].append(task)
        task = self.state["tasks"][0]
        task["status"] = "completed"
        self.state["completed_steps"].append(task["title"])
        self.beliefs["pending_tasks"] = Belief("pending_tasks", sum(t["status"] == "pending" for t in self.state["tasks"]), "task store")
        self.state["last_action"] = f"completed:{task['title']}"
        self.log("ACTION", f"Autonomously completed task: {task['title']}")

    def dashboard(self):
        active = next((i.name for i in reversed(self.intentions) if i.status == "active"), "none")
        dashboard = {
            "agent": APP_NAME,
            "runtime": "RUNNING" if self.started and not self.stop_event.is_set() else "STOPPED",
            "study_mode": self.state["study_mode"],
            "tasks": self.state["tasks"],
            "beliefs": {k: v.value for k, v in self.beliefs.items()},
            "desires": [{"name": d.name, "priority": d.priority} for d in self.desires],
            "active_intention": active,
            "worker_results": len(self.worker_results),
            "cooperation_status": self.cooperation["status"],
            "security_events_blocked": len(self.gate.events),
            "last_action": self.state["last_action"]
        }
        print("\n=== ADSPA LIVE STATE DASHBOARD ===")
        print(json.dumps(dashboard, indent=2, sort_keys=True))
        print("=== END DASHBOARD ===\n")
        return dashboard

    def run_cycle(self, live_weather=False, latitude=13.0827, longitude=80.2707):
        self.start()
        try:
            self.log("CORE", "Production cycle started")
            # Authenticated command enters through the secure gateway.
            envelope = signed_message("adspa-coordinator-01", "ADD_STUDY_TASK",
                                      {"title": "Prepare capstone submission"},
                                      nonce="capstone-valid-nonce-0001")
            self.log("SECURITY", f"Trusted command accepted: {self.receive_secure_command(envelope)}")

            # Demonstrate malicious host rejection and unchanged state.
            before = self.state["study_mode"]
            bad_payload = {"host_id": "unknown-host-evil", "timestamp": int(time.time()),
                           "nonce": "malicious-nonce-00000001", "command": "SET_STUDY_MODE",
                           "args": {"mode": "offline"}}
            bad_envelope = {"payload": bad_payload, "signature": "0" * 64}
            try:
                self.receive_secure_command(bad_envelope)
            except SecurityError as exc:
                self.log("SECURITY", f"Malicious request safely blocked: {exc}")
            assert self.state["study_mode"] == before

            self.negotiate_with_peer()

            if live_weather:
                try:
                    raw = OpenMeteoClient().fetch(latitude, longitude)
                    weather = weather_beliefs(raw)
                    source = "Open-Meteo REST API"
                    self.log("API", "LIVE_API_FETCH_SUCCEEDED=True")
                except Exception as exc:
                    self.log("API", f"LIVE_API_FETCH_SUCCEEDED=False; using deterministic fallback; error={type(exc).__name__}: {exc}")
                    weather = {"weather_condition": "severe", "weather_code": 95, "wind_kmh": 20,
                               "precipitation_mm": 10, "precipitation_probability": 90, "temperature_c": 27}
                    source = "offline fallback fixture"
            else:
                weather = {"weather_condition": "severe", "weather_code": 95, "wind_kmh": 20,
                           "precipitation_mm": 10, "precipitation_probability": 90, "temperature_c": 27}
                source = "deterministic test fixture"
                self.log("API", "Offline deterministic weather fixture selected")
            self.update_weather(weather, source)
            self.events.join()
            self.complete_action_cycle()
            dashboard = self.dashboard()
            assert self.cooperation["status"] == "AGREEMENT_REACHED"
            assert len(self.gate.events) == 1
            assert self.state["study_mode"] == "online"
            assert self.state["tasks"][0]["status"] == "completed"
            assert self.intentions[-1].status == "active"
            print("INTEGRATED_MODULES_VERIFIED=True")
            print("AUTONOMOUS_TASK_COMPLETED=True")
            print("COOPERATIVE_AGREEMENT_REACHED=True")
            print("BDI_INTENTION_UPDATED=True")
            print("SECURITY_BREACH_BLOCKED=True")
            print("WORKER_PROCESSED_TASK=True")
            print("ALL_CAPSTONE_ASSERTIONS_PASSED=True")
            return dashboard
        finally:
            self.stop()

def main():
    parser = argparse.ArgumentParser(description="Integrated ADSPA capstone agent")
    parser.add_argument("--live-weather", action="store_true", help="try live Open-Meteo REST API; deterministic fallback on failure")
    parser.add_argument("--latitude", type=float, default=13.0827)
    parser.add_argument("--longitude", type=float, default=80.2707)
    args, _unknown = parser.parse_known_args()
    agent = ADSPACapstone()
    agent.run_cycle(args.live_weather, args.latitude, args.longitude)

if __name__ == "__main__":
    main()
