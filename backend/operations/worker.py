import logging
import os
import threading
import time
from uuid import uuid4
from psycopg.types.json import Jsonb
from . import db, demo, queue, service
from .schemas import ResearchResult

logger=logging.getLogger('operations.worker')


def run_job(job):
    with db.connect() as c:
        ca=c.execute('SELECT * FROM campaigns WHERE id=%s',(job['campaign_id'],)).fetchone()
    if ca['mode']=='live':
        from .agent import run_live_job
        return run_live_job(job,ca)
    if job['kind']=='plan':
        if not ca['criteria']:
            definition=demo.plan(ca['query'],ca['target_count'])
            with db.connect() as c:
                db.require_lease(c,job['id'],job['lease_version'],lock=True)
                c.execute('UPDATE campaigns SET criteria=%s WHERE id=%s',(Jsonb(definition.model_dump()),ca['id']))
                db.enqueue(c,ca['id'],'discovery','discovery')
        return
    if job['kind']=='discovery':
        persist_discovery(job,demo.candidates(ca['target_count']))
        return
    if job['kind']=='research':
        for lead_id in job['payload']['lead_ids']:
            with db.connect() as c:
                lead=c.execute('SELECT * FROM leads WHERE id=%s',(lead_id,)).fetchone()
                if lead['qualification']:
                    continue
                source=c.execute('SELECT * FROM sources WHERE lead_id=%s LIMIT 1',(lead_id,)).fetchone()
                if not source:
                    page=demo.page(lead)
                    source=service.add_source(c,job,lead_id,page['url'],page['title'],page['content'])
            with db.connect() as c:
                service.save_result(c,job,demo.research(lead,source))
            time.sleep(float(os.getenv('DEMO_STEP_DELAY','0.05')))
        return
    raise ValueError('Unknown queue job kind.')


def persist_discovery(job,companies):
    with db.connect() as c:
        db.require_lease(c,job['id'],job['lease_version'],lock=True)
        ca=c.execute('SELECT * FROM campaigns WHERE id=%s',(job['campaign_id'],)).fetchone()
        count=c.execute('SELECT count(*) AS n FROM leads WHERE campaign_id=%s',(ca['id'],)).fetchone()['n']
        for company in companies:
            if count >= ca['target_count']:
                break
            try:
                domain=service.normalized_domain(company['url'])
            except ValueError:
                db.log(c,ca['id'],'discovery','skipped','A search candidate has no valid company domain.',job_id=job['id'])
                continue
            inserted=c.execute('INSERT INTO leads(id,campaign_id,company_name,domain) VALUES (%s,%s,%s,%s) ON CONFLICT(campaign_id,domain) DO NOTHING RETURNING id', (uuid4(),ca['id'],company['company_name'],domain)).fetchone()
            count += bool(inserted)
        leads=c.execute('SELECT id FROM leads WHERE campaign_id=%s ORDER BY domain LIMIT %s',(ca['id'],ca['target_count'])).fetchall()
        pilot = ca['mode']=='live' and len(leads)>5
        if pilot:
            budget=c.execute('SELECT * FROM budget WHERE name=%s',(db.settings.budget_scope,)).fetchone()
            c.execute("INSERT INTO step_outputs(campaign_id,step,output) VALUES (%s,'pilot_budget',%s) ON CONFLICT DO NOTHING",(ca['id'],Jsonb(budget)))
            c.execute("UPDATE campaigns SET live_phase='pilot' WHERE id=%s",(ca['id'],))
        for i in range(0,min(5,len(leads)) if pilot else len(leads),5):
            db.enqueue(c,ca['id'],'research',str(i//5),{'lead_ids':[str(x['id']) for x in leads[i:i+5]]})
        db.log(c,ca['id'],'discovery','completed',f'{len(leads)} unique companies found.',job_id=job['id'])


def execute(job):
    stop=threading.Event()
    def renew():
        while not stop.wait(max(1, min(10, db.settings.lease_seconds/3))):
            try:
                if not queue.heartbeat(job):
                    return
            except Exception:
                logger.exception('Task heartbeat failed; persisted lease still fences commits.')
                return
    heart=threading.Thread(target=renew,daemon=True)
    heart.start()
    try:
        run_job(job)
        queue.finish(job)
    except db.LostLease:
        logger.info('Abandoned stale or cancelled task %s',job['id'])
    except Exception as error:
        # Provider exceptions declare their retry policy. Validation errors are permanent.
        queue.fail(job,error,retryable=getattr(error,'retryable',False))
        logger.warning('Task %s failed: %s',job['id'],type(error).__name__)
    finally:
        stop.set();heart.join(timeout=2)


def main():
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    db.migrate()
    worker_id=str(uuid4())
    while True:
        job=queue.claim(worker_id)
        if job:
            execute(job)
        else:
            time.sleep(0.5)

if __name__=='__main__':
    main()
