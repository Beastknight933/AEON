import asyncio
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.integrations.suppliers.base import BaseSupplierAdapter
from app.integrations.suppliers.mock_supplier_a import MockSupplierA
from app.integrations.suppliers.mock_supplier_b import MockSupplierB
from app.integrations.suppliers.schemas import NormalizedQuote
from app.models.supplier import Supplier


class SupplierRegistry:
    def __init__(self):
        self._adapters: Dict[str, BaseSupplierAdapter] = {}
        # Register default mock suppliers
        self.register(MockSupplierA())
        self.register(MockSupplierB())

    def register(self, adapter: BaseSupplierAdapter) -> None:
        self._adapters[adapter.code.lower()] = adapter

    def get(self, code: str) -> Optional[BaseSupplierAdapter]:
        return self._adapters.get(code.lower())

    def list_adapters(self) -> List[BaseSupplierAdapter]:
        return list(self._adapters.values())

    async def ensure_suppliers_in_db(self, session: AsyncSession) -> Dict[str, Supplier]:
        """
        Ensure all registered supplier adapters have corresponding records in the suppliers DB table.
        Returns a mapping of supplier_code -> Supplier model.
        """
        supplier_models: Dict[str, Supplier] = {}
        for adapter in self._adapters.values():
            stmt = select(Supplier).where(Supplier.code == adapter.code)
            record = await session.scalar(stmt)
            if not record:
                record = Supplier(
                    code=adapter.code,
                    name=adapter.name,
                    is_active=True,
                )
                session.add(record)
                await session.flush()
            supplier_models[adapter.code] = record
        return supplier_models

    async def collect_quotes(
        self,
        item_description: str,
        category: str,
        requirements: dict,
        currency: str = "USD",
    ) -> List[NormalizedQuote]:
        """
        Collect normalized quotes from all registered suppliers concurrently.
        """
        tasks = [
            adapter.fetch_quote(
                item_description=item_description,
                category=category,
                requirements=requirements,
                currency=currency,
            )
            for adapter in self._adapters.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_quotes: List[NormalizedQuote] = []
        for r in results:
            if isinstance(r, NormalizedQuote):
                valid_quotes.append(r)
        return valid_quotes


# Global registry singleton
supplier_registry = SupplierRegistry()
