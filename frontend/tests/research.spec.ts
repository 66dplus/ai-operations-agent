import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
const assets=path.resolve('../docs/verification');

test.beforeEach(async({page})=>{
  // Offline acceptance must never dispatch a paid run, even when the UI regresses.
  await page.route('**/api/campaigns',async route=>{
    if(route.request().method()==='POST'&&route.request().postDataJSON().mode!=='demo'){
      await route.abort();expect(route.request().postDataJSON().mode).toBe('demo');return;
    }
    await route.continue();
  });
});

test('late live readiness preserves demo mode without a select change event',async({page})=>{
  let releaseHealth!:()=>void;
  const held=new Promise<void>(resolve=>{releaseHealth=resolve;});
  await page.route('**/api/health',async route=>{
    await held;await route.fulfill({json:{live_available:true}});
  });
  await page.goto('/');
  const mode=page.getByRole('combobox',{name:'Research mode'});
  await expect(mode).toHaveValue('demo');releaseHealth();
  await expect(mode.locator('option[value="live"]')).toBeEnabled();
  await expect(mode).toHaveValue('demo');
  await page.getByRole('textbox',{name:'Research request'}).fill('Find 5 European robotics companies for a delayed readiness test.');
  await page.getByRole('button',{name:'Start research →'}).click();
  await expect(page.getByText('DEMO · RESEARCH COMPLETE')).toBeVisible({timeout:30000});
  await expect(page.locator('tbody tr')).toHaveCount(5);
});

test('50-company research, evidence, edit, approval, rejection, export and refresh',async({page},testInfo)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Who are you looking for?'})).toBeVisible();
  await page.getByRole('combobox',{name:'Research mode'}).selectOption('demo');
  await page.getByRole('textbox',{name:'Research request'}).fill('Find 50 European robotics companies for simulation testing.');
  await page.screenshot({path:path.join(assets,testInfo.project.name+'-start.png')});
  await page.getByRole('button',{name:'Start research →'}).click();
  await expect(page.getByRole('button',{name:'Stop research'})).toBeVisible();
  await expect(page.getByText('DEMO · RESEARCH COMPLETE')).toBeVisible({timeout:30000});
  await expect(page.locator('tbody tr')).toHaveCount(50);
  await expect(page.getByRole('button',{name:'Qualified 40',exact:true})).toBeVisible();
  await page.screenshot({path:path.join(assets,testInfo.project.name+'-results.png')});
  await page.getByRole('button',{name:'Atlas Robotics',exact:true}).click();
  const drawer=page.getByRole('dialog',{name:'Review Atlas Robotics'});
  await expect(drawer.getByText('Synthetic demo company and source evidence')).toBeVisible();
  await expect(drawer.getByRole('blockquote')).toContainText('autonomous robots');
  await drawer.locator('summary').filter({hasText:'Source pages'}).click();
  await drawer.locator('summary').filter({hasText:'Atlas Robotics'}).click();
  await expect(drawer.locator('pre')).toContainText('Our autonomous robots adapt');
  const body='Hello Atlas team,\n\nWe help validate production scenarios in simulation.\nCould we discuss a pilot, next week?';
  await drawer.getByRole('textbox',{name:'Message',exact:true}).fill(body);
  await drawer.getByRole('button',{name:'Approve introduction',exact:true}).click();
  await expect(drawer.getByRole('button',{name:'Approved',exact:true})).toBeDisabled();
  await expect(drawer.getByText(/Approved revision 2/)).toBeVisible();
  await drawer.locator('summary').filter({hasText:'Source pages'}).click();
  await drawer.getByRole('heading',{name:'Atlas Robotics',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(assets,testInfo.project.name+'-review.png')});
  await drawer.getByRole('button',{name:'Close company details'}).click();
  await page.getByRole('button',{name:'Nordic Automation',exact:true}).click();
  await page.getByRole('button',{name:'Reject',exact:true}).click();
  await page.getByRole('button',{name:'Close company details'}).click();
  await expect(page.getByRole('button',{name:'Rejected',exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button',{name:'Approved 1',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Approved 1',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('link',{name:'Export approved ↓'}).click();
  const download=await downloadPromise;const csv=await readFile((await download.path())!,'utf8');
  expect(csv).toContain('approved_revision');expect(csv).toContain('Atlas Robotics');expect(csv).toContain(body.replaceAll('"','""'));expect(csv).not.toContain('Nordic Automation');
  const jsonPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Export JSON'}).click();
  const data=JSON.parse(await readFile((await (await jsonPromise).path())!,'utf8'));
  expect(data).toHaveLength(1);expect(data[0].body).toBe(body);expect(data[0].approved_revision).toBe(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('stop, refresh and retry unfinished research',async({page})=>{
  await page.goto('/');await page.getByRole('combobox',{name:'Research mode'}).selectOption('demo');await page.getByRole('textbox',{name:'Research request'}).fill('Find 50 European robotics companies for a restart test.');
  await page.getByRole('button',{name:'Start research →'}).click();
  await page.getByRole('button',{name:'Stop research'}).click();
  await expect(page.getByRole('button',{name:'Retry unfinished steps'})).toBeVisible();
  await page.reload();await expect(page.getByText('DEMO · CANCELLED')).toBeVisible();
  await page.getByRole('button',{name:'Retry unfinished steps'}).click();
  await expect(page.getByText('DEMO · RESEARCH COMPLETE')).toBeVisible({timeout:30000});
  await expect(page.locator('tbody tr')).toHaveCount(50);
});

test('lost create response can be retried without creating duplicate runs',async({page})=>{
  await page.goto('/');await page.getByRole('combobox',{name:'Research mode'}).selectOption('demo');const query='Find 5 European robotics companies response test '+crypto.randomUUID();
  await page.getByRole('textbox',{name:'Research request'}).fill(query);
  let lost=false;
  await page.route('**/api/campaigns',async route=>{
    if(route.request().method()==='POST'&&route.request().postDataJSON().mode!=='demo'){
      await route.abort();expect(route.request().postDataJSON().mode).toBe('demo');return;
    }
    if(route.request().method()==='POST'&&!lost){lost=true;await route.fetch();await route.abort('connectionreset');}
    else await route.continue();
  });
  await page.getByRole('button',{name:'Start research →'}).click();
  await expect(page.locator('main').getByRole('alert')).toBeVisible();
  await page.getByRole('button',{name:'Start research →'}).click();
  await expect(page.getByText('DEMO · RESEARCH COMPLETE')).toBeVisible({timeout:30000});
  const history=await (await page.request.get('/api/campaigns')).json();
  expect(history.filter((x:{query:string})=>x.query===query)).toHaveLength(1);
});
