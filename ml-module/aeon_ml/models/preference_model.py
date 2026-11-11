"""AEON ML Module - Trainable scikit-learn Preference Scoring Model.

Implements a StandardScaler + LogisticRegression preference scorer over
9 engineered procurement features. Supports fitting on historical quote-selection
outcomes and safe JSON artifact serialization (no pickle).
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aeon_ml.exceptions import ModelInferenceError
from aeon_ml.models.features import FEATURE_NAMES

DEFAULT_ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "preference_model.json"


class SklearnPreferenceModel:
    """Calibrated logistic preference model backed by scikit-learn."""

    def __init__(self, version: str = "aeon-sklearn-logreg-v1.0.0") -> None:
        self.version = version
        self.scaler = StandardScaler()
        self.classifier = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        self.is_fitted = False
        self.training_metadata: Dict[str, Any] = {}

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "SklearnPreferenceModel":
        """Train the scaler and logistic preference model on labeled quote selections."""
        if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES):
            raise ValueError(
                f"Expected feature matrix shape (N, {len(FEATURE_NAMES)}), got {features.shape}"
            )
        if not np.all(np.isfinite(features)):
            raise ValueError("Training features contain NaN or infinite values.")

        scaled = self.scaler.fit_transform(features)
        self.classifier.fit(scaled, labels)
        self.is_fitted = True
        self.training_metadata = metadata or {}
        return self

    def predict_scores(self, features: np.ndarray) -> np.ndarray:
        """Predict preference scores in [0.0, 100.0] for each candidate quote row."""
        if not self.is_fitted:
            raise ModelInferenceError("Preference model must be fitted or loaded before scoring.")
        if features.ndim != 2 or features.shape[1] != len(FEATURE_NAMES):
            raise ModelInferenceError(
                f"Invalid feature shape {features.shape}; expected (*, {len(FEATURE_NAMES)})."
            )
        if not np.all(np.isfinite(features)):
            raise ModelInferenceError("Input feature matrix contains non-finite values.")

        try:
            scaled = self.scaler.transform(features)
            probs = self.classifier.predict_proba(scaled)[:, 1]
            scores = np.clip(probs * 100.0, 0.0, 100.0)
            if not np.all(np.isfinite(scores)):
                raise ModelInferenceError("Model produced non-finite prediction scores.")
            return scores
        except ModelInferenceError:
            raise
        except Exception as exc:
            raise ModelInferenceError(f"scikit-learn inference failed: {exc}", cause=exc) from exc

    def save_json(self, path: Path = DEFAULT_ARTIFACT_PATH) -> None:
        """Persist fitted scaler and classifier parameters to a JSON artifact."""
        if not self.is_fitted:
            raise RuntimeError("Cannot save an unfitted SklearnPreferenceModel.")

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "feature_names": FEATURE_NAMES,
            "scaler": {
                "mean": self.scaler.mean_.tolist(),
                "scale": self.scaler.scale_.tolist(),
                "var": self.scaler.var_.tolist(),
                "n_features_in": int(self.scaler.n_features_in_),
            },
            "classifier": {
                "coef": self.classifier.coef_.tolist(),
                "intercept": self.classifier.intercept_.tolist(),
                "classes": self.classifier.classes_.tolist(),
            },
            "training_metadata": self.training_metadata,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path = DEFAULT_ARTIFACT_PATH) -> "SklearnPreferenceModel":
        """Load fitted parameters from JSON and reconstruct scikit-learn objects."""
        if not path.exists():
            raise ModelInferenceError(f"Model artifact not found at '{path}'.")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("feature_names") != FEATURE_NAMES:
                raise ModelInferenceError("Model artifact feature schema mismatch.")

            model = cls(version=data.get("version", "aeon-sklearn-logreg-v1.0.0"))

            scaler_data = data["scaler"]
            model.scaler.mean_ = np.asarray(scaler_data["mean"], dtype=np.float64)
            model.scaler.scale_ = np.asarray(scaler_data["scale"], dtype=np.float64)
            model.scaler.var_ = np.asarray(scaler_data["var"], dtype=np.float64)
            model.scaler.n_features_in_ = int(scaler_data["n_features_in"])

            clf_data = data["classifier"]
            model.classifier.coef_ = np.asarray(clf_data["coef"], dtype=np.float64)
            model.classifier.intercept_ = np.asarray(clf_data["intercept"], dtype=np.float64)
            model.classifier.classes_ = np.asarray(clf_data["classes"], dtype=np.int64)
            model.classifier.n_features_in_ = int(scaler_data["n_features_in"])

            model.training_metadata = data.get("training_metadata", {})
            model.is_fitted = True
            return model
        except ModelInferenceError:
            raise
        except Exception as exc:
            raise ModelInferenceError(f"Failed to load model artifact '{path}': {exc}", cause=exc) from exc
