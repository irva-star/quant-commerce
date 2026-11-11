"""Explicitly synthetic products and merchant offers; never presented as API results."""
from .models import Product, Material, Offer

SCENARIOS = {
    'clean': dict(name='Arc / Precision Desk Stand', sku='ARC-AL-01', advertised='68.00', reference='79.00',
                  final='76.00', fees='0.00', shipping_cost='4.00', tax='4.00', mass_kg=.32,
                  shipment_kg=.50, distance_km=480, mode='road', recurring=False,
                  claims=['Solid aluminium construction', 'One-time purchase. No recurring charges.']),
    'anchor': dict(name='Arc / Precision Desk Stand', sku='ARC-AL-01', advertised='59.00', reference='199.00',
                   final='93.00', fees='19.00', shipping_cost='10.00', tax='5.00', mass_kg=.32,
                   shipment_kg=.50, distance_km=480, mode='road', recurring=True, recurring_amount='9.99',
                   claims=['Save 70% against our reference price', 'No extra checkout fees', 'One-time purchase. No recurring charges.']),
    'carbon': dict(name='Atlas / Aluminium Monitor Arm', sku='ATLAS-AL-02', advertised='79.00', reference='85.00',
                   final='89.00', fees='0.00', shipping_cost='5.00', tax='5.00', mass_kg=2.4,
                   shipment_kg=3.0, distance_km=11000, mode='air', recurring=False,
                   claims=['Primary aluminium construction', 'Carbon-neutral delivery']),
}

def seed_product(scenario: str, base: str, offer: str | None = None) -> Product:
    values = SCENARIOS[scenario].copy()
    merchant = 'Arc Supply / Demo Merchant'
    if offer in ('north', 'form', 'studio'):
        values.update(advertised={'north':'54.00','form':'62.00','studio':'72.00'}[offer],
                      reference=None, final={'north':'62.00','form':'70.00','studio':'80.00'}[offer],
                      fees='0.00', shipping_cost='4.00', tax='4.00', recurring=False,
                      recurring_amount=None, claims=['Solid aluminium construction', 'One-time purchase. No recurring charges.'])
        merchant = {'north':'Northline / Synthetic Offer', 'form':'Form Market / Synthetic Offer','studio':'Studio Goods / Synthetic Offer'}[offer]
        if offer=='studio': values.update(name='Elevate / Functional Desk Stand',sku='ELEVATE-01')
    return Product(**values, merchant=merchant, url=f'{base}/store/{scenario}' + (f'?offer={offer}' if offer else ''),
                   materials=[Material(name='primary_aluminium', fraction=1)], origin='Pennsylvania, US' if scenario != 'carbon' else 'Shanghai, CN',
                   destination='New York, US', manufacturing_kwh=.12 if scenario != 'carbon' else .8,
                   manufacturing_factor=.4, controlled=True, synthetic=True)

def seed_offers(scenario: str, base: str) -> list[Offer]:
    p = seed_product(scenario, base)
    return [Offer(id=key, name=p.name if key != 'studio' else 'Elevate / Functional Desk Stand', merchant=merchant,
                  url=f'{base}/store/{scenario}?offer={key}', price=price,
                  match='identical' if key != 'studio' else 'equivalent',
                  match_reason='Same synthetic SKU and configuration' if key != 'studio' else 'Similar function; different design and SKU',
                  synthetic=True, specifications={'material':'primary aluminium', 'sku': p.sku if key != 'studio' else 'ELEVATE-01'}, total_known=False)
            for key, merchant, price in [('north','Northline','54.00'),('form','Form Market','62.00'),('studio','Studio Goods','72.00')]]
