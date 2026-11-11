import json
import base64
from datetime import datetime,timezone,timedelta
from decimal import Decimal
import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend import paypal,storage
from backend.main import app
from backend.models import Mandate
from backend.seeds import seed_product,seed_offers
from backend.carbon import estimate
from backend.governance import market_matrix,validate

BASE='http://127.0.0.1:8000'

@pytest.fixture
def audit(monkeypatch):
    p=seed_product('clean',BASE)
    m=Mandate(product_url=p.url)
    carbon=estimate(p,False,0,50)
    market=market_matrix(p,seed_offers('clean',BASE))
    epistemic={'claims':[]}
    persona={'delta':0}
    decision,findings=validate(m,p,carbon,market,epistemic,persona,0)
    a=dict(id='a'*24,created_at=datetime.now(timezone.utc).isoformat(),mandate=m.model_dump(mode='json'),
           product=p.model_dump(mode='json'),carbon=carbon,market=market,epistemic=epistemic,persona=persona,
           decision=decision,findings=findings,fiat={'total':76})
    storage.save_audit(a)
    async def collect(*args): return p,[],{}
    monkeypatch.setattr(paypal,'collect',collect)
    return a

@pytest.mark.asyncio
@pytest.mark.parametrize('status',[200,401,403,500])
async def test_auth_only_returns_status_never_secrets(status,monkeypatch):
    monkeypatch.setenv('PAYPAL_CLIENT_ID','unit-client')
    monkeypatch.setenv('PAYPAL_CLIENT_SECRET','unit-secret')
    async def post(self,url,**kwargs):
        assert url=='https://api-m.sandbox.paypal.com/v1/oauth2/token'
        assert kwargs['data']=={'grant_type':'client_credentials'}
        assert isinstance(kwargs['auth'],httpx.BasicAuth)
        return httpx.Response(status,json={'access_token':'unit-access-token','debug':'unit-secret'},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    result=await paypal.test_auth()
    assert result=={'connected':status==200,'http_status':status}
    assert 'unit-' not in json.dumps(result)

def test_auth_endpoint_has_exact_public_contract(monkeypatch):
    async def check(): return {'connected':True,'http_status':200}
    monkeypatch.setattr(paypal,'test_auth',check)
    response=TestClient(app).post('/api/paypal/test-auth')
    assert response.status_code==200
    assert response.json()=={'connected':True,'http_status':200}

@pytest.mark.asyncio
async def test_unconfigured_auth_returns_status_only():
    assert await paypal.test_auth()=={'connected':False,'http_status':503}

@pytest.mark.asyncio
@pytest.mark.parametrize('decision',['BLOCK','REVIEW'])
async def test_create_rejects_non_pass_before_any_api_call(audit,decision,monkeypatch):
    audit['decision']=decision
    with storage.db() as c: c.execute('UPDATE audits SET payload=? WHERE id=?',(json.dumps(audit),audit['id']))
    async def never(*args,**kwargs): pytest.fail('PayPal must never be called for non-PASS audits')
    monkeypatch.setattr(paypal,'request',never)
    with pytest.raises(HTTPException) as exc: await paypal.create(audit['id'],True,Decimal('76'))
    assert exc.value.status_code==409

@pytest.mark.asyncio
@pytest.mark.parametrize('approved,total',[(False,76),(True,75),(True,77)])
async def test_buyer_must_approve_exact_total(audit,approved,total,monkeypatch):
    async def never(*args,**kwargs): pytest.fail('No PayPal request without matching buyer approval')
    monkeypatch.setattr(paypal,'request',never)
    with pytest.raises(HTTPException): await paypal.create(audit['id'],approved,Decimal(total))

@pytest.mark.asyncio
async def test_expired_audit_cannot_create(audit):
    audit['created_at']=(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat()
    with storage.db() as c: c.execute('UPDATE audits SET payload=?',(json.dumps(audit),))
    with pytest.raises(HTTPException) as exc: await paypal.gate(audit['id'],True,76)
    assert exc.value.status_code==409

@pytest.mark.asyncio
async def test_changed_dom_requires_new_audit(audit,monkeypatch):
    p=seed_product('anchor',BASE)
    async def changed(*args): return p,[],{}
    monkeypatch.setattr(paypal,'collect',changed)
    with pytest.raises(HTTPException) as exc: await paypal.gate(audit['id'],True,76)
    assert exc.value.status_code==409

@pytest.mark.asyncio
async def test_updated_monthly_ledger_cannot_bypass_gate(audit):
    with storage.db() as c: c.execute('INSERT INTO ledger VALUES (?,?,?,?,?)',('previous',storage.month(),0,49,'SIMULATED'))
    with pytest.raises(HTTPException) as exc: await paypal.gate(audit['id'],True,76)
    assert exc.value.status_code==409

@pytest.mark.asyncio
async def test_create_and_capture_require_separate_buyer_approval(audit,monkeypatch):
    calls=[]
    state={'approved':False}
    async def request(method,path,body=None,request_id=None):
        calls.append((method,path,body))
        if path=='/v2/checkout/orders':
            assert body['purchase_units'][0]['amount']=={'currency_code':'USD','value':'76.00'}
            assert body['intent']=='CAPTURE'
            assert 'payment_source' in body
            assert '/capture' not in path
            return {'id':'TESTORDER123','status':'PAYER_ACTION_REQUIRED','links':[{'rel':'payer-action','href':'https://www.sandbox.paypal.com/checkoutnow?token=TESTORDER123'}]}
        if method=='GET': return {'status':'APPROVED' if state['approved'] else 'CREATED'}
        return {'status':'COMPLETED','purchase_units':[{'payments':{'captures':[{'id':'CAP123','status':'COMPLETED','amount':{'value':'76.00','currency_code':'USD'}}]}}]}
    monkeypatch.setattr(paypal,'request',request)
    order=await paypal.create(audit['id'],True,76)
    assert len(calls)==1 and storage.usage()['carbon']==0
    assert order['carbon_leg']['mode']=='SIMULATED' and order['carbon_leg']['credited_kg']==0
    # A return_url or local boolean is insufficient. PayPal must report APPROVED.
    with pytest.raises(HTTPException): await paypal.capture(audit['id'],'TESTORDER123',True,76)
    assert not any('/capture' in path for _,path,_ in calls)
    state['approved']=True
    result=await paypal.capture(audit['id'],'TESTORDER123',True,76)
    assert result['status']=='COMPLETED'
    assert storage.usage()['fiat']==76
    assert storage.usage()['carbon']==pytest.approx(audit['carbon']['gross_kg'])
    await paypal.capture(audit['id'],'TESTORDER123',True,76)
    assert storage.usage()['fiat']==76 # Idempotent ledger accounting.

@pytest.mark.asyncio
@pytest.mark.parametrize('amount,currency,status',[('77.00','USD','COMPLETED'),('76.00','EUR','COMPLETED'),('76.00','USD','PENDING')])
async def test_bad_capture_never_posts_ledger(audit,monkeypatch,amount,currency,status):
    with storage.db() as c: c.execute('INSERT INTO orders VALUES (?,?,?,?,?)',('TESTORDER123',audit['id'],'76.00','CREATED','{}'))
    async def request(method,*args):
        if method=='GET': return {'status':'APPROVED'}
        return {'status':'COMPLETED','purchase_units':[{'payments':{'captures':[{'id':'cap','status':status,'amount':{'value':amount,'currency_code':currency}}]}}]}
    monkeypatch.setattr(paypal,'request',request)
    with pytest.raises(HTTPException): await paypal.capture(audit['id'],'TESTORDER123',True,76)
    assert storage.usage()=={'carbon':0,'fiat':0}

@pytest.mark.asyncio
async def test_simulation_does_not_call_paypal(audit,monkeypatch):
    async def never(*args): pytest.fail('Simulation cannot call PayPal')
    monkeypatch.setattr(paypal,'request',never)
    result=await paypal.simulate(audit['id'],True,76)
    assert result['mode']=='SIMULATED' and result['order_id'].startswith('SIM-')
    assert result['carbon_leg']['credited_kg']==0

@pytest.mark.asyncio
async def test_external_merchants_never_use_our_credentials(audit):
    audit['product']['url']='https://external.example/product'
    audit['product']['controlled']=False
    with storage.db() as c: c.execute('UPDATE audits SET payload=?',(json.dumps(audit),))
    with pytest.raises(HTTPException) as exc: await paypal.gate(audit['id'],True,76)
    assert exc.value.status_code==403

def test_endpoint_requires_explicit_total():
    assert TestClient(app).post('/api/paypal/orders',json={'audit_id':'test','buyer_approved':True}).status_code==422

@pytest.mark.asyncio
async def test_synthetic_arbitrage_offer_cannot_create_real_order(audit,monkeypatch):
    p=seed_product('clean',BASE,'north')
    audit['product']=p.model_dump(mode='json')
    audit['fiat']['total']=62
    audit['mandate']['product_url']=p.url
    with storage.db() as c: c.execute('UPDATE audits SET payload=?',(json.dumps(audit),))
    async def fresh(*args): return p,[],{}
    monkeypatch.setattr(paypal,'collect',fresh)
    with pytest.raises(HTTPException) as exc: await paypal.create(audit['id'],True,62)
    assert exc.value.status_code==403
    assert (await paypal.simulate(audit['id'],True,62))['mode']=='SIMULATED'

@pytest.mark.asyncio
async def test_identical_credentials_rejected_before_network(monkeypatch):
    monkeypatch.setenv('PAYPAL_CLIENT_ID','unit-client')
    monkeypatch.setenv('PAYPAL_CLIENT_SECRET','unit-client')
    async def never(*args,**kwargs): pytest.fail('Duplicated credentials must not reach PayPal')
    monkeypatch.setattr(httpx.AsyncClient,'post',never)
    assert not paypal.configured()
    assert 'duplicates' in paypal.configuration_problem()
    assert await paypal.test_auth()=={'connected':False,'http_status':503}
    with pytest.raises(HTTPException) as error: await paypal.request('POST','/v2/checkout/orders',{})
    assert error.value.status_code==503
    assert 'unit-client' not in str(error.value.detail)

@pytest.mark.asyncio
async def test_oauth_wire_request_has_basic_auth_and_form_grant(monkeypatch):
    monkeypatch.setenv('PAYPAL_CLIENT_ID','unit-client')
    monkeypatch.setenv('PAYPAL_CLIENT_SECRET','unit-secret')
    def inspect(request):
        assert str(request.url)=='https://api-m.sandbox.paypal.com/v1/oauth2/token'
        scheme,encoded=request.headers['Authorization'].split(' ',1)
        assert scheme=='Basic'
        assert base64.b64decode(encoded)==b'unit-client:unit-secret'
        assert request.headers['Content-Type']=='application/x-www-form-urlencoded'
        assert request.content==b'grant_type=client_credentials'
        return httpx.Response(200,json={'access_token':'mock-token','token_type':'Bearer'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(inspect)) as client:
        token,status=await paypal.oauth_token(client)
    assert token=='mock-token' and status==200

@pytest.mark.parametrize('decision,max_spend,cap,policy',[
    ('BLOCK',75,8,'strict'),('REVIEW',100,3,'reviewable_carbon'),
])
def test_real_deterministic_non_pass_blocks_order_endpoint(audit,monkeypatch,decision,max_spend,cap,policy):
    p=seed_product('clean',BASE)
    m=Mandate(product_url=p.url,max_spend=max_spend,purchase_carbon_cap=cap,override_policy=policy)
    computed,findings=validate(m,p,audit['carbon'],audit['market'],audit['epistemic'],audit['persona'],0)
    assert computed==decision
    audit.update(mandate=m.model_dump(mode='json'),decision=computed,findings=findings)
    with storage.db() as c: c.execute('UPDATE audits SET payload=?',(json.dumps(audit),))
    async def never(*args,**kwargs): pytest.fail('BLOCK/REVIEW endpoint must not authenticate or create a PayPal order')
    monkeypatch.setattr(paypal,'request',never)
    response=TestClient(app).post('/api/paypal/orders',json={'audit_id':audit['id'],'buyer_approved':True,'approved_total':76})
    assert response.status_code==409
    with storage.db() as c: assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0

def test_forged_pass_is_revalidated_before_network(audit,monkeypatch):
    audit['mandate']['max_spend']='75.00'
    assert audit['decision']=='PASS'
    with storage.db() as c: c.execute('UPDATE audits SET payload=?',(json.dumps(audit),))
    async def never(*args,**kwargs): pytest.fail('Stale/forged PASS must not reach PayPal')
    monkeypatch.setattr(paypal,'request',never)
    response=TestClient(app).post('/api/paypal/orders',json={'audit_id':audit['id'],'buyer_approved':True,'approved_total':76})
    assert response.status_code==409
