import decimal
from typing import Any, Dict
from app.integrations.suppliers.base import BaseSupplierAdapter
from app.integrations.suppliers.schemas import NormalizedQuote


class MockSupplierB(BaseSupplierAdapter):
    @property
    def code(self) -> str:
        return "mock_supplier_b"

    @property
    def name(self) -> str:
        return "MockHardwareSupply"

    async def fetch_quote(
        self,
        item_description: str,
        category: str,
        requirements: Dict[str, Any],
        currency: str = "USD",
    ) -> NormalizedQuote:
        quantity = int(requirements.get("quantity", 1))
        # Slightly different pricing structure
        if "compute" in category.lower() or "server" in item_description.lower():
            unit_price = decimal.Decimal("135.00")
            item_id = "mhs-baremetal-node"
        elif "storage" in category.lower() or "disk" in item_description.lower():
            unit_price = decimal.Decimal("40.00")
            item_id = "mhs-storage-hdd-array"
        else:
            unit_price = decimal.Decimal("95.00")
            item_id = "mhs-generic-hardware"

        total = unit_price * quantity
        return NormalizedQuote(
            supplier_code=self.code,
            supplier_name=self.name,
            item_id=item_id,
            unit_price=unit_price,
            quantity=quantity,
            total_amount=total,
            currency=currency,
            estimated_delivery_days=2,
            reliability_score=decimal.Decimal("0.94"),
            raw_data={
                "provider": "MockHardwareSupply",
                "warehouse": "central-hub-3",
                "warranty_months": 24,
            },
        )
