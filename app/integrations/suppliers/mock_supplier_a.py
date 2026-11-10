import decimal
from typing import Any, Dict
from app.integrations.suppliers.base import BaseSupplierAdapter
from app.integrations.suppliers.schemas import NormalizedQuote


class MockSupplierA(BaseSupplierAdapter):
    @property
    def code(self) -> str:
        return "mock_supplier_a"

    @property
    def name(self) -> str:
        return "MockCloudStore"

    async def fetch_quote(
        self,
        item_description: str,
        category: str,
        requirements: Dict[str, Any],
        currency: str = "USD",
    ) -> NormalizedQuote:
        quantity = int(requirements.get("quantity", 1))
        # Base pricing heuristic based on category/specs
        if "compute" in category.lower() or "server" in item_description.lower():
            unit_price = decimal.Decimal("120.00")
            item_id = "mcs-compute-v2"
        elif "storage" in category.lower() or "disk" in item_description.lower():
            unit_price = decimal.Decimal("45.00")
            item_id = "mcs-storage-nvme"
        else:
            unit_price = decimal.Decimal("80.00")
            item_id = "mcs-standard-sku"

        total = unit_price * quantity
        return NormalizedQuote(
            supplier_code=self.code,
            supplier_name=self.name,
            item_id=item_id,
            unit_price=unit_price,
            quantity=quantity,
            total_amount=total,
            currency=currency,
            estimated_delivery_days=0,  # instant cloud provisioning
            reliability_score=decimal.Decimal("0.98"),
            raw_data={
                "provider": "MockCloudStore",
                "tier": "enterprise",
                "sla_uptime": "99.99%",
                "region": requirements.get("region", "us-east-1"),
            },
        )
