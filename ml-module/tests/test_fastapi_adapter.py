"""Integration test for AEON FastAPI backend adapter."""

import pytest
from fastapi.testclient import TestClient
from examples.fastapi_adapter import app


@pytest.fixture
def client():
    return TestClient(app)


def test_fastapi_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["ml_module"] == "aeon_ml"


def test_fastapi_recommendation_endpoint(client):
    payload = {
        "purchase_id": "REQ-FASTAPI-TEST",
        "currency": "USD",
        "requirements": {
            "max_delivery_days": 10,
            "target_price": 5000.0,
        },
        "quotes": [
            {
                "quote_id": "Q-FAST-01",
                "supplier_id": "SUP-FAST",
                "amount": 4500.0,
                "currency": "USD",
                "supplier_attributes": {
                    "delivery_days": 5,
                    "quality_score": 90.0,
                    "reliability_rating": 88.0,
                },
            },
            {
                "quote_id": "Q-SLOW-02",
                "supplier_id": "SUP-SLOW",
                "amount": 4200.0,
                "currency": "USD",
                "supplier_attributes": {
                    "delivery_days": 12,
                    "quality_score": 80.0,
                    "reliability_rating": 80.0,
                },
            },
        ],
    }

    response = client.post("/api/v1/procurement/recommendations", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["purchase_id"] == "REQ-FASTAPI-TEST"
    assert data["recommended_quote_id"] == "Q-FAST-01"
    assert "reasoning" in data
    assert len(data["scores"]) == 2


def test_fastapi_validation_error_mismatched_currency(client):
    payload = {
        "purchase_id": "REQ-FASTAPI-MISMATCH",
        "currency": "USD",
        "requirements": {},
        "quotes": [
            {
                "quote_id": "Q-USD",
                "supplier_id": "SUP-USD",
                "amount": 100.0,
                "currency": "USD",
                "supplier_attributes": {"delivery_days": 2},
            },
            {
                "quote_id": "Q-EUR",
                "supplier_id": "SUP-EUR",
                "amount": 100.0,
                "currency": "EUR",  # Mismatch
                "supplier_attributes": {"delivery_days": 2},
            },
        ],
    }

    response = client.post("/api/v1/procurement/recommendations", json=payload)
    assert response.status_code == 422 or response.status_code == 400

