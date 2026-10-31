#!/usr/bin/env python3
"""
Assignment 3.2: Self-Interested Agent Utility Optimization for E-Commerce
Agent family: Academic Deadline & Study Planning Agent (ADSPA)

Scenario:
ADSPA acts as a self-interested e-commerce agent selecting one study-product
bundle from ten candidates under a fixed budget and hard constraints.

Run:
    python Assignment_3_2_ADSPA_Utility_Optimization.py
    python Assignment_3_2_ADSPA_Utility_Optimization.py --verbose

Uses only the Python standard library.
"""
import argparse
import json
import math
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass(frozen=True)
class Offer:
    offer_id: str
    product: str
    price: float
    quality: float          # 0..10
    delivery_days: int
    convenience: float      # 0..10
    study_value: float      # 0..10
    stock: int
    shipping_fee: float = 0.0


@dataclass
class ScoredOffer:
    offer: Offer
    utility: float
    feasible: bool
    reasons: List[str]


# Fixed constraints for this mock e-commerce decision.
BUDGET = 100.0
MAX_DELIVERY_DAYS = 5
MIN_QUALITY = 6.0
MIN_STUDY_VALUE = 6.0
WEIGHTS = {
    "quality": 0.30,
    "delivery": 0.20,
    "convenience": 0.20,
    "study_value": 0.30,
}


def utility_function(offer: Offer) -> float:
    """
    U(o) = 0.30*Q + 0.20*D + 0.20*C + 0.30*S - 0.04*P_total

    Q, C, S are normalized 0..10 scores.
    D = 10 * (1 - delivery_days / 10), clipped to [0, 10].
    P_total = price + shipping_fee.
    The price penalty is 0.04 utility points per currency unit.
    """
    delivery_score = max(0.0, min(10.0, 10.0 * (1.0 - offer.delivery_days / 10.0)))
    total_price = offer.price + offer.shipping_fee
    return round(
        WEIGHTS["quality"] * offer.quality
        + WEIGHTS["delivery"] * delivery_score
        + WEIGHTS["convenience"] * offer.convenience
        + WEIGHTS["study_value"] * offer.study_value
        - 0.04 * total_price,
        4,
    )


def validate_and_check(offer: Offer) -> List[str]:
    """Return all reasons an offer is infeasible; handles invalid boundaries."""
    reasons = []
    numeric_nonnegative = {
        "price": offer.price,
        "shipping_fee": offer.shipping_fee,
        "quality": offer.quality,
        "convenience": offer.convenience,
        "study_value": offer.study_value,
    }
    for field_name, value in numeric_nonnegative.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            reasons.append(f"{field_name} must be finite and non-negative")
    for field_name, value in [("quality", offer.quality), ("convenience", offer.convenience), ("study_value", offer.study_value)]:
        if isinstance(value, (int, float)) and math.isfinite(value) and not 0 <= value <= 10:
            reasons.append(f"{field_name} must be in [0, 10]")
    if not isinstance(offer.delivery_days, int) or offer.delivery_days < 0:
        reasons.append("delivery_days must be a non-negative integer")
    if not isinstance(offer.stock, int) or offer.stock < 0:
        reasons.append("stock must be a non-negative integer")
    total_price = offer.price + offer.shipping_fee
    if math.isfinite(total_price) and total_price > BUDGET:
        reasons.append(f"total price {total_price:.2f} exceeds budget {BUDGET:.2f}")
    if offer.delivery_days > MAX_DELIVERY_DAYS:
        reasons.append(f"delivery exceeds {MAX_DELIVERY_DAYS} days")
    if offer.quality < MIN_QUALITY:
        reasons.append(f"quality below minimum {MIN_QUALITY}")
    if offer.study_value < MIN_STUDY_VALUE:
        reasons.append(f"study value below minimum {MIN_STUDY_VALUE}")
    if offer.stock < 1:
        reasons.append("out of stock")
    return reasons


def build_offers() -> List[Offer]:
    """Ten deterministic, deliberately varied mock e-commerce offers."""
    return [
        Offer("O01", "Focus Desk Lamp", 28.0, 8.5, 2, 8.0, 7.5, 12, 3.0),
        Offer("O02", "Premium Study Bundle", 76.0, 9.8, 1, 9.0, 9.8, 5, 4.0),
        Offer("O03", "Budget Notebook Pack", 14.0, 6.5, 4, 7.0, 6.2, 20, 2.0),
        Offer("O04", "Ergonomic Study Kit", 54.0, 9.0, 2, 8.8, 9.2, 7, 4.0),
        Offer("O05", "Wireless Keyboard", 39.0, 8.0, 6, 8.5, 7.0, 0, 0.0),
        Offer("O06", "Basic Reading Light", 18.0, 5.5, 1, 7.0, 5.5, 18, 2.0),
        Offer("O07", "Noise-Cancelling Headphones", 88.0, 9.5, 3, 9.0, 9.0, 4, 5.0),
        Offer("O08", "Study Planner Set", 22.0, 7.5, 3, 8.0, 8.5, 1, 2.0),
        Offer("O09", "Refurbished Tablet", 95.0, 9.0, 5, 7.5, 9.5, 2, 8.0),
        Offer("O10", "Exam Essentials Bundle", 61.0, 8.8, 2, 8.5, 9.0, 3, 2.0),
    ]


def score_offers(offers: List[Offer]) -> List[ScoredOffer]:
    results = []
    for offer in offers:
        reasons = validate_and_check(offer)
        feasible = len(reasons) == 0
        # Invalid numeric inputs are not scored as competitive candidates.
        try:
            score = utility_function(offer) if feasible else float("-inf")
        except (TypeError, ValueError, OverflowError):
            score = float("-inf")
        results.append(ScoredOffer(offer, score, feasible, reasons))
    return results


def select_best(scored: List[ScoredOffer]) -> Optional[ScoredOffer]:
    """Exhaustive search over all feasible candidates; deterministic tie-break by offer_id."""
    feasible = [item for item in scored if item.feasible and math.isfinite(item.utility)]
    if not feasible:
        return None
    return sorted(feasible, key=lambda item: (-item.utility, item.offer.offer_id))[0]


def boundary_tests() -> dict:
    """Small tests for budget, range, delivery and inventory constraints."""
    tests = [
        Offer("X01", "Over-budget item", 99, 9, 1, 9, 9, 1, 2),
        Offer("X02", "Invalid quality", 20, 11, 2, 8, 8, 2, 0),
        Offer("X03", "No stock", 20, 8, 2, 8, 8, 0, 0),
        Offer("X04", "Too slow", 20, 8, 8, 8, 8, 2, 0),
        Offer("X05", "Negative price", -1, 8, 2, 8, 8, 2, 0),
    ]
    scored = score_offers(tests)
    return {
        "tests_run": len(tests),
        "all_invalid_or_infeasible_rejected": all(not item.feasible for item in scored),
        "details": [
            {"offer_id": item.offer.offer_id, "feasible": item.feasible, "reasons": item.reasons}
            for item in scored
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="ADSPA self-interested utility optimization")
    parser.add_argument("--verbose", action="store_true", help="print constraint details for every option")
    args = parser.parse_args()

    offers = build_offers()
    scored = score_offers(offers)
    best = select_best(scored)

    print("=" * 88)
    print("ASSIGNMENT 3.2 — SELF-INTERESTED AGENT UTILITY OPTIMIZATION")
    print("Agent: Academic Deadline & Study Planning Agent (ADSPA)")
    print(f"Constraints: budget <= {BUDGET:.2f}, delivery <= {MAX_DELIVERY_DAYS} days, "
          f"quality >= {MIN_QUALITY}, study_value >= {MIN_STUDY_VALUE}, stock >= 1")
    print("=" * 88)
    print(f"{'ID':<5} {'Offer':<31} {'Total':>8} {'Utility':>9} {'Feasible':>10}")
    print("-" * 88)
    for item in scored:
        total = item.offer.price + item.offer.shipping_fee
        utility_text = f"{item.utility:.4f}" if item.feasible else "REJECTED"
        print(f"{item.offer.offer_id:<5} {item.offer.product[:30]:<31} {total:>8.2f} "
              f"{utility_text:>9} {str(item.feasible):>10}")
        if args.verbose and item.reasons:
            for reason in item.reasons:
                print(f"      - {reason}")
    print("-" * 88)
    if best:
        print("OPTIMAL FEASIBLE CHOICE")
        print(f"  Offer: {best.offer.offer_id} — {best.offer.product}")
        print(f"  Total price: {best.offer.price + best.offer.shipping_fee:.2f}")
        print(f"  Utility: {best.utility:.4f}")
        print(f"  Feasible candidates: {sum(x.feasible for x in scored)} / {len(scored)}")
        print(f"  Search: exhaustive argmax over all feasible offers")
    else:
        print("NO FEASIBLE OFFER — agent abstains rather than violating constraints")

    tests = boundary_tests()
    print("\nCONSTRAINT BOUNDARY TESTS")
    print(f"  Tests run: {tests['tests_run']}")
    print(f"  All invalid/infeasible offers rejected: {tests['all_invalid_or_infeasible_rejected']}")
    for test in tests["details"]:
        print(f"  {test['offer_id']}: feasible={test['feasible']} | {'; '.join(test['reasons'])}")
    print("=" * 88)

    result = {
        "agent": "Academic Deadline & Study Planning Agent (ADSPA)",
        "constraints": {
            "budget": BUDGET,
            "max_delivery_days": MAX_DELIVERY_DAYS,
            "min_quality": MIN_QUALITY,
            "min_study_value": MIN_STUDY_VALUE,
            "minimum_stock": 1,
        },
        "utility_equation": "U(o)=0.30Q + 0.20D + 0.20C + 0.30S - 0.04P_total",
        "offers": [
            {
                "offer_id": x.offer.offer_id,
                "product": x.offer.product,
                "total_price": x.offer.price + x.offer.shipping_fee,
                "utility": x.utility if math.isfinite(x.utility) else None,
                "feasible": x.feasible,
                "rejection_reasons": x.reasons,
            } for x in scored
        ],
        "selected_offer": None if best is None else {
            "offer_id": best.offer.offer_id,
            "product": best.offer.product,
            "total_price": best.offer.price + best.offer.shipping_fee,
            "utility": best.utility,
        },
        "boundary_tests": tests,
    }
    with open("Assignment_3_2_Optimization_Results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print("Saved machine-readable results to Assignment_3_2_Optimization_Results.json")


if __name__ == "__main__":
    main()
