"""Replaceable carbon partner payment leg. No contracted/eligible partner is configured."""
from typing import Protocol

class CarbonPartner(Protocol):
    async def settle(self,audit_id: str,carbon: dict) -> dict: ...

class SimulatedCarbonPartner:
    async def settle(self,audit_id: str,carbon: dict):
        return dict(mode='SIMULATED',status='PROPOSED' if carbon['offset_amount'] else 'NOT_REQUESTED',
                    partner=carbon['offset_partner'],amount=carbon['offset_amount'],currency='USD',
                    requested_kg=carbon['offset_requested_kg'],credited_kg=0,
                    explanation='Separate proposed leg. No transfer, retirement, verified credits or atomic split. Payouts/Multiparty require confirmed permissions and an eligible contracted partner.')

carbon_partner: CarbonPartner = SimulatedCarbonPartner()
