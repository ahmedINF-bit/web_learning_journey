from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class BillingCheckoutRequest(BaseModel):
    plan: Literal["pro", "enterprise"]


class BillingOrderResponse(BaseModel):
    id: int
    plan: str
    amount_dzd: int
    currency: str
    order_reference: str
    status: str
    checkout_url: str | None = None
    created_at: datetime
    paid_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
