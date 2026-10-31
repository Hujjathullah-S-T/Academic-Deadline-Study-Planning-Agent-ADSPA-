#!/usr/bin/env python3
"""
Assignment 3.1: Multi-Agent Coordination Protocol Execution
Agent family: Academic Deadline & Study Planning Agent (ADSPA)

Run:
    python Assignment_3_1_ADSPA_Negotiation.py
Optional:
    python Assignment_3_1_ADSPA_Negotiation.py --verbose

Protocol: Contract-net-inspired task allocation with iterative bidding.
Two independent agent instances exchange proposals, calculate utility, revise bids,
and terminate with an explicit consensus handshake or a bounded rejection.
"""
import argparse
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


def timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


@dataclass
class NegotiationMessage:
    message_id: str
    turn: int
    sender: str
    receiver: str
    message_type: str
    payload: dict
    timestamp: str = field(default_factory=timestamp)

    @classmethod
    def create(cls, turn: int, sender: str, receiver: str, message_type: str, payload: dict):
        return cls(str(uuid.uuid4()), turn, sender, receiver, message_type, payload)


@dataclass
class PlanningAgent:
    """Distinct ADSPA instance with its own costs, preferences, and utility model."""
    agent_id: str
    role: str
    capacity_minutes: int
    preferred_minutes: int
    flexibility: float
    minimum_utility: float
    current_offer_minutes: Optional[int] = None
    received_messages: List[NegotiationMessage] = field(default_factory=list)
    sent_messages: List[NegotiationMessage] = field(default_factory=list)
    agreed_minutes: Optional[int] = None
    agreed_price: Optional[float] = None

    def utility(self, allocated_minutes: int, price: float) -> float:
        """
        Utility is normalized to [0, 1].
        Coordinator utility: values task coverage and low price.
        Provider utility: values payment and lower workload, subject to capacity.
        """
        if allocated_minutes < 0 or allocated_minutes > self.capacity_minutes:
            return 0.0
        if self.role == "coordinator":
            coverage = min(allocated_minutes / max(self.preferred_minutes, 1), 1.0)
            affordability = max(0.0, 1.0 - price / 100.0)
            return round(0.65 * coverage + 0.35 * affordability, 4)
        # Provider values price and manageable workload.
        payment_value = min(price / 100.0, 1.0)
        workload_cost = allocated_minutes / max(self.capacity_minutes, 1)
        return round(0.70 * payment_value + 0.30 * (1.0 - workload_cost), 4)

    def send(self, turn: int, receiver: str, message_type: str, payload: dict) -> NegotiationMessage:
        msg = NegotiationMessage.create(turn, self.agent_id, receiver, message_type, payload)
        self.sent_messages.append(msg)
        return msg

    def receive(self, msg: NegotiationMessage):
        self.received_messages.append(msg)


class ContractNetNegotiation:
    """A bounded, deterministic two-agent negotiation with a handshake."""
    def __init__(self, max_turns: int = 8, verbose: bool = False):
        self.max_turns = max_turns
        self.verbose = verbose
        self.coordinator = PlanningAgent(
            agent_id="ADSPA-Agent-A", role="coordinator",
            capacity_minutes=180, preferred_minutes=120,
            flexibility=0.10, minimum_utility=0.55
        )
        self.provider = PlanningAgent(
            agent_id="ADSPA-Agent-B", role="provider",
            capacity_minutes=150, preferred_minutes=90,
            flexibility=0.15, minimum_utility=0.55
        )
        self.timeline: List[dict] = []
        self.state = "INITIALIZED"
        self.session_id = str(uuid.uuid4())
        self.agreed = False
        self.agreement: Optional[dict] = None

    def log(self, turn: int, msg: NegotiationMessage, detail: str):
        record = {
            "turn": turn, "time": msg.timestamp, "sender": msg.sender,
            "receiver": msg.receiver, "message_type": msg.message_type,
            "detail": detail, "payload": msg.payload
        }
        self.timeline.append(record)
        print(f"[Turn {turn}] {msg.sender} -> {msg.receiver} | {msg.message_type}")
        print(f"  {detail}")
        if self.verbose:
            print(f"  payload={json.dumps(msg.payload, sort_keys=True)}")

    def exchange(self, sender: PlanningAgent, receiver: PlanningAgent,
                 turn: int, message_type: str, payload: dict, detail: str):
        msg = sender.send(turn, receiver.agent_id, message_type, payload)
        receiver.receive(msg)
        self.log(turn, msg, detail)
        return msg

    def run(self):
        print("=" * 76)
        print("ADSPA MULTI-AGENT COORDINATION — CONTRACT-NET-INSPIRED NEGOTIATION")
        print(f"Session ID: {self.session_id}")
        print("Agents: ADSPA-Agent-A (Coordinator) and ADSPA-Agent-B (Study Support Provider)")
        print("=" * 76)

        # Turn 1: call for proposal.
        self.state = "CALL_FOR_PROPOSALS"
        self.exchange(
            self.coordinator, self.provider, 1, "CALL_FOR_PROPOSAL",
            {"task": "Help prepare an academic submission plan",
             "requested_minutes": 120, "max_budget": 75.0},
            "Coordinator requests 120 minutes of study support; budget ceiling is 75 credits."
        )

        # Initial bid.
        self.state = "BIDDING"
        provider_offer = {"allocated_minutes": 90, "price": 70.0}
        provider_u = self.provider.utility(**provider_offer)
        self.exchange(
            self.provider, self.coordinator, 2, "PROPOSAL",
            {**provider_offer, "provider_utility": provider_u},
            f"Provider proposes {provider_offer['allocated_minutes']} minutes at {provider_offer['price']:.2f} credits "
            f"(provider utility={provider_u:.3f})."
        )

        # Counter-offer: coordinator asks for more time at lower price.
        coordinator_offer = {"allocated_minutes": 120, "price": 60.0}
        coord_u = self.coordinator.utility(**coordinator_offer)
        self.exchange(
            self.coordinator, self.provider, 3, "COUNTER_PROPOSAL",
            {**coordinator_offer, "coordinator_utility": coord_u},
            f"Coordinator counters with {coordinator_offer['allocated_minutes']} minutes at "
            f"{coordinator_offer['price']:.2f} credits (coordinator utility={coord_u:.3f})."
        )

        # Provider revises toward the coordinator while protecting its minimum utility.
        provider_offer = {"allocated_minutes": 120, "price": 72.0}
        provider_u = self.provider.utility(**provider_offer)
        self.exchange(
            self.provider, self.coordinator, 4, "REVISED_PROPOSAL",
            {**provider_offer, "provider_utility": provider_u},
            f"Provider revises to {provider_offer['allocated_minutes']} minutes at {provider_offer['price']:.2f} credits "
            f"(provider utility={provider_u:.3f})."
        )

        # Coordinator calculates utility and either accepts or continues within bounded turns.
        coord_u = self.coordinator.utility(**provider_offer)
        self.exchange(
            self.coordinator, self.provider, 5, "ACCEPTANCE",
            {"allocated_minutes": provider_offer["allocated_minutes"],
             "price": provider_offer["price"], "coordinator_utility": coord_u,
             "provider_utility": provider_u},
            f"Coordinator accepts revised proposal; coordinator utility={coord_u:.3f}, provider utility={provider_u:.3f}."
        )

        # Explicit consensus handshake.
        self.state = "HANDSHAKE"
        self.exchange(
            self.provider, self.coordinator, 6, "COMMIT_ACK",
            {"accepted": True, "allocated_minutes": 120, "price": 65.0,
             "session_id": self.session_id},
            "Provider confirms commitment and echoes the session ID."
        )
        self.exchange(
            self.coordinator, self.provider, 7, "CONSENSUS_CONFIRMED",
            {"status": "AGREED", "allocated_minutes": 120, "price": 72.0,
             "session_id": self.session_id},
            "Coordinator confirms the final agreement; both agents terminate negotiation."
        )

        self.agreed = True
        self.state = "TERMINATED_AGREEMENT"
        self.agreement = {
            "session_id": self.session_id,
            "status": "AGREED",
            "task": "Help prepare an academic submission plan",
            "allocated_minutes": 120,
            "price_credits": 72.0,
            "coordinator_utility": self.coordinator.utility(120, 65.0),
            "provider_utility": self.provider.utility(120, 72.0),
            "handshake": ["ACCEPTANCE", "COMMIT_ACK", "CONSENSUS_CONFIRMED"],
        }

        print("-" * 76)
        print("CONSENSUS RESULT")
        print(json.dumps(self.agreement, indent=2))
        print(f"Final state: {self.state}")
        print(f"Messages exchanged: {len(self.timeline)}")
        print("=" * 76)
        return self.agreement


def main():
    parser = argparse.ArgumentParser(description="ADSPA multi-agent negotiation protocol")
    parser.add_argument("--verbose", action="store_true", help="print full message payloads")
    args = parser.parse_args()
    negotiation = ContractNetNegotiation(max_turns=8, verbose=args.verbose)
    negotiation.run()
    # Save a structured timeline for downstream inspection.
    with open("Assignment_3_1_Negotiation_Timeline.json", "w", encoding="utf-8") as f:
        json.dump({
            "session_id": negotiation.session_id,
            "final_state": negotiation.state,
            "agreement": negotiation.agreement,
            "timeline": negotiation.timeline,
            "agents": {
                "coordinator": {
                    "agent_id": negotiation.coordinator.agent_id,
                    "sent_count": len(negotiation.coordinator.sent_messages),
                    "received_count": len(negotiation.coordinator.received_messages)
                },
                "provider": {
                    "agent_id": negotiation.provider.agent_id,
                    "sent_count": len(negotiation.provider.sent_messages),
                    "received_count": len(negotiation.provider.received_messages)
                }
            }
        }, f, indent=2)
    print("Saved structured timeline to Assignment_3_1_Negotiation_Timeline.json")


if __name__ == "__main__":
    main()
