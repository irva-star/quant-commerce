import httpx
import pytest
from fastapi.testclient import TestClient
from backend.channel3 import Channel3Client,Channel3Error,compare,normalize
from backend.main import app
from backend.models import Mandate,Product
from backend.governance import market_matrix

PRODUCT={'id':'known-1','title':'Known Stand','materials':['Aluminium'],'key_features':['Adjustable height'],
    'offers':[{'url':'https://merchant.example/stand','domain':'merchant.example','price':{'price':54,'currency':'USD'},'condition':'new','availability':'InStock'}]}

def mock_post(monkeypatch,status=200,data=None,headers=None):
    monkeypatch.setattr('backend.discovery.socket.getaddrinfo',lambda *args,**kwargs:[(2,1,6,'',('93.184.216.34',443))])
    monkeypatch.setenv('CHANNEL3_API_KEY','unit-channel3-secret')
    async def post(self,url,**kwargs):
        assert url.startswith('https://api.trychannel3.com/v1/')
        assert kwargs['headers']['x-api-key']=='unit-channel3-secret'
        assert 'CHANNEL3_API_KEY' not in kwargs['json'] and 'x-api-key' not in kwargs['json']
        payload=data if data is not None else {'product':PRODUCT} if url.endswith('/lookup') else {'products':[PRODUCT]}
        return httpx.Response(status,json=payload,headers=headers,request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.AsyncClient,'post',post)

@pytest.mark.asyncio
async def test_documented_lookup_and_search_contract(monkeypatch):
    mock_post(monkeypatch)
    client=Channel3Client()
    lookup,status=await client.lookup('https://merchant.example/stand')
    search,status2=await client.search('aluminium laptop stand',12)
    assert status==status2==200
    offers=normalize(search,lookup)
    assert len(offers)==1 and offers[0].name=='Known Stand' and offers[0].price==54
    assert offers[0].currency=='USD' and offers[0].match=='identical' and not offers[0].synthetic

@pytest.mark.asyncio
@pytest.mark.parametrize('status,code',[(401,'AUTHENTICATION'),(403,'AUTHENTICATION'),(404,'PRODUCT_NOT_FOUND'),(429,'RATE_LIMIT'),(500,'UPSTREAM')])
async def test_actionable_sanitized_http_failures(monkeypatch,status,code):
    mock_post(monkeypatch,status,{'message':'unit-channel3-secret must not leak'},headers={'Retry-After':'30'})
    with pytest.raises(Channel3Error) as caught: await Channel3Client().search('stand')
    assert caught.value.code==code and caught.value.http_status==status
    assert 'unit-channel3-secret' not in str(caught.value.public())
    if status==429: assert caught.value.retry_after==30

@pytest.mark.asyncio
async def test_timeout_has_no_fake_results(monkeypatch):
    monkeypatch.setenv('CHANNEL3_API_KEY','unit')
    async def timeout(*args,**kwargs): raise httpx.ReadTimeout('private diagnostic')
    monkeypatch.setattr(httpx.AsyncClient,'post',timeout)
    with pytest.raises(Channel3Error) as caught: await Channel3Client().search('stand')
    assert caught.value.code=='TIMEOUT' and caught.value.http_status is None
    assert 'private diagnostic' not in caught.value.message

@pytest.mark.asyncio
async def test_empty_search_is_valid_live_response(monkeypatch):
    mock_post(monkeypatch,data={'products':[]})
    products,status=await Channel3Client().search('unfindable item')
    assert products=={'products':[]} and status==200

@pytest.mark.asyncio
async def test_missing_lookup_product_is_explicit(monkeypatch):
    mock_post(monkeypatch,data={'product':None})
    with pytest.raises(Channel3Error) as caught: await Channel3Client().lookup('https://merchant.example/not-found')
    assert caught.value.code=='PRODUCT_NOT_FOUND'

@pytest.mark.asyncio
async def test_external_lookup_resolves_title_before_comparable_search(monkeypatch):
    mock_post(monkeypatch)
    offers,status=await compare(Mandate(product_url='https://merchant.example/stand',market_mode='live'),'test')
    assert status['query']=='Known Stand' and status['lookup_http_status']==status['search_http_status']==200
    assert offers[0].match=='identical'

@pytest.mark.asyncio
async def test_local_fallback_is_labeled_mock_on_auth_failure(monkeypatch):
    mock_post(monkeypatch,status=401)
    offers,status=await compare(Mandate(product_url='http://127.0.0.1:8000/store/clean',market_mode='live'),'test')
    assert status['mode']=='SYNTHETIC_FALLBACK' and status['http_status']==401
    assert 'MOCK' in status['fallback_note'] and all(o.synthetic for o in offers)

def test_api_proxy_keeps_key_server_side(monkeypatch):
    mock_post(monkeypatch)
    client=TestClient(app)
    response=client.post('/api/channel3/search',json={'query':'stand'})
    assert response.status_code==200
    assert response.json()['channel3']['product_count']==1
    assert response.json()['channel3']['http_status']==200
    assert 'unit-channel3-secret' not in response.text
    response=client.post('/api/channel3/lookup',json={'url':'https://merchant.example/stand'})
    assert response.status_code==200 and response.json()['product']['title']=='Known Stand'

def test_rate_limit_propagates_safe_status_and_retry_header(monkeypatch):
    mock_post(monkeypatch,status=429,headers={'Retry-After':'17'})
    response=TestClient(app).post('/api/channel3/search',json={'query':'stand'})
    assert response.status_code==429 and response.headers['Retry-After']=='17'

def test_matrix_excludes_mixed_currency_and_unverified_prices():
    from backend.seeds import seed_offers,seed_product
    p=seed_product('clean','http://127.0.0.1:8000')
    offers=seed_offers('clean','http://127.0.0.1:8000')
    offers.append(offers[0].model_copy(update={'id':'eur','currency':'EUR','price':1}))
    offers.append(offers[0].model_copy(update={'id':'unknown','match':'unverified','price':1}))
    matrix=market_matrix(p,offers)
    assert matrix['median']==58 and matrix['original_price']==68
    assert matrix['price_difference_pct']==pytest.approx((68/58-1)*100)
    assert len(matrix['alternatives'])==2

def test_invalid_offer_does_not_discard_valid_rows():
    offers=normalize({'products':[{**PRODUCT,'offers':[{'url':'https://bad.example','price':{'price':'NaN'}},*PRODUCT['offers']]}]}, {})
    assert len(offers)==1 and offers[0].price==54
