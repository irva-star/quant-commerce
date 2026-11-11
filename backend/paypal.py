import asyncio
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse,parse_qs,urlencode
import httpx
from fastapi import HTTPException
from . import storage
from .config import setting
from .extractor import collect, controlled_url
from .governance import validate
from .models import Mandate, Product
from .partners import carbon_partner

# Local single-buyer MVP: one API process. SQLite persists orders/ledger; lock serializes settlements.
settlement_lock=asyncio.Lock()
BASE='https://api-m.sandbox.paypal.com'

def configuration_problem():
    """Return a safe actionable category; never include either credential value."""
    client_id=setting('PAYPAL_CLIENT_ID')
    client_secret=setting('PAYPAL_CLIENT_SECRET')
    if not client_id or not client_secret:
        return 'PayPal Sandbox Client ID and Secret are required in the workspace-root .env.'
    if client_id==client_secret:
        return 'PAYPAL_CLIENT_SECRET duplicates PAYPAL_CLIENT_ID. Copy the Secret from the same Sandbox REST app into the workspace-root .env, then restart FastAPI.'
    if any(c.isspace() for c in client_id+client_secret):
        return 'PayPal credentials contain whitespace. Copy the exact Sandbox Client ID and Secret, then restart FastAPI.'
    return None

def configured(): return configuration_problem() is None

async def oauth_token(client: httpx.AsyncClient):
    """Token is ephemeral server memory only. Never include upstream bodies in errors."""
    if not configured(): return None,503
    try:
        response=await client.post(BASE+'/v1/oauth2/token',
            auth=httpx.BasicAuth(setting('PAYPAL_CLIENT_ID'),setting('PAYPAL_CLIENT_SECRET')),
            data={'grant_type':'client_credentials'},headers={'Accept':'application/json'})
        if response.status_code!=200: return None,response.status_code
        token=response.json().get('access_token')
        return (token,200) if isinstance(token,str) and token else (None,502)
    except (httpx.HTTPError,ValueError): return None,None

async def test_auth():
    async with httpx.AsyncClient(timeout=20) as client:
        token,status=await oauth_token(client)
    return {'connected':bool(token),'http_status':status}

async def request(method,path,body=None,request_id=None):
    problem=configuration_problem()
    if problem: raise HTTPException(503,problem)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token,status=await oauth_token(client)
            if not token: raise HTTPException(502,{'message':'PayPal Sandbox authentication failed','http_status':status})
            r=await client.request(method,BASE+path,json=body,headers={'Authorization':'Bearer '+token,
                'Content-Type':'application/json','PayPal-Request-Id':request_id or secrets.token_hex(16),'Prefer':'return=representation'})
            if r.status_code>=400:
                data=r.json()
                raise HTTPException(502,{'message':'PayPal Sandbox rejected the request','name':data.get('name'),'debug_id':data.get('debug_id')})
            return r.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502,'PayPal Sandbox network/authentication error; no success assumed.') from exc

async def gate(audit_id,approved,approved_total,exclude_order=None,simulated=False):
    if not approved: raise HTTPException(400,'Explicit buyer approval is required.')
    audit=storage.get_audit(audit_id)
    if not audit: raise HTTPException(404,'Audit not found')
    expected_total=Decimal(str(audit['fiat']['total'])) if audit['fiat']['total'] is not None else None
    if expected_total is None or Decimal(str(approved_total))!=expected_total:
        raise HTTPException(409,'Buyer-confirmed total differs from the immutable audited total. Re-audit and approve the displayed costs.')
    if (datetime.now(timezone.utc)-datetime.fromisoformat(audit['created_at'])).total_seconds()>900:
        raise HTTPException(409,'Audit expired after 15 minutes. Run a new mandate audit.')
    m=Mandate.model_validate(audit['mandate'])
    p=Product.model_validate(audit['product'])
    if not p.controlled or not controlled_url(p.url): raise HTTPException(403,'Only the controlled demo merchant can use these PayPal Sandbox credentials. Visit external merchants directly.')
    if not simulated and 'offer' in parse_qs(urlparse(p.url).query):
        raise HTTPException(403,'Synthetic arbitrage merchants are simulation-only. PayPal Sandbox orders are limited to the original controlled demo merchant.')
    if audit['decision']!='PASS': raise HTTPException(409,'Settlement requires PASS; resolve all BLOCK/REVIEW findings and rerun the audit.')
    current=storage.usage()['carbon']
    with storage.db() as c:
        for r in c.execute("SELECT * FROM orders WHERE status != 'COMPLETED'"):
            if r['id']!=exclude_order and r['audit_id']!=audit_id:
                other=storage.get_audit(r['audit_id'])
                current+=other['carbon']['gross_kg'] or 0
    decision,findings=validate(m,p,audit['carbon'],audit['market'],audit['epistemic'],audit['persona'],current)
    if decision!='PASS': raise HTTPException(409,{'message':'Mandate no longer passes against current ledger and pending reservations. Re-audit.','findings':findings})
    fresh,_,_=await collect(p.url,secrets.token_hex(8))
    keys=['advertised','reference','final','fees','shipping_cost','tax','recurring','recurring_amount','mass_kg','shipment_kg','materials','origin','destination','mode','distance_km','manufacturing_kwh','manufacturing_factor','claims','currency','sku']
    if any(getattr(p,k)!=getattr(fresh,k) for k in keys): raise HTTPException(409,'Storefront evidence changed since approval. Re-audit before payment.')
    return audit

def record(order_id,audit,mode):
    with storage.db() as c:
        c.execute('INSERT OR IGNORE INTO ledger VALUES (?,?,?,?,?)',(order_id,storage.month(),float(audit['product']['final']),audit['carbon']['gross_kg'],mode))
        c.execute("UPDATE orders SET status='COMPLETED' WHERE id=?",(order_id,))

def merchant_origin():
    # Match the buyer-facing origin (including its port), not the internal API port.
    return setting('APP_URL','http://127.0.0.1:8765').rstrip('/')

def stored_checkout(audit_id=None,order_id=None):
    with storage.db() as c:
        if order_id:
            row=c.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone()
            if row and audit_id and row['audit_id']!=audit_id: raise HTTPException(409,'PayPal order does not belong to this audit.')
        elif audit_id: row=c.execute('SELECT * FROM orders WHERE audit_id=?',(audit_id,)).fetchone()
        else:
            row=c.execute("SELECT o.* FROM orders o JOIN audits a ON a.id=o.audit_id WHERE o.status!='COMPLETED' AND o.id NOT LIKE 'SIM-%' ORDER BY a.created_at DESC LIMIT 1").fetchone()
    if not row or row['id'].startswith('SIM-'): return None
    return dict(row)

async def checkout_state(audit_id=None,order_id=None):
    row=stored_checkout(audit_id,order_id)
    if not row: return None
    audit=storage.get_audit(row['audit_id'])
    payload=json.loads(row['payload'])
    state=dict(audit_id=row['audit_id'],order_id=row['id'],approval_url=payload.get('approval_url',''),amount=row['amount'],currency='USD',
        mode='PAYPAL_SANDBOX',paypal_status='UNVERIFIED',approval_verified=False,capture_completed=row['status']=='COMPLETED',
        audit_expired=(datetime.now(timezone.utc)-datetime.fromisoformat(audit['created_at'])).total_seconds()>900,warning=None)
    try:
        upstream=await request('GET','/v2/checkout/orders/'+row['id'])
        units=upstream.get('purchase_units',[])
        amount_matches=bool(units) and all(unit.get('amount',{}).get('currency_code')=='USD' for unit in units) and sum(Decimal(unit['amount']['value']) for unit in units)==Decimal(row['amount'])
        state.update(paypal_status=upstream['status'],approval_verified=amount_matches and upstream['status'] in ('APPROVED','COMPLETED'))
        if not amount_matches: state['warning']='PayPal total does not match the saved checkout. Capture is blocked.'
    except HTTPException:
        state['warning']='Could not verify PayPal status. This return or refresh does not authorize payment.'
    return state

def return_destination(audit_id,order_id,cancelled=False):
    row=stored_checkout(audit_id,order_id)
    params={'paypal':'cancelled' if cancelled else 'returned'}
    if row: params.update(audit=row['audit_id'],order=row['id'])
    else:
        params['paypal']='unresolved'
        if audit_id: params['audit']=audit_id
    return merchant_origin()+'/?'+urlencode(params)

async def create(audit_id,approved,approved_total):
    async with settlement_lock:
        audit=await gate(audit_id,approved,approved_total)
        with storage.db() as c:
            row=c.execute('SELECT * FROM orders WHERE audit_id=?',(audit_id,)).fetchone()
            if row:
                if row['status']=='COMPLETED': raise HTTPException(409,'This audit is already settled. Run a new audit for a new purchase.')
                return json.loads(row['payload'])
        amount=f"{Decimal(audit['product']['final']):.2f}"
        app_url=merchant_origin()
        order=await request('POST','/v2/checkout/orders',{
            'intent':'CAPTURE',
            'purchase_units':[{'reference_id':audit_id,'custom_id':audit_id,'description':'QCT controlled demo merchant — Sandbox purchase',
                               'amount':{'currency_code':'USD','value':amount}}],
            'payment_source':{'paypal':{'experience_context':{'brand_name':'QCT / Demo Merchant','user_action':'PAY_NOW',
                'shipping_preference':'NO_SHIPPING','return_url':app_url+'/api/paypal/return?audit='+audit_id,
                'cancel_url':app_url+'/api/paypal/cancel?audit='+audit_id}}}},'qct-create-'+audit_id)
        link=next((x['href'] for x in order.get('links',[]) if x['rel'] in ('approve','payer-action')),None)
        if not link or urlparse(link).hostname!='www.sandbox.paypal.com': raise HTTPException(502,'PayPal did not return a Sandbox buyer approval URL.')
        payload=dict(order_id=order['id'],status=order['status'],approval_url=link,amount=amount,currency='USD',mode='PAYPAL_SANDBOX',
                     carbon_leg=await carbon_partner.settle(audit_id,audit['carbon']))
        with storage.db() as c:
            c.execute('INSERT INTO orders VALUES (?,?,?,?,?)',(order['id'],audit_id,amount,'CREATED',json.dumps(payload)))
        return payload

async def capture(audit_id,order_id,approved,approved_total):
    async with settlement_lock:
        with storage.db() as c:
            row=c.execute('SELECT * FROM orders WHERE id=? AND audit_id=?',(order_id,audit_id)).fetchone()
        if not row: raise HTTPException(404,'Order is not associated with this audit.')
        if order_id.startswith('SIM-'): raise HTTPException(403,'Simulated orders cannot be captured with PayPal.')
        if row['status']=='COMPLETED':
            if not approved: raise HTTPException(400,'Explicit buyer approval is required.')
            return dict(status='COMPLETED',order_id=order_id,mode='PAYPAL_SANDBOX',already_recorded=True)
        audit=await gate(audit_id,approved,approved_total,order_id)
        # Read before capture also handles response loss after a successful earlier capture.
        order=await request('GET','/v2/checkout/orders/'+order_id)
        if order['status']!='COMPLETED':
            if order['status']!='APPROVED': raise HTTPException(409,'Buyer must approve this order on PayPal Sandbox before capture.')
            order=await request('POST','/v2/checkout/orders/'+order_id+'/capture',{},'qct-capture-'+audit_id)
        captures=[cap for unit in order.get('purchase_units',[]) for cap in unit.get('payments',{}).get('captures',[])]
        if order['status']!='COMPLETED' or not captures or any(c['status']!='COMPLETED' for c in captures):
            raise HTTPException(409,'PayPal capture is not COMPLETED; ledger remains uncredited.')
        if any(c['amount']['currency_code']!='USD' for c in captures) or sum(Decimal(c['amount']['value']) for c in captures)!=Decimal(row['amount']):
            raise HTTPException(409,'PayPal confirmed amount does not match the approved server order.')
        record(order_id,audit,'PAYPAL_SANDBOX')
        return dict(status='COMPLETED',order_id=order_id,mode='PAYPAL_SANDBOX',captures=[c['id'] for c in captures],carbon_leg=await carbon_partner.settle(audit_id,audit['carbon']))

async def simulate(audit_id,approved,approved_total):
    async with settlement_lock:
        audit=await gate(audit_id,approved,approved_total,simulated=True)
        with storage.db() as c:
            old=c.execute('SELECT id FROM orders WHERE audit_id=?',(audit_id,)).fetchone()
            if old: raise HTTPException(409,'This audit already has an order. Run a new audit for a new purchase.')
            order_id='SIM-'+secrets.token_hex(6)
            payload=dict(status='COMPLETED',mode='SIMULATED',order_id=order_id,message='Demo ledger entry only. No PayPal call or movement of money.',carbon_leg=await carbon_partner.settle(audit_id,audit['carbon']))
            c.execute('INSERT INTO orders VALUES (?,?,?,?,?)',(order_id,audit_id,audit['product']['final'],'COMPLETED',json.dumps(payload)))
        record(order_id,audit,'SIMULATED')
        return payload
