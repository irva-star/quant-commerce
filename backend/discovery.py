"""Catalog research only. Never runs a browser, governance, carbon or payment code."""
import asyncio
import ipaddress
import socket
from datetime import datetime,timezone
from urllib.parse import urlparse
from .channel3 import Channel3Client,Channel3Error,normalize,DOCS
from .config import setting

def validate_public_product_url(url: str):
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Discovery requires a public HTTPS product URL without credentials or a custom port.')
    if parsed.hostname=='localhost' or parsed.hostname.endswith(('.localhost','.local','.internal')):
        raise ValueError('Local hostnames are not permitted for public discovery.')
    try: literal=ipaddress.ip_address(parsed.hostname)
    except ValueError: literal=None
    if literal is not None and not literal.is_global:
        raise ValueError('Private and reserved IP addresses are not permitted for public discovery.')
    try: addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    except OSError: raise ValueError('Product hostname could not be resolved. No provider request was sent.') from None
    if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
        raise ValueError('Private, loopback, link-local and reserved destinations are not permitted for public discovery.')

def deep_audit_allowed(url: str):
    allowed={host.strip().lower() for host in setting('AUDIT_ALLOWED_HOSTS').split(',') if host.strip()}
    return urlparse(url).hostname in allowed

async def discover(url: str,query: str='',limit: int=12):
    await asyncio.to_thread(validate_public_product_url,url)
    client=Channel3Client()
    lookup,search={},{}
    sources=[]
    errors=[]
    try:
        lookup,status=await client.lookup(url)
        if not lookup['product'].get('id') or not lookup['product'].get('title'):
            lookup={}
            raise Channel3Error('INVALID_RESPONSE','Lookup did not supply a canonical ID and title; identity remains unverified.',status)
        sources.append({'operation':'Lookup','http_status':status,'source':'https://channel3.ai/docs/guides/url-lookup'})
    except Channel3Error as error:
        errors.append({'operation':'Lookup',**error.public()})
    title=(lookup.get('product') or {}).get('title')
    search_query=query.strip() or title
    # An explicit query or actual resolved title can drive search; identity is never invented.
    if search_query and (lookup or not errors or errors[0]['error_code']=='PRODUCT_NOT_FOUND' or errors[0]['http_status'] in (400,404,422)):
        try:
            search,status=await client.search(search_query,limit)
            sources.append({'operation':'Search','http_status':status,'source':DOCS})
        except Channel3Error as error:
            errors.append({'operation':'Search',**error.public()})
    offers=normalize(search,lookup)
    return {
        'kind':'DISCOVERY','decision':'REVIEW','input_url':url,
        'product':lookup.get('product'),'products':search.get('products',[]),
        'offers':[offer.model_dump(mode='json') for offer in offers],
        'verification':{'identity':'RESOLVED' if lookup.get('product') else 'NOT VERIFIED',
            'checkout':'NOT VERIFIED','carbon':'NOT VERIFIED','purchase_authorized':False},
        'provenance':{'mode':'LIVE' if sources else 'UNAVAILABLE','captured_at':datetime.now(timezone.utc).isoformat(),
            'provider':'Channel3','sources':sources,'synthetic':False},
        'deep_audit':{'allowed':deep_audit_allowed(url),'reason':'Browser access is approved for this host.' if deep_audit_allowed(url) else 'This host is not approved in AUDIT_ALLOWED_HOSTS. Catalog discovery does not require browser approval.'},
        'errors':errors,
    }
