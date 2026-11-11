import {test,expect} from '@playwright/test';

test('mocked PayPal redirect and return require buyer action before each payment step',async({page})=>{
  // This verifies the terminal protocol only. It never reaches a real PayPal API.
  let auditId='';
  let creates=0,captures=0;
  let providerApproved=false;
  const publicOrigin='http://127.0.0.1:5173';
  await page.route('**/api/health',async route=>{
    const response=await route.fetch();
    const health=await response.json();
    await route.fulfill({json:{...health,paypal_configured:true}});
  });
  await page.route('**/api/paypal/orders',async route=>{
    creates++;
    const body=route.request().postDataJSON();
    expect(body.buyer_approved).toBe(true);
    expect(body.approved_total).toBe(76);
    auditId=body.audit_id;
    await route.fulfill({json:{order_id:'MOCKORDER123',mode:'PAYPAL_SANDBOX',
      approval_url:'https://www.sandbox.paypal.com/checkoutnow?token=MOCKORDER123'}});
  });
  await page.route('**/api/paypal/checkout?**',route=>route.fulfill({json:auditId?{audit_id:auditId,order_id:'MOCKORDER123',amount:'76.00',currency:'USD',mode:'PAYPAL_SANDBOX',approval_url:'https://www.sandbox.paypal.com/checkoutnow?token=MOCKORDER123',paypal_status:providerApproved?'APPROVED':'PAYER_ACTION_REQUIRED',approval_verified:providerApproved,capture_completed:false,audit_expired:false,warning:null}:null}));
  await page.route('https://www.sandbox.paypal.com/**',route=>{
    providerApproved=true;
    return route.fulfill({contentType:'text/html',body:
      `<html><body><h1>Mock PayPal approval fixture</h1><a href="${publicOrigin}/?paypal=returned&audit=${auditId}&token=MOCKORDER123">Approve mock order</a></body></html>`});
  });
  await page.route('**/api/paypal/capture',async route=>{
    captures++;
    expect(route.request().postDataJSON()).toEqual({audit_id:auditId,buyer_approved:true,approved_total:76,order_id:'MOCKORDER123'});
    await route.fulfill({json:{status:'COMPLETED',order_id:'MOCKORDER123',mode:'PAYPAL_SANDBOX'}});
  });
  await page.goto('/?new=1');
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  await expect(page.getByRole('button',{name:'Pay with PayPal Sandbox'})).toBeDisabled();
  expect(creates).toBe(0);
  await page.getByRole('checkbox',{name:/I approve this audited purchase/}).check();
  await page.getByRole('button',{name:'Pay with PayPal Sandbox'}).click();
  await expect(page.getByRole('heading',{name:'Mock PayPal approval fixture'})).toBeVisible();
  expect(creates).toBe(1);
  expect(captures).toBe(0);
  await page.getByRole('link',{name:'Approve mock order'}).click();
  await expect(page.getByTestId('decision')).toHaveText('PASS');
  await expect(page.getByRole('button',{name:'Capture approved Sandbox order'})).toBeDisabled();
  expect(captures).toBe(0);
  await page.reload();
  await expect(page.getByRole('button',{name:'Capture approved Sandbox order'})).toBeDisabled();
  expect(creates).toBe(1);
  await page.getByRole('button',{name:'Product discovery',exact:true}).click();
  await expect(page.getByRole('button',{name:'Capture approved Sandbox order'})).toHaveCount(0);
  await page.getByRole('button',{name:'Audited checkout',exact:true}).click();
  await expect(page.getByRole('button',{name:'Capture approved Sandbox order'})).toBeDisabled();
  expect(creates).toBe(1);expect(captures).toBe(0);
  await page.getByRole('checkbox',{name:/I approve this audited purchase/}).check();
  await page.getByRole('button',{name:'Capture approved Sandbox order'}).click();
  await expect(page.getByRole('status')).toContainText('COMPLETED');
  expect(captures).toBe(1);
});

test('cancelled/token-only return and refresh recover the unpaid order without new audits or orders',async({page})=>{
  let auditId='',audits=0,creates=0,captures=0;
  page.on('request',request=>{if(request.method()==='POST'&&request.url().endsWith('/api/audits'))audits++});
  await page.route('**/api/paypal/orders',route=>{creates++;return route.fulfill({status:500,json:{detail:'Unexpected create'}})});
  await page.route('**/api/paypal/capture',route=>{captures++;return route.fulfill({status:500,json:{detail:'Unexpected capture'}})});
  await page.route('**/api/paypal/checkout?**',route=>route.fulfill({json:{audit_id:auditId,order_id:'MOCKORDER123',amount:'76.00',currency:'USD',mode:'PAYPAL_SANDBOX',approval_url:'https://www.sandbox.paypal.com/checkoutnow?token=MOCKORDER123',paypal_status:'PAYER_ACTION_REQUIRED',approval_verified:false,capture_completed:false,audit_expired:false,warning:null}}));
  const initial=page.waitForResponse(r=>r.url().endsWith('/api/audits')&&r.request().method()==='POST');
  await page.goto('/?new=1');
  auditId=(await (await initial).json()).id;
  await expect(page.getByTestId('decision')).toHaveText('PASS');
  await page.goto('/?paypal=cancelled&token=MOCKORDER123');
  await expect(page.getByTestId('checkout-recovery')).toContainText('PAYER_ACTION_REQUIRED');
  await expect(page.getByRole('button',{name:'Resume PayPal approval'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Capture approved Sandbox order'})).toHaveCount(0);
  await page.goto('/');
  await expect(page.getByTestId('checkout-recovery')).toContainText('Existing Sandbox checkout');
  await page.reload();
  await expect(page.getByTestId('checkout-recovery')).toContainText('PAYER_ACTION_REQUIRED');
  expect(audits).toBe(1);expect(creates).toBe(0);expect(captures).toBe(0);
});
