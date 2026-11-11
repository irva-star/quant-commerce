import {test,expect} from '@playwright/test';

const url='https://unapproved-retailer.example/products/stand';
function result(allowed=false){return {
  kind:'DISCOVERY',decision:'REVIEW',input_url:url,
  product:{id:'catalog-123',title:'Catalog stand',materials:['Aluminium'],key_features:['Adjustable height']},products:[],
  offers:[{id:'offer-1',name:'Catalog stand',merchant:'unapproved-retailer.example',url,price:'54.00',currency:'CAD',match:'identical',match_reason:'Same canonical catalog product',synthetic:false,specifications:{condition:'new'}}],
  verification:{identity:'RESOLVED',checkout:'NOT VERIFIED',carbon:'NOT VERIFIED',purchase_authorized:false},
  provenance:{mode:'LIVE',provider:'Channel3',captured_at:new Date().toISOString(),synthetic:false,sources:[{operation:'Lookup',http_status:200,source:'https://channel3.ai/docs/guides/url-lookup'}]},
  deep_audit:{allowed,reason:allowed?'Host explicitly approved.':'Host not approved for browser access.'},errors:[],
}}

test('public URL discovery shows live identity and offers without audit/payment authority',async({page})=>{
  let audits=0,payments=0;
  page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/audits'))audits++;if(request.method()==='POST'&&/\/api\/paypal\/(orders|capture)$/.test(request.url()))payments++});
  await page.route('**/api/channel3/discover',route=>{
    expect(route.request().postDataJSON().url).toBe(url);
    expect(route.request().headers()['x-api-key']).toBeUndefined();
    return route.fulfill({json:result()});
  });
  await page.goto('/?discover='+encodeURIComponent(url));
  await expect(page.getByRole('heading',{name:'Catalog stand'})).toBeVisible();
  await expect(page.getByText('54.00 CAD',{exact:true})).toBeVisible();
  await expect(page.getByText('NOT VERIFIED',{exact:true})).toHaveCount(2);
  await expect(page.getByText('REVIEW',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Deep Storefront Audit'})).toBeDisabled();
  await expect(page.getByRole('button',{name:/Pay with PayPal|Capture approved|Simulate settlement/})).toHaveCount(0);
  expect(audits).toBe(0);expect(payments).toBe(0);
});

test('deep browser audit requires a separate explicit action on an approved host',async({page})=>{
  let audits=0;
  await page.route('**/api/channel3/discover',route=>route.fulfill({json:result(true)}));
  await page.route('**/api/audits',route=>{
    if(route.request().method()!=='POST')return route.continue();
    audits++;expect(route.request().postDataJSON().product_url).toBe(url);
    return route.fulfill({status:422,json:{detail:'Test fixture: missing checkout evidence'}});
  });
  await page.goto('/?discover='+encodeURIComponent(url));
  await expect(page.getByRole('button',{name:'Deep Storefront Audit'})).toBeEnabled();
  expect(audits).toBe(0);
  await page.getByRole('button',{name:'Deep Storefront Audit'}).click();
  await expect(page.getByRole('alert')).toContainText('missing checkout evidence');
  expect(audits).toBe(1);
});

test('unsupported catalog URL remains unverified and never substitutes synthetic evidence',async({page})=>{
  const unavailable={...result(),product:null,offers:[],provenance:{...result().provenance,mode:'UNAVAILABLE',sources:[]},
    errors:[{operation:'Lookup',error_code:'PRODUCT_NOT_FOUND',detail:'No supported catalog product',http_status:404}]};
  await page.route('**/api/channel3/discover',route=>route.fulfill({json:unavailable}));
  await page.goto('/?discover='+encodeURIComponent(url));
  await expect(page.getByRole('heading',{name:'Product identity NOT VERIFIED'})).toBeVisible();
  await expect(page.getByText('No supported catalog product',{exact:true})).toBeVisible();
  await expect(page.getByText('REVIEW',{exact:true})).toBeVisible();
  await expect(page.getByTestId('decision')).toHaveCount(0);
});

test('the main URL entry routes public products to discovery instead of Playwright',async({page})=>{
  let audits=0;
  page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/audits'))audits++});
  await page.route('**/api/channel3/discover',route=>route.fulfill({json:result()}));
  await page.goto('/?new=1');
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  expect(audits).toBe(1);
  await page.getByRole('textbox',{name:'Product URL',exact:true}).fill(url);
  await page.getByRole('button',{name:/^Discover product/}).click();
  await expect(page.getByRole('heading',{name:'Catalog stand'})).toBeVisible();
  expect(audits).toBe(1);
});
