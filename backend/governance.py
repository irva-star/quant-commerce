from decimal import Decimal
from statistics import median
from .models import Mandate, Product, Offer, Finding

def market_matrix(p: Product, offers: list[Offer]):
    identical=[o for o in offers if o.match=='identical' and o.currency==p.currency]
    prices=[float(o.price) for o in identical]
    med=median(prices) if prices else None
    deviation=(float(p.reference)/med-1)*100 if p.reference and med else None
    alternatives=sorted([o for o in offers if o.match in ('identical','equivalent') and o.currency==p.currency and p.advertised is not None and o.price<p.advertised],key=lambda o:o.price)[:3]
    return dict(original_price=float(p.advertised) if p.advertised is not None else None,currency=p.currency,
                price_difference_pct=(float(p.advertised)/med-1)*100 if p.advertised is not None and med else None,
                median=med,spread=max(prices)-min(prices) if prices else None,reference_deviation_pct=deviation,
                suspicious_anchor=bool(deviation is not None and deviation>50),sample_size=len(prices),
                alternatives=[o.model_dump(mode='json') for o in alternatives],
                basis='Identical-product, same-currency advertised item prices only; tax, shipping and condition/configuration must be checked before switching. Functional equivalents excluded from median. No historical pricing proof.')

def validate(m: Mandate,p: Product,carbon: dict,market: dict,epistemic: dict,persona: dict,monthly_used: float):
    findings=[]
    def add(code,severity,message): findings.append(Finding(code=code,severity=severity,message=message).model_dump())
    critical=[key for key in ['advertised','final','fees','shipping_cost','tax','recurring'] if getattr(p,key) is None]
    if critical: add('MISSING_EVIDENCE','BLOCK','Missing critical checkout evidence: '+', '.join(critical))
    if carbon['missing']: add('MISSING_CARBON','BLOCK','Missing carbon inputs: '+'; '.join(carbon['missing']))
    if p.currency!='USD': add('CURRENCY','BLOCK','This MVP mandate and settlement support USD only. No FX conversion assumed.')
    total=None if p.final is None else p.final+Decimal(str(carbon['offset_amount']))
    if total is not None and total>m.max_spend: add('FIAT_CAP','BLOCK',f'Total including optional carbon leg ${total:.2f} exceeds ${m.max_spend:.2f}.')
    if p.fees is not None and p.fees>m.max_fees: add('FEES','BLOCK',f'Checkout fees ${p.fees:.2f} exceed authorized ${m.max_fees:.2f}.')
    if m.no_subscription and p.recurring: add('SUBSCRIPTION','BLOCK','Recurring charge detected; mandate requires a one-time purchase.')
    if all(x is not None for x in (p.final,p.advertised,p.fees,p.shipping_cost,p.tax)):
        if p.final != p.advertised+p.fees+p.shipping_cost+p.tax: add('TOTAL_MISMATCH','BLOCK','Checkout components do not reconcile with final payable amount.')
    if m.cart:
        if len(m.cart)!=1 or m.cart[0].quantity!=1 or p.advertised is None or m.cart[0].unit_price!=p.advertised:
            add('CART_UNRESOLVED','BLOCK','Cart must reconcile to the audited single-item, quantity-one checkout. Multi-item checkout evidence is not available in this MVP.')
    if p.destination and p.destination.casefold()!=m.destination.casefold(): add('DESTINATION','BLOCK','Shipping evidence destination differs from buyer destination. Route must be remeasured.')
    gross=carbon['gross_kg']
    if gross is not None:
        for code,actual,cap,label in [('PURCHASE_CARBON',gross,m.purchase_carbon_cap,'Purchase gross carbon'),('MONTHLY_CARBON',monthly_used+gross,m.monthly_carbon_cap,'Projected monthly carbon')]:
            if actual>cap:
                if m.override_policy=='reviewable_carbon' and m.override_acknowledged:
                    add(code+'_OVERRIDDEN','INFO',f'{label} {actual:.3f} kg exceeds {cap:.3f} kg; explicit buyer exception recorded: {m.override_reason}')
                else:
                    add(code,'BLOCK' if m.override_policy=='strict' else 'REVIEW',f'{label} {actual:.3f} kg exceeds {cap:.3f} kg. Offsets do not change this test.')
    if m.detect_anchor and market['suspicious_anchor']: add('ANCHOR','REVIEW','Reference price is over 50% above the observed identical-product median. Needs historical evidence; price differences alone do not prove deception.')
    if persona.get('delta') not in (None,0): add('PERSONA_DELTA','REVIEW',f"Observed personalized price difference ${persona['delta']:.2f}; controlled cookie experiment, not proof of discrimination.")
    if any(c['verdict']=='contradicted' for c in epistemic['claims']): add('CLAIM_CONTRADICTION','REVIEW','Marketing claims conflict with captured evidence; inspect source references.')
    if p.synthetic: add('SYNTHETIC','INFO','Controlled demo merchant and evidence are synthetic. Sandbox settlement only.')
    decision='BLOCK' if any(f['severity']=='BLOCK' for f in findings) else 'REVIEW' if any(f['severity']=='REVIEW' for f in findings) else 'PASS'
    return decision,findings
