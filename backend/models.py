from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Money = Decimal
NonNegative = Field(ge=0, allow_inf_nan=False)

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class CartItem(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=100)
    unit_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

class Mandate(StrictModel):
    product_url: HttpUrl
    scenario: Literal['clean', 'anchor', 'carbon'] = 'clean'
    market_mode: Literal['synthetic','live'] = 'synthetic'
    market_query: str = Field(default='',max_length=500)
    cart: list[CartItem] = Field(default_factory=list, max_length=20)
    max_spend: Decimal = Field(default=Decimal('100'), ge=0, max_digits=10, decimal_places=2)
    purchase_carbon_cap: float = Field(default=8, ge=0)
    monthly_carbon_cap: float = Field(default=50, ge=0)
    max_fees: Decimal = Field(default=Decimal('5'), ge=0, max_digits=10, decimal_places=2)
    no_subscription: bool = True
    detect_anchor: bool = True
    offset_opt_in: bool = False
    override_policy: Literal['strict', 'reviewable_carbon'] = 'strict'
    override_acknowledged: bool = False
    override_reason: str = Field(default='', max_length=500)
    destination: str = Field(default='New York, US', min_length=2, max_length=150)
    @model_validator(mode='after')
    def explicit_override(self):
        if self.override_acknowledged and (self.override_policy != 'reviewable_carbon' or len(self.override_reason.strip()) < 10):
            raise ValueError('Carbon override requires reviewable policy and a reason of at least 10 characters')
        return self

class Material(StrictModel):
    name: str
    fraction: float = Field(gt=0, le=1)

class Product(StrictModel):
    name: str
    sku: str | None = None
    merchant: str
    url: str
    advertised: Decimal | None = Field(default=None, ge=0)
    reference: Decimal | None = Field(default=None, ge=0)
    final: Decimal | None = Field(default=None, ge=0)
    fees: Decimal | None = Field(default=None, ge=0)
    shipping_cost: Decimal | None = Field(default=None, ge=0)
    tax: Decimal | None = Field(default=None, ge=0)
    currency: str = 'USD'
    mass_kg: float | None = Field(default=None, gt=0)
    shipment_kg: float | None = Field(default=None, gt=0)
    materials: list[Material] = Field(default_factory=list)
    origin: str | None = None
    destination: str | None = None
    mode: Literal['road', 'air', 'sea'] | None = None
    distance_km: float | None = Field(default=None, gt=0)
    manufacturing_kwh: float | None = Field(default=None, ge=0)
    manufacturing_factor: float | None = Field(default=None, ge=0)
    recurring: bool | None = None
    recurring_amount: Decimal | None = Field(default=None, ge=0)
    claims: list[str] = Field(default_factory=list)
    controlled: bool = False
    synthetic: bool = False

class Evidence(StrictModel):
    id: str
    field: str
    value: str
    url: str
    selector: str
    captured_at: str
    synthetic: bool
    sha256: str

class Offer(StrictModel):
    id: str
    name: str
    merchant: str
    url: HttpUrl
    price: Decimal = Field(ge=0)
    currency: str = 'USD'
    match: Literal['identical', 'equivalent', 'unverified']
    match_reason: str
    synthetic: bool
    specifications: dict = Field(default_factory=dict)
    total_known: bool = False

class ClaimAssessment(StrictModel):
    claim: str
    verdict: Literal['supported', 'contradicted', 'unverified']
    explanation: str
    source_ids: list[str]

class ClaimResult(StrictModel):
    claims: list[ClaimAssessment]
    uncertainty: str

class Finding(StrictModel):
    code: str
    severity: Literal['BLOCK', 'REVIEW', 'INFO']
    message: str

class Approval(StrictModel):
    audit_id: str
    buyer_approved: bool
    approved_total: Decimal = Field(ge=0, max_digits=10, decimal_places=2)

class Capture(Approval):
    order_id: str = Field(pattern=r'^[A-Z0-9]{5,40}$')

class ProductSearch(StrictModel):
    query: str = Field(min_length=2,max_length=500)
    limit: int = Field(default=12,ge=1,le=50)
    reference_url: HttpUrl | None = None

class ProductLookup(StrictModel):
    url: HttpUrl

class ProductDiscovery(ProductLookup):
    query: str = Field(default='',max_length=500)
    limit: int = Field(default=12,ge=1,le=50)
