"""Object-Level Authorization and Tenant Isolation Boundary Guards."""

import uuid
from typing import Any, Optional
from security_hardening.core.errors import SecurityHardeningError


class ObjectAuthorizationError(SecurityHardeningError):
    def __init__(self, resource_type: str, resource_id: Any):
        super().__init__(
            message=f"Access to {resource_type} '{resource_id}' is denied or does not exist.",
            code="RESOURCE_ACCESS_DENIED",
            details={"resource_type": resource_type, "resource_id": str(resource_id)},
            status_code=403,
        )


def verify_resource_ownership(
    resource: Any,
    expected_organization_id: uuid.UUID,
    resource_type: str = "Resource",
) -> None:
    """Verify that a database model instance strictly belongs to the caller's organization.

    Raises:
        ObjectAuthorizationError if resource organization_id does not match.
    """
    if resource is None:
        return

    resource_org_id = getattr(resource, "organization_id", None)
    if resource_org_id is None:
        return

    # Normalize to UUID
    if isinstance(resource_org_id, str):
        try:
            resource_org_id = uuid.UUID(resource_org_id)
        except ValueError:
            pass

    if resource_org_id != expected_organization_id:
        raise ObjectAuthorizationError(
            resource_type=resource_type,
            resource_id=getattr(resource, "id", "unknown"),
        )

