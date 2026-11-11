"""Train the scikit-learn preference ranker and print held-out benchmark accuracy metrics.

Usage:
    python scripts/train_and_evaluate.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aeon_ml.evaluation import train_and_benchmark


def main() -> None:
    print("=" * 78)
    print("AEON ML Layer - Training & Disjoint Synthetic Benchmark Evaluation")
    print("=" * 78)
    print("Training on 1,200 synthetic procurement requisitions (seed=42)...")
    print("Evaluating on 500 unseen held-out requisitions (seed=999)...\n")

    reports = train_and_benchmark(
        train_requests=1200,
        eval_requests=500,
        train_seed=42,
        eval_seed=999,
        save_artifact=True,
    )

    header = f"{'Model':<34} | {'Top-1 Acc':>9} | {'Top-2 Hit':>9} | {'MRR':>6} | {'NDCG@3':>7} | {'Compliant':>9}"
    print(header)
    print("-" * len(header))
    for report in reports.values():
        print(
            f"{report.model_name:<34} | "
            f"{report.top1_accuracy * 100:>8.2f}% | "
            f"{report.top2_hit_rate * 100:>8.2f}% | "
            f"{report.mrr:>6.4f} | "
            f"{report.ndcg_at_3:>7.4f} | "
            f"{report.constraint_compliance_rate * 100:>8.2f}%"
        )
    print("\nSaved trained model weights to aeon_ml/models/artifacts/preference_model.json")


if __name__ == "__main__":
    main()

