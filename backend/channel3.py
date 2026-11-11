"""Official Channel3 v1 Search + Lookup; all authentication stays on the server.

Upstream fields: products[] / product, title, offers[], price.price (price.amount
in the official Offer guide example), price.currency, domain, url, materials,
key_features, category, condition, variants, dimensions, availability.
Application statuses and matching metadata below are our own, not upstream fields.
"""
import json
import re
from decimal import Decimal,InvalidOperation
import httpx
from pydantic import ValidationError
from .config import DATA,setting
from .extractor import controlled_url
from .models import Mandate,Offer
from .seeds import seed_offers,SCENARIOS

DOCS='https://channel3.ai/docs/guides/make-a-search'

class Channel3Error(Exception):
    def __init__(self,code,message,http_status=None,retry_after=None):
        super().__init__(message)
        self.code,self.message,self.http_status,self.retry_after=code,message,http_status,retry_after
    def public(self):
        return dict(error_code=self.code,detail=self.message,http_status=self.http_status,retry_after_seconds=self.retry_after)

class Channel3Client:
    async def post(self,path,body):
        key=setting('CHANNEL3_API_KEY')
        if not key: raise Channel3Error('NOT_CONFIGURED','CHANNEL3_API_KEY is not configured on the backend.',503)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=5),follow_redirects=False) as client:
                response=await client.post(setting('CHANNEL3_BASE_URL','https://api.trychannel3.com').rstrip('/')+path,
                    headers={'x-api-key':key,'Content-Type':'application/json','Accept':'application/json'},json=body)
        except httpx.TimeoutException:
            raise Channel3Error('TIMEOUT','Channel3 timed out. Retry the search; no live data is assumed.') from None
        except httpx.HTTPError:
            raise Channel3Error('NETWORK','Channel3 could not be reached. No live data is assumed.') from None
        status=response.status_code
        if status in (401,403): raise Channel3Error('AUTHENTICATION','Channel3 rejected the backend API key. Check CHANNEL3_API_KEY and account access.',status)
        if status==429:
            retry=response.headers.get('Retry-After','')
            raise Channel3Error('RATE_LIMIT','Channel3 rate limit reached. Retry after the indicated delay.',status,int(retry) if retry.isdigit() else None)
        if status==404: raise Channel3Error('PRODUCT_NOT_FOUND','No supported Channel3 product was found for this URL.',status)
        if not 200<=status<300: raise Channel3Error('UPSTREAM','Channel3 returned an upstream error. No live result is asserted.',status)
        try:
            data=response.json()
            if not isinstance(data,dict): raise ValueError()
        except ValueError: raise Channel3Error('INVALID_RESPONSE','Channel3 returned an invalid JSON object.',status) from None
        return data,status

    async def search(self,query,limit=12):
        data,status=await self.post('/v1/search',{'query':query,'limit':limit})
        if not isinstance(data.get('products'),list): raise Channel3Error('INVALID_RESPONSE','Channel3 Search response is missing products[].',status)
        return data,status

    async def lookup(self,url):
        data,status=await self.post('/v1/lookup',{'url':url})
        if not isinstance(data.get('product'),dict): raise Channel3Error('PRODUCT_NOT_FOUND','Channel3 Lookup did not return a product. No identity match is assumed.',status)
        return data,status

def normalize(search: dict,lookup: dict):
    reference=lookup.get('product') or {}
    canonical=reference.get('id')
    def norm(value): return re.sub(r'\s+',' ',str(value).strip().casefold())
    def as_list(value): return value if isinstance(value,list) else [value] if isinstance(value,str) else []
    def features(p):
        return {norm(f) for f in as_list(p.get('key_features')) if re.search(r'capacity|compatible|adjustable|support|power|battery|resolution|waterproof|volume|dimensions|mount|load|connectivity',str(f),re.I)}
    def category(p):
        c=p.get('category') or {}
        return c.get('slug') if isinstance(c,dict) else None
    products=list(search.get('products') or [])
    if lookup.get('product'): products.insert(0,lookup['product'])
    result=[]
    seen=set()
    for product in products:
        if not isinstance(product,dict): continue
        for index,o in enumerate(product.get('offers') or []):
            if not isinstance(o,dict): continue
            pricing=o.get('price') or {}
            if not isinstance(pricing,dict): continue
            amount=pricing.get('price',pricing.get('amount'))
            url=o.get('url')
            if amount is None or not url or url in seen or o.get('availability')=='OutOfStock': continue
            identity=bool(canonical and product.get('id')==canonical and o.get('condition')=='new' and not o.get('variants'))
            shared=features(reference)&features(product)
            shared_materials={norm(m) for m in as_list(reference.get('materials'))}&{norm(m) for m in as_list(product.get('materials'))}
            equivalent=bool(canonical and product.get('id')!=canonical and category(reference) and category(reference)==category(product)
                            and len(shared)>=2 and shared_materials and o.get('condition')=='new' and not o.get('variants'))
            try:
                offer=Offer(id=f"{product.get('id','unknown')}-{index}",name=product.get('title','Unknown product'),
                    merchant=o.get('domain','Unknown merchant'),url=url,price=Decimal(str(amount)),currency=pricing.get('currency','UNKNOWN'),
                    match='identical' if identity else 'equivalent' if equivalent else 'unverified',
                    match_reason='Same canonical Channel3 product; new condition, no unresolved variants' if identity else
                        ('Functional candidate: same category/material and shared explicit specifications: '+', '.join(sorted(shared))+'. Verify dimensions and performance; different product.') if equivalent else
                        'Search candidate; identity, condition and configuration require verification. Query similarity alone is insufficient.',
                    synthetic=False,specifications={'product_id':product.get('id'),'materials':product.get('materials'),
                        'key_features':product.get('key_features'),'category':product.get('category'),'shared_functional_specifications':sorted(shared),
                        'dimensions':o.get('dimensions'),'condition':o.get('condition'),'variants':o.get('variants')},total_known=False)
                result.append(offer)
                seen.add(url)
            except (ValidationError,InvalidOperation,TypeError,ValueError): continue
    return result

def status_metadata(search,offers,http_status,lookup_http_status=None,query=None):
    return dict(mode='LIVE_API',detail='Live Channel3 catalog response. Item prices do not establish final payable totals.',source=DOCS,
        http_status=http_status,search_http_status=http_status,lookup_http_status=lookup_http_status,
        product_count=len(search.get('products') or []),offer_count=len(offers),query=query,
        error_code=None,retry_after_seconds=None)

async def research(query,limit=12,reference_url=None):
    client=Channel3Client()
    lookup,lookup_status={},None
    if reference_url: lookup,lookup_status=await client.lookup(reference_url)
    search,search_status=await client.search(query,limit)
    offers=normalize(search,lookup)
    return dict(products=search['products'],offers=[o.model_dump(mode='json') for o in offers],
                channel3=status_metadata(search,offers,search_status,lookup_status,query))

async def compare(m: Mandate,audit_id: str):
    local=controlled_url(str(m.product_url))
    if local and m.market_mode=='synthetic':
        return seed_offers(m.scenario,setting('STOREFRONT_URL','http://127.0.0.1:8000')),dict(
            mode='SYNTHETIC_FIXTURE',detail='MOCK: reproducible synthetic catalog selected. Enable live discovery for real Search results.',
            source=DOCS,http_status=None,product_count=3,offer_count=3,query=None,error_code=None)
    client=Channel3Client()
    sr,lr={},{}
    search_status,lookup_status=None,None
    try:
        if not local: lr,lookup_status=await client.lookup(str(m.product_url))
        query=m.market_query.strip() or (lr.get('product') or {}).get('title') or SCENARIOS[m.scenario]['name']
        sr,search_status=await client.search(query)
        (DATA/f'{audit_id}-channel3.json').write_text(json.dumps({'search':sr,'lookup':lr}),encoding='utf-8')
        offers=normalize(sr,lr)
        metadata=status_metadata(sr,offers,search_status,lookup_status,query)
        if not sr['products']: metadata['detail']='Live Search returned zero products. No alternatives were fabricated.'
        return offers,metadata
    except Channel3Error as exc:
        offers=normalize(sr,lr)
        if offers:
            return offers,dict(mode='LIVE_API',source=DOCS,**exc.public(),search_http_status=exc.http_status,
                lookup_http_status=lookup_status,product_count=1,offer_count=len(offers),query=m.market_query,
                partial=True)
        return (seed_offers(m.scenario,setting('STOREFRONT_URL','http://127.0.0.1:8000')) if local else []),dict(
            mode='SYNTHETIC_FALLBACK' if local else 'UNAVAILABLE',source=DOCS,**exc.public(),
            product_count=0,offer_count=3 if local else 0,query=m.market_query,
            fallback_note='MOCK synthetic fixture rows shown after API failure.' if local else 'No mock products substituted for this external merchant.')
