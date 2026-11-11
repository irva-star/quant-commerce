from decimal import Decimal
import pytest
from pydantic import ValidationError
from backend.models import Mandate, Material
from backend.seeds import seed_product,seed_offers
from backend.carbon import estimate
from backend.governance import validate,market_matrix

BASE='http://127.0.0.1:8000'

def run(scenario='clean',product_updates=None,used=0,**overrides):
    p=seed_product(scenario,BASE).model_copy(update=product_updates or {})
    m=Mandate(product_url=p.url,scenario=scenario,**overrides)
    carbon=estimate(p,m.offset_opt_in,used,m.monthly_carbon_cap)
    market=market_matrix(p,seed_offers(scenario,BASE))
    d,f=validate(m,p,carbon,market,{'claims':[]},{'delta':0},used)
    return d,{x['code'] for x in f},carbon

def test_clean_passes():
    decision,_,c=run()
    assert decision=='PASS'
    assert c['gross_kg']==pytest.approx(.32*14.8+.12*.4+.5/1000*480*.10163)

def test_anchor_and_drip_block():
    d,codes,_=run('anchor')
    assert d=='BLOCK'
    assert {'ANCHOR','FEES','SUBSCRIPTION'}<=codes

def test_offset_never_clears_strict_cap():
    d,codes,c=run('carbon',offset_opt_in=True)
    assert d=='BLOCK' and 'PURCHASE_CARBON' in codes and 'MONTHLY_CARBON' in codes
    assert c['offset_amount']>0 and c['credited_kg']==0

def test_reviewable_cap_needs_explicit_exception():
    assert run('carbon',override_policy='reviewable_carbon')[0]=='REVIEW'
    d,codes,_=run('carbon',override_policy='reviewable_carbon',override_acknowledged=True,override_reason='Buyer accepts the disclosed gross carbon exception.')
    assert d=='PASS' and 'PURCHASE_CARBON_OVERRIDDEN' in codes

def test_override_cannot_bypass_fiat_or_fees():
    assert run('anchor',override_policy='reviewable_carbon',override_acknowledged=True,override_reason='Buyer accepts carbon only.')[0]=='BLOCK'

@pytest.mark.parametrize('field',['final','fees','recurring','shipping_cost','tax'])
def test_missing_checkout_evidence_blocks(field):
    assert run(product_updates={field:None})[0]=='BLOCK'

@pytest.mark.parametrize('field',['mass_kg','shipment_kg','distance_km','mode','origin','manufacturing_kwh'])
def test_missing_carbon_inputs_blocks(field):
    d,codes,c=run(product_updates={field:None})
    assert d=='BLOCK' and c['gross_kg'] is None

def test_unknown_material_blocks_without_guess():
    assert run(product_updates={'materials':[Material(name='mystery',fraction=1)]})[0]=='BLOCK'

def test_incomplete_composition_blocks():
    assert run(product_updates={'materials':[Material(name='primary_aluminium',fraction=.5)]})[0]=='BLOCK'

def test_offset_amount_counts_toward_fiat_limit():
    assert run(offset_opt_in=True,max_spend=76)[0]=='BLOCK'
    assert run(max_spend=76)[0]=='PASS'

def test_equal_caps_pass():
    c=run()[2]
    assert run(purchase_carbon_cap=c['gross_kg'],monthly_carbon_cap=c['gross_kg'])[0]=='PASS'

def test_monthly_actual_usage_is_enforced():
    assert 'MONTHLY_CARBON' in run(used=49)[1]

def test_checkout_reconciles():
    assert 'TOTAL_MISMATCH' in run(product_updates={'final':Decimal('75')})[1]

def test_shipping_destination_mismatch_blocks():
    assert 'DESTINATION' in run(destination='Boston, US')[1]

def test_cart_requires_audited_quantity_and_price():
    assert 'CART_UNRESOLVED' in run(cart=[{'name':'Desk stand','quantity':2,'unit_price':68}])[1]

def test_functional_equivalents_do_not_inflate_identical_median():
    p=seed_product('clean',BASE)
    offers=seed_offers('clean',BASE)
    matrix=market_matrix(p,offers)
    assert matrix['median']==58 and matrix['spread']==8 and matrix['sample_size']==2

@pytest.mark.parametrize('data',[{'max_spend':-1},{'purchase_carbon_cap':float('nan')},{'monthly_carbon_cap':float('inf')},{'max_fees':-2},{'override_acknowledged':True},{'override_policy':'reviewable_carbon','override_acknowledged':True,'override_reason':'x'}])
def test_malformed_mandates_rejected(data):
    with pytest.raises(ValidationError): Mandate(product_url=BASE+'/store/clean',**data)
