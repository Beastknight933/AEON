"""AEON FastAPI Backend Integration Adapter Example.

This example illustrates how the backend engineering team integrates the
in-process AEON ML recommendation module into their FastAPI application.

Key architectural boundaries:
1. Backend retrieves quotes from procurement database.
2. Backend passes validated in-memory payload to recommend().
3. ML module executes purely in-process (no DB, no payment decisions).
4. Backend receives RecommendationResponse, checks against business rules,
   and persists recommendations to database.

To test this endpoint locally:
    python examples/fastapi_adapter.py
    (Or launch with: uvicorn examples.fastapi_adapter:app --reload)
"""

import sys
from pathlib import Path
from typing import Any, Dict

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from aeon_ml import (
    AEONMLError,
    CurrencyMismatchError,
    DuplicateQuoteIdError,
    EmptyQuotesError,
    RecommendationRequest,
    RecommendationResponse,
    recommend,
)

app = FastAPI(
    title="AEON Procurement Engine API",
    version="1.0.0",
    description="Backend procurement service integrating the AEON ML recommendation module.",
)


@app.exception_handler(AEONMLError)
async def aeon_ml_error_handler(request, exc: AEONMLError):
    """Custom exception handler for domain errors from AEON ML module."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": exc.__class__.__name__, "message": exc.message, "details": exc.details},
    )


@app.post(
    "/api/v1/procurement/recommendations",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare supplier quotes and recommend optimal quote",
    tags=["Recommendations"],
)
async def get_procurement_recommendation(request: RecommendationRequest) -> RecommendationResponse:
    """FastAPI endpoint delegating directly to the in-process ML recommendation module.

    - Pure in-process execution.
    - Zero external DB calls in the ML layer.
    - Strict input and output schema validation.
    """
    try:
        # Backend team: validate request against stored purchase requisitions if needed
        # e.g., db.verify_purchase_exists(request.purchase_id)

        # In-process call to the ML model
        response: RecommendationResponse = recommend(request)

        # Backend team: store the recommendation and audit trail
        # e.g., db.save_recommendation(response)

        return response

    except EmptyQuotesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "EmptyQuotesError", "message": exc.message},
        ) from exc
    except CurrencyMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CurrencyMismatchError", "message": exc.message, "details": exc.details},
        ) from exc
    except DuplicateQuoteIdError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "DuplicateQuoteIdError", "message": exc.message, "details": exc.details},
        ) from exc
    except AEONMLError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "AEONMLError", "message": exc.message, "details": exc.details},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "UnexpectedError", "message": str(exc)},
        ) from exc


@app.get("/health", tags=["Monitoring"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint confirming ML module readiness."""
    return {
        "status": "healthy",
        "service": "aeon-procurement-backend",
        "ml_module": "aeon_ml",
        "ml_version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    print("Starting AEON FastAPI adapter on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)
