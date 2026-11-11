"""Conservative standard-page extraction. Never equate an item Offer price with a checkout total."""
import json
import re
from decimal import Decimal,InvalidOperation
from urllib.parse import urlparse

SCRIPT=r'''() => {
  const read = selectors => {
    for (const selector of selectors) {
      const el=document.querySelector(selector);
      if(el) { const value=(el.getAttribute('content') || el.getAttribute('data-value') || el.textContent || '').trim().slice(0,2000);
        if(value) return {value,selector}; }
    } return null;
  };
  return {
    qct:Object.fromEntries([...document.querySelectorAll('[data-qct]')].filter(e=>!['claim','slashed-reference'].includes(e.dataset.qct)).slice(0,50).map(e=>[e.dataset.qct,e.textContent.trim().slice(0,2000)])),
    slashed:read(['[data-qct="slashed-reference"]']),
    claims:[...document.querySelectorAll('[data-qct="claim"], [data-claim], [itemprop="description"], .product-description')].slice(0,15).map(e=>e.textContent.trim().slice(0,1500)),
    jsonld:[...document.querySelectorAll('script[type="application/ld+json"]')].slice(0,20).map(e=>e.textContent.slice(0,200000)),
    selected:{
      name:read(['[itemprop="name"]','h1']),
      advertised:read(['meta[property="product:price:amount"]','[itemprop="price"]','[data-product-price]','.product__price']),
      currency:read(['meta[property="product:price:currency"]','[itemprop="priceCurrency"]']),
      reference:read(['[data-compare-at-price]','.compare-at-price','.price--compare','del.price']),
      final:read(['[data-checkout-total]','[data-order-total]']),
      fees:read(['[data-checkout-fees]']), shipping_cost:read(['[data-shipping-cost]']), tax:read(['[data-checkout-tax]']),
      material_text:read(['[itemprop="material"]','[data-material-composition]']),
      weight_text:read(['[itemprop="weight"]','[data-product-weight]']),
      origin:read(['[itemprop="countryOfOrigin"]','[data-country-of-origin]']),
      mode:read(['[data-shipping-method]']),recurring:read(['[data-recurring]']),recurring_amount:read(['[data-recurring-amount]'])
    }
  };
}'''

def price(value):
    if value is None or isinstance(value,bool): return None
    # Ambiguous decimal-comma and ranges are left unresolved, never silently guessed.
    text=str(value).strip()
    if not re.fullmatch(r'(?:USD\s*|\$\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?(?:\s*USD)?',text): return None
    try: return str(Decimal(re.sub(r'USD|\$|,|\s','',text)))
    except InvalidOperation: return None

def _nodes(value):
    if isinstance(value,list):
        for item in value: yield from _nodes(item)
    elif isinstance(value,dict):
        yield value
        yield from _nodes(value.get('@graph',[]))

def normalize_observations(raw,url):
    fields=dict(raw.get('qct') or {})
    sources={k:f'[data-qct="{k}"]' for k in fields}
    notes=[]
    if raw.get('slashed'):
        reference=price(raw['slashed']['value'])
        if reference is not None:
            fields['reference']=reference
            sources['reference']=raw['slashed']['selector']
    products=[]
    for index,text in enumerate(raw.get('jsonld') or []):
        try:
            for node in _nodes(json.loads(text)):
                kind=node.get('@type',[])
                if kind=='Product' or isinstance(kind,list) and 'Product' in kind:
                    products.append((node,f'script[type="application/ld+json"] index={index}'))
        except (ValueError,TypeError): notes.append('Invalid JSON-LD ignored.')
    if len(products)==1:
        product,source=products[0]
        def put(key,value,path):
            if key not in fields and value is not None:
                fields[key]=value
                sources[key]=source+' :: '+path
        put('name',product.get('name'),'Product.name')
        put('sku',product.get('sku'),'Product.sku')
        origin=product.get('countryOfOrigin')
        put('origin',origin.get('name') if isinstance(origin,dict) else origin,'Product.countryOfOrigin')
        put('material_text',product.get('material'),'Product.material')
        weight=product.get('weight')
        if isinstance(weight,dict) and weight.get('unitCode') in ('KGM','GRM'):
            try: put('mass_kg',float(weight['value'])/(1000 if weight['unitCode']=='GRM' else 1),'Product.weight')
            except (KeyError,ValueError,TypeError): notes.append('Unsupported product weight.')
        offers=product.get('offers')
        if isinstance(offers,list): offers=offers[0] if len(offers)==1 else None
        if isinstance(offers,dict) and offers.get('@type')!='AggregateOffer':
            put('advertised',price(offers.get('price')),'Product.offers.price')
            put('currency',offers.get('priceCurrency'),'Product.offers.priceCurrency')
            seller=offers.get('seller')
            if isinstance(seller,dict): put('merchant',seller.get('name'),'Product.offers.seller.name')
        if product.get('description') and not raw.get('claims'):
            raw={**raw,'claims':[str(product['description'])[:1500]]}
    elif len(products)>1:
        notes.append('Multiple JSON-LD products: no arbitrary product or offer selected.')
    for key,observation in (raw.get('selected') or {}).items():
        if observation and key not in fields:
            value=observation['value']
            if key in ('advertised','reference','final','fees','shipping_cost','tax','recurring_amount'): value=price(value)
            if value is not None: fields[key]=value; sources[key]=observation['selector']
    if 'reference' in fields: fields['reference']=price(fields['reference'])
    if fields.get('recurring') not in (True,False,'true','false'):
        fields.pop('recurring',None) # Unknown terms are not evidence of no subscription.
    if 'mode' in fields:
        mode=str(fields['mode']).lower()
        if mode not in ('air','road','sea'): fields.pop('mode')
    fields['claims']=raw.get('claims') or []
    sources['claims']='[data-qct="claim"], [data-claim], [itemprop="description"], .product-description / Product.description'
    if 'name' not in fields: fields['name']=urlparse(url).hostname or 'Unsupported listing'; sources['name']='URL hostname (fallback label)'
    if 'merchant' not in fields: fields['merchant']=urlparse(url).hostname or 'Unknown merchant'; sources['merchant']='URL hostname (fallback label)'
    if 'currency' not in fields: fields['currency']='UNKNOWN'; sources['currency']='Unknown; no currency assumption'
    supported=bool(products or raw.get('qct') or (raw.get('selected') or {}).get('advertised'))
    return fields,sources,notes+([] if supported else ['Extraction unavailable: no supported Product JSON-LD or explicit price selectors found.'])
