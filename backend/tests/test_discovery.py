import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.channel3 import Channel3Client,Channel3Error
from backend.discovery import validate_public_product_url
from backend import storage

URL='https://retailer.example/products/stand'
PRODUCT={'id':'catalog-123','title':'Real catalog stand','materials':['Aluminium'],'key_features':['Adjustable height'],
    'offers':[{'domain':'retailer.example','url':URL,'price':{'price':54,'currency':'CAD'},'condition':'new','availability':'InStock'}]}

@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr('backend.discovery.socket.getaddrinfo',lambda *args,**kwargs:[(2,1,6,'',('93.184.216.34',443))])
    monkeypatch.setenv('AUDIT_ALLOWED_HOSTS','')

def stub_catalog(monkeypatch):
    async def lookup(self,url): assert url==URL;return {'product':PRODUCT},200
    async def search(self,query,limit=12): assert query;return {'products':[PRODUCT]},200
    monkeypatch.setattr(Channel3Client,'lookup',lookup)
    monkeypatch.setattr(Channel3Client,'search',search)

def test_discovery_does_not_require_host_approval_or_run_purchase_pipeline(public_dns,monkeypatch):
    stub_catalog(monkeypatch)
    def never(*args,**kwargs): pytest.fail('Catalog discovery must not run browser/governance/carbon/payment work')
    for target in ('collect','estimate','validate'): monkeypatch.setattr('backend.main.'+target,never)
    monkeypatch.setattr('backend.paypal.request',never)
    response=TestClient(app).post('/api/channel3/discover',json={'url':URL})
    assert response.status_code==200
    data=response.json()
    assert data['product']['title']==PRODUCT['title']
    assert data['offers'][0]['price']=='54' and data['offers'][0]['currency']=='CAD'
    assert data['provenance']['mode']=='LIVE' and data['provenance']['synthetic'] is False
    assert data['decision']=='REVIEW' and data['verification']=={'identity':'RESOLVED','checkout':'NOT VERIFIED','carbon':'NOT VERIFIED','purchase_authorized':False}
    assert not data['deep_audit']['allowed']
    with storage.db() as connection:
        assert connection.execute('SELECT COUNT(*) FROM audits').fetchone()[0]==0
        assert connection.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0

def test_deep_audit_still_requires_allowlist(public_dns):
    response=TestClient(app).post('/api/audits',json={'product_url':URL})
    assert response.status_code==422 and 'allowlisted' in response.json()['detail']

def test_explicit_host_approval_only_enables_deep_action(public_dns,monkeypatch):
    stub_catalog(monkeypatch)
    monkeypatch.setenv('AUDIT_ALLOWED_HOSTS','retailer.example')
    response=TestClient(app).post('/api/channel3/discover',json={'url':URL})
    assert response.json()['deep_audit']['allowed']
    assert response.json()['verification']['purchase_authorized'] is False

@pytest.mark.parametrize('url',['http://retailer.example/product','https://user:password@retailer.example/product','https://localhost/product',
    'https://127.0.0.1/product','https://[::1]/product','https://169.254.169.254/latest','https://10.1.2.3/product','https://retailer.example:8443/product','file:///etc/passwd'])
def test_private_or_unsafe_urls_rejected_before_provider(public_dns,monkeypatch,url):
    async def never(*args,**kwargs): pytest.fail('Unsafe URL reached the provider')
    monkeypatch.setattr(Channel3Client,'lookup',never)
    assert TestClient(app).post('/api/channel3/discover',json={'url':url}).status_code==422

def test_dns_rebinding_to_private_address_is_rejected(monkeypatch):
    monkeypatch.setattr('backend.discovery.socket.getaddrinfo',lambda *args,**kwargs:[(2,1,6,'',('10.0.0.1',443))])
    with pytest.raises(ValueError): validate_public_product_url(URL)

def test_failed_lookup_never_invents_identity_or_offers(public_dns,monkeypatch):
    async def unsupported(*args): raise Channel3Error('PRODUCT_NOT_FOUND','Not in catalog',404)
    monkeypatch.setattr(Channel3Client,'lookup',unsupported)
    data=TestClient(app).post('/api/channel3/discover',json={'url':URL}).json()
    assert data['product'] is None and data['offers']==[] and data['provenance']['mode']=='UNAVAILABLE'
    assert data['verification']['identity']=='NOT VERIFIED' and data['decision']=='REVIEW'

def test_explicit_search_after_failed_lookup_is_live_and_unverified(public_dns,monkeypatch):
    async def unsupported(*args): raise Channel3Error('UPSTREAM','URL unsupported',422)
    async def search(*args): return {'products':[PRODUCT]},200
    monkeypatch.setattr(Channel3Client,'lookup',unsupported)
    monkeypatch.setattr(Channel3Client,'search',search)
    data=TestClient(app).post('/api/channel3/discover',json={'url':URL,'query':'adjustable laptop stand'}).json()
    assert data['product'] is None and data['offers'][0]['match']=='unverified'
    assert data['provenance']['mode']=='LIVE' and data['errors'][0]['http_status']==422

def test_discovery_is_not_a_payment_authorization(public_dns,monkeypatch):
    stub_catalog(monkeypatch)
    client=TestClient(app)
    discovery=client.post('/api/channel3/discover',json={'url':URL}).json()
    assert 'id' not in discovery
    response=client.post('/api/paypal/orders',json={'audit_id':'discovery','buyer_approved':True,'approved_total':54})
    assert response.status_code==404
