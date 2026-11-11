import json
from backend.page_data import normalize_observations,price
from backend.extractor import parse_fields,evidence_from_fields
from backend.seeds import seed_product,seed_offers
from backend.governance import market_matrix,validate
from backend.carbon import estimate
from backend.models import Mandate

BASE='http://127.0.0.1:8000'

def test_slashed_price_alone_populates_reference_and_anchor_evidence():
    p=seed_product('anchor',BASE)
    data=p.model_dump(mode='json')
    data.pop('reference')
    data['materials']='primary_aluminium:1'
    data['recurring']='true'
    raw={'qct':data,'slashed':{'value':'$199.00','selector':'[data-qct="slashed-reference"]'},'claims':p.claims}
    fields,sources,_=normalize_observations(raw,p.url)
    extracted=parse_fields(fields,p.url)
    assert extracted.reference==199
    evidence=evidence_from_fields(fields,p.url,True,'snapshot',sources)
    assert next(e for e in evidence if e['field']=='reference')['selector']=='[data-qct="slashed-reference"]'
    market=market_matrix(extracted,seed_offers('anchor',BASE))
    decision,findings=validate(Mandate(product_url=p.url),extracted,estimate(extracted,False,0,50),market,{'claims':[]},{'delta':12},0)
    assert market['suspicious_anchor'] and market['reference_deviation_pct']>200
    assert any(f['code']=='ANCHOR' and f['severity']=='REVIEW' for f in findings)

def test_standard_product_jsonld_extracts_price_mass_and_raw_material_not_checkout():
    product={'@type':'Product','name':'External stand','sku':'EX-1','material':'Aluminium',
        'weight':{'@type':'QuantitativeValue','value':320,'unitCode':'GRM'},'countryOfOrigin':{'name':'US'},
        'offers':{'@type':'Offer','price':'54.00','priceCurrency':'USD','seller':{'name':'Actual Merchant'}}}
    raw={'jsonld':[json.dumps({'@graph':[product]})]}
    fields,sources,notes=normalize_observations(raw,'https://example.com/stand')
    p=parse_fields(fields,'https://example.com/stand')
    assert p.advertised==54 and p.mass_kg==.32 and p.merchant=='Actual Merchant'
    assert p.final is None and p.fees is None and p.recurring is None
    assert p.materials==[] and fields['material_text']=='Aluminium'
    assert 'Product.offers.price' in sources['advertised']
    assert not notes

def test_supported_selectors_preserve_provenance_and_missing_terms():
    fields,sources,_=normalize_observations({'selected':{'name':{'value':'Stand','selector':'h1'},'advertised':{'value':'$1,249.99','selector':'[itemprop="price"]'},'reference':{'value':'$1,999.00','selector':'.compare-at-price'}}},'https://example.com')
    assert fields['advertised']=='1249.99' and fields['reference']=='1999.00'
    assert sources['name']=='h1' and 'recurring' not in fields and fields['currency']=='UNKNOWN'

def test_unsupported_page_has_clear_limitation():
    fields,_,notes=normalize_observations({},'https://example.com')
    assert any('Extraction unavailable' in n for n in notes)
    assert 'final' not in fields

def test_ambiguous_price_or_multiple_products_never_guessed():
    assert price('€1.299,00') is None and price('$50–$80') is None
    fields,_,notes=normalize_observations({'jsonld':[json.dumps([{'@type':'Product','name':'A'},{'@type':'Product','name':'B'}])]},'https://example.com')
    assert fields['name']=='example.com'
    assert any('Multiple' in n for n in notes)
