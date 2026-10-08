import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
const id=process.env.LIVE_CAMPAIGN_ID;
const mirBody='Hello MiR team,\n\nI read that MiR Fleet manages large, mixed AMR fleets in active production environments.\n\nI offer simulation testing tools for robotics teams. Would you be open to a short conversation about testing deployment scenarios for your AMR fleets?\n\nBest regards,\n[Your name]';
test('existing live50 evidence, preserved approval, review and exact export',async({page},info)=>{
 test.skip(!id,'Opt-in existing live acceptance dataset; never creates paid research.');
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');
 await page.locator('summary').filter({hasText:'Recent runs'}).click();
 await page.getByRole('button',{name:'Global Robotics & Automation Hardware Companies (Simulation Testing Tools Fit) completed · 50 companies',exact:true}).click();
 await expect(page.locator('details.history')).not.toHaveAttribute('open');
 await expect(page.getByText('RESEARCH COMPLETE',{exact:true})).toBeVisible();
 await expect(page.locator('tbody tr')).toHaveCount(50);
 const snapshot=await (await page.request.get('/api/campaigns/'+id)).json();
 expect(snapshot.counts.processed).toBe(50);expect(snapshot.counts.failed).toBe(0);
 for(const lead of snapshot.leads){
  expect(lead.sources.length).toBeGreaterThan(0);expect(lead.qualification.evidence.length).toBeGreaterThan(0);
  for(const ev of lead.qualification.evidence){
   const source=lead.sources.find((s:{id:string})=>s.id===ev.source_id);
   expect(source).toBeDefined();
   expect(source.content.replace(/\s+/g,' ')).toContain(ev.quote.replace(/\s+/g,' '));
  }
 }
 await page.screenshot({path:path.resolve('../docs/verification/live-'+info.project.name+'-results.png')});
 await page.getByRole('button',{name:'Mobile Industrial Robots (MiR)',exact:true}).click();
 const drawer=page.getByRole('dialog');
 await expect(drawer.getByText(/Approved revision 2/)).toBeVisible();
 await expect(drawer.getByRole('textbox',{name:'Message',exact:true})).toHaveValue(mirBody);
 await expect(drawer.getByRole('blockquote')).not.toHaveCount(0);
 await page.screenshot({path:path.resolve('../docs/verification/live-'+info.project.name+'-review.png')});
 await page.getByRole('button',{name:'Close company details'}).click();
 await page.getByRole('button',{name:'FANUC America',exact:true}).click();
 const humanBody='Hello FANUC team,\n\nI read about your industrial and collaborative robots. I offer simulation testing tools for robotics teams. Would you be open to discussing tests for deployment scenarios?\n\nBest regards,\n[Your name]';
 await page.getByRole('textbox',{name:'Message',exact:true}).fill(humanBody);
 const approve=page.getByRole('button',{name:'Approve introduction',exact:true});
 if(await approve.count())await approve.click();
 await expect(page.getByRole('dialog').getByRole('button',{name:'Approved',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Close company details'}).click();
 await page.getByRole('button',{name:'Savant Automation',exact:true}).click();
 await page.getByRole('button',{name:'Reject',exact:true}).click();
 await page.getByRole('button',{name:'Close company details'}).click();
 await page.reload();await expect(page.getByRole('button',{name:'Approved 2',exact:true})).toBeVisible();
 const csvPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Export approved ↓'}).click();
 const csv=await readFile((await (await csvPromise).path())!,'utf8');expect(csv).toContain(mirBody);expect(csv).toContain(humanBody);expect(csv).not.toContain('Savant Automation');
 const jsonPromise=page.waitForEvent('download');await page.getByRole('link',{name:'Export JSON'}).click();
 const exported=JSON.parse(await readFile((await (await jsonPromise).path())!,'utf8'));expect(exported).toHaveLength(2);
 const mir=exported.find((x:{company:string})=>x.company==='Mobile Industrial Robots (MiR)');
 expect(mir.approved_revision).toBe(2);expect(mir.body).toBe(mirBody);
 if(snapshot.budget.limits_enabled&&(snapshot.budget.firecrawl_credits>=snapshot.budget.max_firecrawl_credits||snapshot.budget.model_calls>=snapshot.budget.max_model_calls)){
  const before=await (await page.request.get('/api/campaigns')).json();
  await page.getByRole('button',{name:'New research',exact:true}).click();
  await page.getByRole('combobox',{name:'Research mode'}).selectOption('live');
  await page.getByRole('textbox',{name:'Research request'}).fill('Find 5 robotics companies for an exhausted budget check.');
  await page.getByRole('button',{name:'Start research →'}).click();
  await expect(page.locator('main').getByRole('alert')).toContainText('budget is exhausted');
  const after=await (await page.request.get('/api/campaigns')).json();
  expect(after.length).toBe(before.length);
  const preserved=await (await page.request.get('/api/campaigns/'+id)).json();
  expect(preserved.budget).toEqual(snapshot.budget);
 }
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);expect(errors).toEqual([]);
});
