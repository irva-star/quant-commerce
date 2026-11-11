import { test, expect } from '@playwright/test';

test('clean purchase, evidence export, budget block and synthetic offer re-audit',async({page})=>{
  const errors:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/?new=1');
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  await expect(page.getByRole('heading',{name:'Arc / Precision Desk Stand'})).toBeVisible();
  await expect(page.getByRole('button',{name:/Pay with PayPal/})).toBeDisabled();
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export audit'}).click();
  const download=await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^qct-audit-/);
  await page.getByRole('button',{name:/Source evidence/}).click();
  await expect(page.getByRole('heading',{name:'Source evidence explorer'})).toBeVisible();
  await expect(page.locator('.provenance-details')).toContainText('PLAYWRIGHT_DOM');
  await page.getByRole('button',{name:'Audit overview'}).click();
  await page.getByRole('spinbutton',{name:'Maximum total spend'}).fill('60');
  await expect(page.getByTestId('decision')).toHaveText('RE-AUDIT');
  await page.getByRole('button',{name:'Apply mandate & re-audit'}).click();
  await expect(page.getByTestId('decision')).toHaveText('BLOCK',{timeout:60_000});
  await expect(page.getByText('FIAT CAP',{exact:true})).toBeVisible();
  await page.getByRole('spinbutton',{name:'Maximum total spend'}).fill('100');
  await page.getByRole('button',{name:'Apply mandate & re-audit'}).click();
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  await page.getByRole('button',{name:/Re-audit/}).first().click();
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  await expect(page.getByRole('textbox',{name:'Product URL'})).toHaveValue(/offer=north/);
  await expect(page.locator('.product-strip')).toContainText('Northline / Synthetic Offer');
  await page.getByRole('checkbox',{name:/I approve this audited purchase/}).check();
  await expect(page.getByRole('button',{name:/Pay with PayPal/})).toBeDisabled();
  expect(errors).toEqual([]);
});

test('anchor scenario measures cookie delta and blocks fees and subscriptions',async({page})=>{
  await page.goto('/?new=1');
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  await page.getByRole('button',{name:'Anchor + drip pricing'}).click();
  await expect(page.getByTestId('decision')).toHaveText('BLOCK',{timeout:60_000});
  for(const finding of ['ANCHOR','FEES','SUBSCRIPTION','PERSONA DELTA'])await expect(page.getByText(finding,{exact:true})).toBeVisible();
  await expect(page.getByText('+$12.00',{exact:true})).toBeVisible();
  await expect(page.getByRole('checkbox',{name:/I approve this audited purchase/})).toBeDisabled();
});

test('offset does not clear strict carbon cap; explicit reviewable exception is recorded',async({page})=>{
  await page.goto('/?new=1');
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  await page.getByRole('button',{name:'Carbon cap violation'}).click();
  await expect(page.getByTestId('decision')).toHaveText('BLOCK',{timeout:60_000});
  await page.getByRole('checkbox',{name:/Carbon contribution/}).check();
  await page.getByRole('button',{name:'Apply mandate & re-audit'}).click();
  await expect(page.getByTestId('decision')).toHaveText('BLOCK',{timeout:60_000});
  await expect(page.getByText('PURCHASE CARBON',{exact:true})).toBeVisible();
  await page.getByLabel('Carbon override policy').selectOption('reviewable_carbon');
  await page.getByRole('checkbox',{name:/I explicitly accept exceeding/}).check();
  await page.getByRole('textbox',{name:'Override reason'}).fill('Demo buyer accepts this disclosed carbon exception.');
  await page.getByRole('button',{name:'Apply mandate & re-audit'}).click();
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  await expect(page.getByRole('button',{name:/Simulate settlement/})).toBeDisabled();
});

test('mobile layout has no document overflow and exposes mandate controls',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/?new=1');
  await expect(page.getByTestId('decision')).toHaveText('PASS',{timeout:60_000});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  expect(overflow).toBe(false);
  await expect(page.getByRole('spinbutton',{name:'Maximum total spend'})).toBeVisible();
});
