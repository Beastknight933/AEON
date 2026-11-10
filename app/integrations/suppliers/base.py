import abc
from typing import Any, Dict
from app.integrations.suppliers.schemas import NormalizedQuote


class BaseSupplierAdapter(abc.ABC):
    @property
    @abc.abstractmethod
    def code(self) -> str:
        """Unique supplier system code (e.g. mock_supplier_a)"""
        pass

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable supplier name"""
        pass

    @abc.abstractmethod
    async def fetch_quote(
        self,
        item_description: str,
        category: str,
        requirements: Dict[str, Any],
        currency: str = "USD",
    ) -> NormalizedQuote:
        """Fetch and return a normalized quote for requested item specifications."""
        pass
