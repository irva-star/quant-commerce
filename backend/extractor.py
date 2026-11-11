import asyncio
import hashlib
import ipaddress
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
from .config import DATA, setting
from .models import Product, Material, Evidence
from .seeds import seed_product
from .page_data import SCRIPT,normalize_observations

def controlled_url(url: str):
    parsed=urlparse(url)
    bases=[urlparse(setting('STOREFRONT_URL','http://127.0.0.1:8000')),urlparse(setting('APP_URL','http://127.0.0.1:8765'))]
    return any((parsed.scheme,parsed.hostname,parsed.port)==(base.scheme,base.hostname,base.port) for base in bases) and parsed.path in ('/store/clean','/store/anchor','/store/carbon')

def check_url(url: str):
    if controlled_url(url): return
    parsed=urlparse(url)
    allowed={s.strip().lower() for s in setting('AUDIT_ALLOWED_HOSTS').split(',') if s.strip()}
    if parsed.scheme!='https' or parsed.hostname not in allowed or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('URL must be the controlled storefront or an explicitly allowlisted public HTTPS host (AUDIT_ALLOWED_HOSTS).')
    for result in socket.getaddrinfo(parsed.hostname,443):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError('Private/internal network destinations are not permitted.')

def evidence_from_fields(fields,url,synthetic,snapshot,sources=None):
    now=datetime.now(timezone.utc).isoformat()
    digest=hashlib.sha256(snapshot.encode()).hexdigest()
    return [Evidence(id=f'e{i:02}',field=key,value=str(value),url=url,selector=(sources or {}).get(key,f'[data-qct="{key}"]'),
                     captured_at=now,synthetic=synthetic,sha256=digest).model_dump() for i,(key,value) in enumerate(fields.items())]

def parse_fields(fields,url):
    allowed=Product.model_fields.keys()
    data={k:v for k,v in fields.items() if k in allowed and k not in ('controlled','synthetic','url')}
    if 'materials' in data:
        data['materials']=[Material(name=m.split(':')[0],fraction=float(m.split(':')[1])) for m in data['materials'].split(';')]
    if 'recurring' in data: data['recurring']=data['recurring'] in ('true',True)
    for key in ('advertised','reference','final','fees','shipping_cost','tax','recurring_amount','mass_kg','shipment_kg','distance_km','manufacturing_kwh','manufacturing_factor'):
        if data.get(key) in ('None','null',''): data[key]=None
    return Product(**data,url=url,controlled=controlled_url(url),synthetic=controlled_url(url))

async def collect(url: str, audit_id: str):
    await asyncio.to_thread(check_url,url)
    is_controlled=controlled_url(url)
    base=setting('STOREFRONT_URL','http://127.0.0.1:8000')
    scenario=urlparse(url).path.rsplit('/',1)[-1]
    offer=parse_qs(urlparse(url).query).get('offer',[None])[0]
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True)
            async def session(personalized):
                context=await browser.new_context(locale='en-US',timezone_id='America/New_York',viewport={'width':1280,'height':800},service_workers='block',accept_downloads=False)
                async def guard(route):
                    try:
                        await asyncio.to_thread(check_url,route.request.url)
                        await route.continue_()
                    except (ValueError,OSError): await route.abort()
                await context.route('**/*',guard)
                if personalized:
                    await context.add_cookies([{'name':'returning_customer','value':'1','url':base}])
                page=await context.new_page()
                await page.goto(url,wait_until='domcontentloaded',timeout=20000)
                raw=await page.evaluate(SCRIPT)
                fields,sources,notes=normalize_observations(raw,url)
                snapshot=await page.content()
                await context.close()
                return fields,snapshot,sources,notes
            clean,personalized=await asyncio.gather(session(False),session(True)) if is_controlled else (await session(False),None)
            await browser.close()
        fields,snapshot,sources,notes=clean
        if not fields.get('name'):
            # Unknown merchant schemas do not get invented checkout/material fields.
            fields.update(name=urlparse(url).hostname or 'External listing',merchant=urlparse(url).hostname or 'Unknown')
        p=parse_fields(fields,url)
        mode='PLAYWRIGHT_DOM'
        evidence=evidence_from_fields(fields,url,is_controlled,snapshot,sources)
        if personalized:
            pf,ps,persona_sources,_=personalized
            persona_dir=DATA/'evidence'
            persona_dir.mkdir(exist_ok=True)
            (persona_dir/f'{audit_id}-personalized.html').write_text(ps,encoding='utf-8')
            evidence+= [dict(e,id='p'+e['id']) for e in evidence_from_fields(pf,url,True,ps,persona_sources)]
            personalized_price=float(pf['final']) if pf.get('final') else None
        else: personalized_price=None
        note=('Isolated Chromium contexts; same locale, time zone, viewport, URL and destination. Only returning_customer cookie changes. Single paired observation; no demographic inference, statistical significance or discrimination claim.' if is_controlled else 'External Product/Offer JSON-LD and explicit selector extraction. Item offers are not checkout totals. No persona experiment on external merchants.')+' '.join(notes)
    except Exception as exc:
        if not is_controlled: raise ValueError('DOM extraction failed; no critical checkout evidence was inferred.') from exc
        p=seed_product(scenario,base,offer)
        snapshot=__import__('json').dumps(p.model_dump(mode='json'),sort_keys=True)
        evidence=evidence_from_fields(p.model_dump(mode='json'),url,True,snapshot)
        mode='SYNTHETIC_FIXTURE_FALLBACK'
        personalized_price=None
        note=f'Browser audit unavailable ({type(exc).__name__}). Fixture evidence only; no counterfactual observation was made. Install Chromium with python -m playwright install chromium.'
    evidence_dir=DATA/'evidence'
    evidence_dir.mkdir(exist_ok=True)
    (evidence_dir/f'{audit_id}.html').write_text(snapshot,encoding='utf-8')
    clean_price=float(p.final) if p.final is not None else None
    return p,evidence,dict(mode=mode,clean_price=clean_price,personalized_price=personalized_price,
                           delta=round(personalized_price-clean_price,2) if personalized_price is not None and clean_price is not None else None,
                           variable='returning_customer=1 cookie' if is_controlled else 'Not run on external merchant',limitations=note)
