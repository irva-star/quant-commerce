"""Versioned factors with explicit boundaries. Unknown inputs remain unknown."""
import json
from decimal import Decimal, ROUND_UP
from .config import ROOT, setting
from .models import Product

AL_SOURCE = 'https://international-aluminium.org/landing/aluminium-carbon-footprint-faqs/'
TRANSPORT_SOURCE = 'https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025'

def money(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_UP))

def estimate(p: Product, offset: bool, monthly_used: float, monthly_cap: float):
    missing=[]
    material=None
    if not p.mass_kg or not p.materials or abs(sum(m.fraction for m in p.materials)-1) > .001:
        missing.append('Complete material fractions and product mass')
    elif any(m.name != 'primary_aluminium' for m in p.materials):
        missing.append('Documented cradle-to-gate factor for each material')
    else:
        material = p.mass_kg * 14.8
    manufacturing=None
    if p.manufacturing_kwh is None or p.manufacturing_factor is None:
        missing.append('Product fabrication electricity and location-specific electricity factor')
    else:
        manufacturing=p.manufacturing_kwh*p.manufacturing_factor
    factor_file=ROOT/'backend'/'data'/'transport-factors.json'
    factors=json.loads(factor_file.read_text()) if factor_file.exists() else {}
    shipping=None
    transport_factor=factors.get(p.mode or '')
    if not all([p.origin,p.destination,p.mode,p.shipment_kg,p.distance_km]) or not transport_factor:
        missing.append('Origin, destination, mode, shipment mass, route distance and documented transport factor')
    else:
        shipping=p.shipment_kg/1000*p.distance_km*transport_factor['value']
    gross=None if any(v is None for v in (material,manufacturing,shipping)) else material+manufacturing+shipping
    price=Decimal(setting('OFFSET_PRICE_PER_TONNE','100'))
    if not price.is_finite() or price < 0:
        raise ValueError('OFFSET_PRICE_PER_TONNE must be finite and nonnegative')
    return dict(material_kg=material,manufacturing_kg=manufacturing,embodied_kg=None if material is None or manufacturing is None else material+manufacturing,
                shipping_kg=shipping,gross_kg=gross,monthly_used=monthly_used,
                monthly_remaining=monthly_cap-monthly_used,monthly_projected=None if gross is None else monthly_used+gross,
                offset_amount=money(Decimal(str(gross))/1000*price) if offset and gross is not None else 0,
                offset_requested_kg=gross if offset else 0,credited_kg=0,offset_partner=setting('OFFSET_PARTNER','Demo carbon partner (uncontracted)'),
                offset_price_per_tonne=float(price),offset_mode='SIMULATED',missing=missing,
                factors=[dict(name='Primary aluminium, 2023 global average',value=14.8,unit='kg CO2e/kg',source=AL_SOURCE,
                              boundary='Mine to cast-house gate; excludes product fabrication. Global proxy, not supplier-specific.'),
                         dict(name='Product fabrication electricity',value=p.manufacturing_factor,unit='kg CO2e/kWh',source=p.url,
                              boundary='Synthetic scenario electricity factor and kWh, explicitly supplied by demo fixture; not measured production.'),
                         dict(name='Freight: '+str(p.mode),value=transport_factor['value'] if transport_factor else None,
                              unit='kg CO2e/tonne-km',source=TRANSPORT_SOURCE,
                              boundary=transport_factor.get('description','Missing factor') if transport_factor else 'Missing factor')],
                methodology='qct-carbon-v1: material = sum(mass × fraction × cradle-to-gate factor); fabrication = kWh × grid factor; shipping = shipment kg / 1000 × km × freight factor; offset quote = gross / 1000 × USD per tonne, rounded up to cents.',
                uncertainty='Screening estimate; illustrative sensitivity ±40% (not a statistical confidence interval). Synthetic route, fabrication energy and composition. Excludes packaging production, retail, use and end-of-life. Strict caps use gross point estimates; offsets never reduce gross.')
