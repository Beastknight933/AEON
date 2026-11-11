"""Minimal Runnable Example for AEON ML Module.

Demonstrates creating a RecommendationRequest, invoking recommend(),
and inspecting the structured RecommendationResponse.

Run with:
    python examples/minimal_runnable.py
"""

import sys
from pathlib import Path
from pprint import pprint

# Ensure project root is in sys.path when running as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aeon_ml import (
    CriteriaWeights,
    ProcurementRequirements,
    RecommendationRequest,
    SupplierAttributes,
    SupplierQuote,
    recommend,
)


def run_minimal_example() -> None:
    print("=" * 70)
    print("AEON Procurement Quote Recommendation - Minimal Runnable Example")
    print("=" * 70)

    # 1. Prepare candidate supplier quotes
    quotes = [
        SupplierQuote(
            quote_id="QUOTE-ACME-001",
            supplier_id="SUP-ACME-CORP",
            amount=14500.00,
            currency="USD",
            supplier_attributes=SupplierAttributes(
                delivery_days=8,
                quality_score=94.5,
                reliability_rating=91.0,
                on_time_delivery_rate=0.96,
                esg_score=85.0,
                warranty_months=24,
            ),
        ),
        SupplierQuote(
            quote_id="QUOTE-FASTLOG-002",
            supplier_id="SUP-FASTLOG-INC",
            amount=15800.00,
            currency="USD",
            supplier_attributes=SupplierAttributes(
                delivery_days=4,
                quality_score=89.0,
                reliability_rating=95.0,
                on_time_delivery_rate=0.98,
                esg_score=78.0,
                warranty_months=12,
            ),
        ),
        SupplierQuote(
            quote_id="QUOTE-BUDGET-003",
            supplier_id="SUP-BUDGET-PARTS",
            amount=12900.00,
            currency="USD",
            supplier_attributes=SupplierAttributes(
                delivery_days=15,  # Exceeds 10-day requirement
                quality_score=78.0,
                reliability_rating=82.0,
                on_time_delivery_rate=0.84,
                esg_score=70.0,
                warranty_months=6,
            ),
        ),
    ]

    # 2. Define procurement requirements
    requirements = ProcurementRequirements(
        max_delivery_days=10,
        target_price=15000.00,
        min_quality_score=80.0,
        min_reliability_rating=85.0,
        priority_weights=CriteriaWeights(
            price_weight=0.35,
            speed_weight=0.30,
            quality_weight=0.20,
            reliability_weight=0.15,
        ),
        notes="Urgent enterprise hardware refresh required before quarter end.",
    )

    # 3. Construct input request payload
    request = RecommendationRequest(
        purchase_id="PR-2026-HQ-0492",
        currency="USD",
        requirements=requirements,
        quotes=quotes,
    )

    print(f"\n[INPUT] Purchase ID: {request.purchase_id}")
    print(f"[INPUT] Currency: {request.currency}")
    print(f"[INPUT] Candidate Quotes: {len(request.quotes)}")
    print(f"[INPUT] Max Delivery Days Constraint: {requirements.max_delivery_days} days")

    # 4. Invoke the ML recommendation module
    response = recommend(request)

    # 5. Output inspection
    print("\n" + "-" * 70)
    print(f"[RESULT] Recommended Quote ID : {response.recommended_quote_id}")
    print(f"[RESULT] Model Version        : {response.model_version}")
    print(f"[RESULT] Evaluated At (UTC)   : {response.evaluated_at}")
    print("-" * 70)
    print(f"\n[REASONING]:\n{response.reasoning}\n")

    print("-" * 70)
    print("EVALUATION METRICS & RANKINGS (Documented scale: 0.0 to 100.0):")
    print("-" * 70)
    for score in response.scores:
        status_flag = "[MET REQS]" if score.meets_requirements else "[FAILED REQ]"
        print(
            f"Rank {score.rank}: Quote '{score.quote_id}' | "
            f"Supplier: {score.supplier_id:<18} | "
            f"Price: {score.currency} {score.amount:>9,.2f} | "
            f"Score: {score.composite_score:>5.2f}/100 {status_flag}"
        )
        print(
            f"        Subscores -> Price: {score.sub_scores.price_score:.1f} | "
            f"Speed: {score.sub_scores.speed_score:.1f} | "
            f"Quality: {score.sub_scores.quality_score:.1f} | "
            f"Reliability: {score.sub_scores.reliability_score:.1f} | "
            f"Penalty: -{score.sub_scores.penalty_deduction:.1f}"
        )
        if score.key_drivers:
            print(f"        Key Drivers: {'; '.join(score.key_drivers)}")
        print()

    print("=" * 70)
    print("Execution completed successfully. Structured response ready for backend adapter.")
    print("=" * 70)


if __name__ == "__main__":
    run_minimal_example()
