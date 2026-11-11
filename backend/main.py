import asyncio
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from .config import DATA, ROOT, setting
from .models import Mandate, Approval, Capture,ProductSearch,ProductLookup,ProductDiscovery
from . import storage, paypal
from .seeds import seed_product
from .storefront import render
from .extractor import collect
from .channel3 import compare,research,normalize,Channel3Client,Channel3Error
from .epistemic import assess
from .carbon import estimate
from .governance import market_matrix, validate
from .discovery import discover,validate_public_product_url

app=FastAPI(title='Quantitative Commerce Terminal',version='1.0.0')

@app.get('/api/health')
def health():
    return dict(status='ok',channel3_configured=bool(setting('CHANNEL3_API_KEY')),llm_configured=bool(setting('LLM_API_KEY')),
                paypal_configured=paypal.configured(),paypal_mode='SANDBOX_ONLY',carbon_partner_mode='SIMULATED',ledger=storage.usage())

@app.get('/store/{scenario}',response_class=HTMLResponse)
def store(scenario: str,request: Request,offer: str | None=None):
    if scenario not in ('clean','anchor','carbon') or offer not in (None,'north','form','studio'): raise HTTPException(404)
    return render(seed_product(scenario,setting('STOREFRONT_URL','http://127.0.0.1:8000'),offer),request.cookies.get('returning_customer')=='1')

@app.post('/api/audits')
async def audit(m: Mandate):
    audit_id=secrets.token_hex(12)
    try:
        extraction,market_result=await asyncio.gather(collect(str(m.product_url),audit_id),compare(m,audit_id))
    except (ValueError,OSError) as exc: raise HTTPException(422,str(exc)) from exc
    p,evidence,persona=extraction
    offers,channel_status=market_result
    epistemic=await assess(p,evidence,audit_id)
    usage=storage.usage()
    carbon=estimate(p,m.offset_opt_in,usage['carbon'],m.monthly_carbon_cap)
    market=market_matrix(p,offers)
    decision,findings=validate(m,p,carbon,market,epistemic,persona,usage['carbon'])
    result=dict(id=audit_id,created_at=datetime.now(timezone.utc).isoformat(),mandate=m.model_dump(mode='json'),product=p.model_dump(mode='json'),
        evidence=evidence,persona=persona,channel3=channel_status,epistemic=epistemic,carbon=carbon,market=market,
        offers=[o.model_dump(mode='json') for o in offers],decision=decision,findings=findings,
        fiat=dict(item=float(p.advertised) if p.advertised is not None else None,shipping=float(p.shipping_cost) if p.shipping_cost is not None else None,
                  tax=float(p.tax) if p.tax is not None else None,fees=float(p.fees) if p.fees is not None else None,
                  merchant_total=float(p.final) if p.final is not None else None,offset=carbon['offset_amount'],
                  total=float(p.final+Decimal(str(carbon['offset_amount']))) if p.final is not None else None,monthly_settled=usage['fiat']))
    storage.save_audit(result)
    return result

@app.get('/api/audits')
def audits(): return storage.history()

def channel_error(exc: Channel3Error):
    code=exc.http_status if exc.http_status in (401,403,404,429,503) else 404 if exc.code=='PRODUCT_NOT_FOUND' else 504 if exc.code=='TIMEOUT' else 502
    return HTTPException(code,exc.public(),headers={'Retry-After':str(exc.retry_after)} if exc.retry_after is not None else None)

@app.post('/api/channel3/search')
async def search_products(body: ProductSearch):
    try:
        if body.reference_url: await asyncio.to_thread(validate_public_product_url,str(body.reference_url))
        return await research(body.query,body.limit,str(body.reference_url) if body.reference_url else None)
    except Channel3Error as exc: raise channel_error(exc) from None
    except ValueError as exc: raise HTTPException(422,str(exc)) from None

@app.post('/api/channel3/lookup')
async def lookup_product(body: ProductLookup):
    try:
        await asyncio.to_thread(validate_public_product_url,str(body.url))
        data,status=await Channel3Client().lookup(str(body.url))
        offers=normalize({},data)
        return dict(mode='LIVE_API',http_status=status,product=data['product'],offers=[o.model_dump(mode='json') for o in offers])
    except Channel3Error as exc: raise channel_error(exc) from None
    except ValueError as exc: raise HTTPException(422,str(exc)) from None

@app.post('/api/channel3/discover')
async def discover_product(body: ProductDiscovery):
    try: return await discover(str(body.url),body.query,body.limit)
    except ValueError as exc: raise HTTPException(422,str(exc)) from None

@app.get('/api/audits/{audit_id}')
def read_audit(audit_id: str):
    result=storage.get_audit(audit_id)
    if not result: raise HTTPException(404,'Audit not found')
    return result

@app.get('/api/audits/{audit_id}/snapshot')
def snapshot(audit_id: str):
    if not storage.get_audit(audit_id): raise HTTPException(404)
    return FileResponse(DATA/'evidence'/f'{audit_id}.html',media_type='text/plain')

@app.post('/api/paypal/orders')
async def create_order(body: Approval): return await paypal.create(body.audit_id,body.buyer_approved,body.approved_total)

@app.post('/api/paypal/test-auth')
async def test_paypal_auth():
    """Read-only Sandbox connectivity check. Deliberately returns no OAuth material."""
    return await paypal.test_auth()

@app.get('/api/paypal/checkout')
async def checkout_state(audit_id: str | None=None,order_id: str | None=None):
    return await paypal.checkout_state(audit_id,order_id)

@app.get('/api/paypal/return')
def paypal_return(audit: str | None=None,token: str | None=None):
    # Returning from PayPal is not proof of buyer approval and never captures payment.
    return RedirectResponse(paypal.return_destination(audit,token),status_code=303)

@app.get('/api/paypal/cancel')
def paypal_cancel(audit: str | None=None,token: str | None=None):
    return RedirectResponse(paypal.return_destination(audit,token,cancelled=True),status_code=303)

@app.post('/api/paypal/capture')
async def capture_order(body: Capture): return await paypal.capture(body.audit_id,body.order_id,body.buyer_approved,body.approved_total)

@app.post('/api/payments/simulate')
async def simulate(body: Approval): return await paypal.simulate(body.audit_id,body.buyer_approved,body.approved_total)

# Optional single-process serving after npm run build. Only dist is served, never .env/data.
if (ROOT/'dist').is_dir():
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
