import json
from datetime import datetime,timezone,timedelta
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend import paypal,storage
from backend.main import app
from backend.tests.test_paypal import audit
from backend.extractor import controlled_url

def test_public_merchant_and_internal_storefront_are_both_controlled(monkeypatch):
    monkeypatch.setenv('APP_URL','http://127.0.0.1:8765')
    monkeypatch.setenv('STOREFRONT_URL','http://127.0.0.1:8000')
    assert controlled_url('http://127.0.0.1:8765/store/clean')
    assert controlled_url('http://127.0.0.1:8000/store/clean')
    assert not controlled_url('http://127.0.0.1:9999/store/clean')
    assert not controlled_url('http://127.0.0.1:8765/api/paypal/orders')

@pytest.fixture
def checkout(audit):
    payload={'order_id':'TESTORDER123','approval_url':'https://www.sandbox.paypal.com/checkoutnow?token=TESTORDER123','mode':'PAYPAL_SANDBOX'}
    with storage.db() as c: c.execute('INSERT INTO orders VALUES (?,?,?,?,?)',('TESTORDER123',audit['id'],'76.00','CREATED',json.dumps(payload)))
    return audit,payload

def test_callback_uses_configured_8765_and_resolves_token_without_audit(checkout,monkeypatch):
    audit,_=checkout
    monkeypatch.setenv('APP_URL','http://127.0.0.1:8765')
    response=TestClient(app).get('/api/paypal/return?token=TESTORDER123',follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location'].startswith('http://127.0.0.1:8765/?paypal=returned')
    assert 'audit='+audit['id'] in response.headers['location']
    assert 'order=TESTORDER123' in response.headers['location']

def test_cancel_does_not_capture_or_create_new_order(checkout,monkeypatch):
    audit,_=checkout
    async def never(*args,**kwargs): pytest.fail('PayPal callbacks must never mutate payments')
    monkeypatch.setattr(paypal,'request',never)
    response=TestClient(app).get('/api/paypal/cancel?audit='+audit['id']+'&token=TESTORDER123',follow_redirects=False)
    assert response.status_code==303 and 'paypal=cancelled' in response.headers['location']
    with storage.db() as c: assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1

def test_unknown_return_is_explicit_and_never_becomes_pass():
    response=TestClient(app).get('/api/paypal/return?token=UNKNOWN123',follow_redirects=False)
    assert 'paypal=unresolved' in response.headers['location']

@pytest.mark.asyncio
@pytest.mark.parametrize('status,verified',[('PAYER_ACTION_REQUIRED',False),('APPROVED',True)])
async def test_restoration_uses_provider_status_not_return_query(checkout,monkeypatch,status,verified):
    audit,_=checkout
    async def read_only(method,path,*args):
        assert method=='GET'
        return {'status':status,'purchase_units':[{'amount':{'value':'76.00','currency_code':'USD'}}]}
    monkeypatch.setattr(paypal,'request',read_only)
    state=await paypal.checkout_state(order_id='TESTORDER123')
    assert state['audit_id']==audit['id'] and state['approval_verified']==verified
    assert state['paypal_status']==status and not state['capture_completed']

@pytest.mark.asyncio
async def test_missing_query_recovers_existing_order_without_new_purchase(checkout,monkeypatch):
    audit,_=checkout
    async def read_only(*args): return {'status':'PAYER_ACTION_REQUIRED','purchase_units':[{'amount':{'value':'76.00','currency_code':'USD'}}]}
    monkeypatch.setattr(paypal,'request',read_only)
    state=await paypal.checkout_state()
    assert state['audit_id']==audit['id'] and state['order_id']=='TESTORDER123'
    with storage.db() as c: assert c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1

@pytest.mark.asyncio
async def test_expired_checkout_is_restored_but_not_authorized(checkout,monkeypatch):
    audit,_=checkout
    audit['created_at']=(datetime.now(timezone.utc)-timedelta(minutes=20)).isoformat()
    with storage.db() as c: c.execute('UPDATE audits SET payload=?',(json.dumps(audit),))
    async def read_only(*args): return {'status':'APPROVED','purchase_units':[{'amount':{'value':'76.00','currency_code':'USD'}}]}
    monkeypatch.setattr(paypal,'request',read_only)
    state=await paypal.checkout_state(audit_id=audit['id'])
    assert state['audit_expired']
    with pytest.raises(HTTPException) as error: await paypal.capture(audit['id'],'TESTORDER123',True,76)
    assert error.value.status_code==409

@pytest.mark.asyncio
async def test_mismatched_total_or_unknown_provider_never_authorizes(checkout,monkeypatch):
    async def wrong_amount(*args): return {'status':'APPROVED','purchase_units':[{'amount':{'value':'77.00','currency_code':'USD'}}]}
    monkeypatch.setattr(paypal,'request',wrong_amount)
    state=await paypal.checkout_state(order_id='TESTORDER123')
    assert not state['approval_verified'] and state['warning']
    async def offline(*args): raise HTTPException(502,'unavailable')
    monkeypatch.setattr(paypal,'request',offline)
    state=await paypal.checkout_state(order_id='TESTORDER123')
    assert state['paypal_status']=='UNVERIFIED' and not state['approval_verified']

@pytest.mark.asyncio
async def test_order_and_audit_cannot_be_substituted(checkout):
    with pytest.raises(HTTPException) as error: await paypal.checkout_state('another-audit','TESTORDER123')
    assert error.value.status_code==409
