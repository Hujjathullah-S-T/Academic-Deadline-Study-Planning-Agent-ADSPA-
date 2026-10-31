#!/usr/bin/env python3
"""
Assignment 5.1 — Agent Authentication and Host Integrity Verification
Agent: Academic Deadline & Study Planning Agent (ADSPA)

Educational demonstration using HMAC-SHA256, trusted-host allowlisting,
timestamp validation, nonce-based replay protection, and command allowlisting.
Uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

# DEMO ONLY: use a secret manager/environment variable in real deployments.
# This shared secret authenticates payload integrity and possession of the key;
# it is not a public-key digital-signature scheme.
DEMO_SHARED_SECRET = b"ADSPA-DEMO-SECRET-CHANGE-ME"

TRUSTED_HOSTS = {
    "adspa-controller-01": {
        "secret": DEMO_SHARED_SECRET,
        "host_label": "Trusted ADSPA Controller",
    }
}
ALLOWED_COMMANDS = {"SET_STUDY_MODE", "ADD_STUDY_TASK", "GET_STATUS"}
MAX_CLOCK_SKEW_SECONDS = 300


class AuthenticationError(Exception):
    """Raised when a payload fails one or more security checks."""


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Stable serialization is required so sender and receiver sign identical bytes."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_payload(payload: dict[str, Any], secret: bytes) -> str:
    """Create an HMAC-SHA256 signature over the canonical payload."""
    return hmac.new(secret, canonical_json(payload), hashlib.sha256).hexdigest()


def create_signed_envelope(
    host_id: str,
    command: str,
    args: dict[str, Any] | None = None,
    *,
    secret: bytes = DEMO_SHARED_SECRET,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Build a signed message, as a trusted sender would."""
    payload = {
        "host_id": host_id,
        "timestamp": int(time.time()) if timestamp is None else int(timestamp),
        "nonce": nonce or secrets.token_hex(16),
        "command": command,
        "args": args or {},
    }
    return {"payload": payload, "signature": sign_payload(payload, secret)}


@dataclass
class ADSPAAgent:
    trusted_hosts: dict[str, dict[str, Any]] = field(default_factory=lambda: TRUSTED_HOSTS.copy())
    allowed_commands: set[str] = field(default_factory=lambda: set(ALLOWED_COMMANDS))
    max_clock_skew_seconds: int = MAX_CLOCK_SKEW_SECONDS
    seen_nonces: set[tuple[str, str]] = field(default_factory=set)
    state: dict[str, Any] = field(default_factory=lambda: {
        "study_mode": "library",
        "tasks": [],
        "last_command": None,
        "security_events": [],
    })

    def reject(self, reason: str, host_id: str | None = None) -> None:
        event = {"event": "BLOCKED_UNAUTHORIZED_REQUEST", "reason": reason, "host_id": host_id}
        self.state["security_events"].append(event)
        print("[SECURITY] BLOCKED_UNAUTHORIZED_REQUEST " + json.dumps(event, sort_keys=True))
        raise AuthenticationError(reason)

    def verify_and_process(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Authenticate origin, integrity, freshness, replay status, and command."""
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
            self.reject("Malformed envelope")

        payload = envelope["payload"]
        signature = envelope["signature"]
        if not isinstance(payload, dict) or not isinstance(signature, str):
            self.reject("Malformed payload or signature")

        host_id = payload.get("host_id")
        if not isinstance(host_id, str) or host_id not in self.trusted_hosts:
            self.reject("Untrusted or unknown host", host_id if isinstance(host_id, str) else None)

        required = {"host_id", "timestamp", "nonce", "command", "args"}
        if set(payload) != required:
            self.reject("Payload schema mismatch", host_id)

        secret = self.trusted_hosts[host_id]["secret"]
        expected = sign_payload(payload, secret)
        if not hmac.compare_digest(signature, expected):
            self.reject("Invalid HMAC signature; payload may be modified", host_id)

        try:
            timestamp = int(payload["timestamp"])
        except (TypeError, ValueError):
            self.reject("Invalid timestamp", host_id)
        if abs(int(time.time()) - timestamp) > self.max_clock_skew_seconds:
            self.reject("Expired or future-dated payload", host_id)

        nonce = payload.get("nonce")
        if not isinstance(nonce, str) or len(nonce) < 16:
            self.reject("Invalid nonce", host_id)
        nonce_key = (host_id, nonce)
        if nonce_key in self.seen_nonces:
            self.reject("Replay detected: nonce already used", host_id)

        command = payload.get("command")
        if not isinstance(command, str) or command not in self.allowed_commands:
            self.reject("Command not allowlisted", host_id)
        args = payload.get("args")
        if not isinstance(args, dict):
            self.reject("Command arguments must be an object", host_id)

        # Mark nonce only after all authenticity/freshness checks pass.
        self.seen_nonces.add(nonce_key)
        result = self._execute(command, args)
        self.state["last_command"] = command
        print("[SECURITY] ACCEPTED_TRUSTED_REQUEST " + json.dumps({
            "host_id": host_id, "command": command, "result": result
        }, sort_keys=True))
        return {"accepted": True, "host_id": host_id, "command": command, "result": result}

    def _execute(self, command: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute only narrowly defined, validated operations; never eval/exec input."""
        if command == "SET_STUDY_MODE":
            mode = args.get("mode")
            if mode not in {"library", "online", "offline"}:
                raise AuthenticationError("Invalid study mode")
            self.state["study_mode"] = mode
            return {"study_mode": mode}
        if command == "ADD_STUDY_TASK":
            title = args.get("title")
            if not isinstance(title, str) or not title.strip() or len(title) > 200:
                raise AuthenticationError("Task title must be 1–200 characters")
            task = {"title": title.strip(), "status": "pending"}
            self.state["tasks"].append(task)
            return {"task_added": task}
        if command == "GET_STATUS":
            return {"study_mode": self.state["study_mode"], "task_count": len(self.state["tasks"])}
        # Defense in depth; should be unreachable after command allowlisting.
        raise AuthenticationError("Unsupported command")


def run_demo() -> None:
    print("=== ADSPA Assignment 5.1: Authentication + Host Integrity ===")
    agent = ADSPAAgent()
    print("Trusted hosts:", sorted(agent.trusted_hosts))
    print("Allowed commands:", sorted(agent.allowed_commands))

    # 1) Trusted signed request must be accepted.
    trusted = create_signed_envelope(
        "adspa-controller-01", "SET_STUDY_MODE", {"mode": "online"},
        nonce="trusted-demo-nonce-0001"
    )
    accepted = agent.verify_and_process(trusted)
    assert accepted["accepted"] is True
    assert agent.state["study_mode"] == "online"

    # 2) Simulated tampering: change command after signing; HMAC must fail.
    tampered = create_signed_envelope(
        "adspa-controller-01", "SET_STUDY_MODE", {"mode": "library"},
        nonce="tamper-demo-nonce-0002"
    )
    tampered["payload"]["args"]["mode"] = "offline"
    try:
        agent.verify_and_process(tampered)
        raise AssertionError("Tampered request should have been rejected")
    except AuthenticationError:
        print("[TEST] Tampered payload rejected as expected.")

    # 3) Simulated unknown/untrusted host.
    untrusted = create_signed_envelope(
        "attacker-host-99", "SET_STUDY_MODE", {"mode": "offline"},
        secret=b"attacker-does-not-have-trusted-key",
        nonce="attacker-demo-nonce-0003"
    )
    try:
        agent.verify_and_process(untrusted)
        raise AssertionError("Untrusted host should have been rejected")
    except AuthenticationError:
        print("[TEST] Untrusted host rejected as expected.")

    # 4) Signed but disallowed command from trusted host.
    bad_command = create_signed_envelope(
        "adspa-controller-01", "DELETE_ALL_DATA", {},
        nonce="bad-command-demo-nonce-0004"
    )
    try:
        agent.verify_and_process(bad_command)
        raise AssertionError("Disallowed command should have been rejected")
    except AuthenticationError:
        print("[TEST] Non-allowlisted command rejected as expected.")

    # 5) Replay a previously accepted valid envelope.
    try:
        agent.verify_and_process(trusted)
        raise AssertionError("Replayed request should have been rejected")
    except AuthenticationError:
        print("[TEST] Replayed request rejected as expected.")

    assert agent.state["study_mode"] == "online", "Rejected requests must not mutate study mode"
    assert len(agent.state["security_events"]) == 4
    print("Final study mode:", agent.state["study_mode"])
    print("Blocked unauthorized events:", len(agent.state["security_events"]))
    print("TAMPERED_PAYLOAD_BLOCKED=True")
    print("UNTRUSTED_HOST_BLOCKED=True")
    print("DISALLOWED_COMMAND_BLOCKED=True")
    print("REPLAY_BLOCKED=True")
    print("REJECTED_REQUESTS_DID_NOT_CHANGE_STATE=True")
    print("ALL_SECURITY_ASSERTIONS_PASSED=True")


def main() -> None:
    parser = argparse.ArgumentParser(description="ADSPA authentication and host integrity demo")
    parser.add_argument("--demo", action="store_true", help="run deterministic security verification tests")
    # parse_known_args allows use inside Jupyter/Colab, which injects its own -f argument.
    args, _unknown = parser.parse_known_args()
    run_demo()


if __name__ == "__main__":
    main()
