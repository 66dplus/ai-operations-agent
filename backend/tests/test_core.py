import csv
import io
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from operations import api, db, demo, queue, service, worker
from operations.schemas import CampaignCreate, DraftEdit, Review


def campaign(n=5,key=None):
    return service.create_campaign(CampaignCreate(query=f'Find {n} European robotics companies',mode='demo'),key or str(uuid4()))


def test_history_keeps_older_runs_accessible_after_thirty_new_runs():
    oldest=campaign()
    for _ in range(30):campaign()
    with TestClient(api.app) as client:
        history=client.get('/api/campaigns').json()
        assert len(history)==31 and str(oldest['id']) in {run['id'] for run in history}
        assert client.get('/api/campaigns/'+str(oldest['id'])).status_code==200


def drain():
    while job:=queue.claim('test-worker'):
        worker.execute(job)


def research_job(n=5):
    ca=campaign(n)
    for _ in range(2):
        job=queue.claim('setup');worker.execute(job)
    return ca,queue.claim('researcher')


def first_result(job):
    with db.connect() as c:
        lead=c.execute('SELECT * FROM leads WHERE id=%s',(job['payload']['lead_ids'][0],)).fetchone()
        page=demo.page(lead)
        source=service.add_source(c,job,lead['id'],**page)
    return lead,source,demo.research(lead,source)


def test_full_offline_50_review_export_and_retry_preserves_approval():
    ca=campaign(50);drain()
    snap=service.snapshot(ca['id'])
    assert snap['campaign']['status']=='completed'
    assert snap['counts']=={'discovered':50,'processed':50,'qualified':40,'approved':0,'failed':0}
    assert snap['budget']['model_calls']==snap['budget']['firecrawl_credits']==0
    lead=next(x for x in snap['leads'] if x['current_revision'])
    edited=DraftEdit(subject='Partnership, simulation',body='Hello team,\n\nA reviewed message with commas, and newlines.',expected_revision=1)
    assert service.edit_draft(lead['id'],edited)['revision']==2
    with pytest.raises(HTTPException) as err:
        service.review_draft(lead['id'],Review(revision=1,decision='approved'))
    assert err.value.status_code==409
    service.review_draft(lead['id'],Review(revision=2,decision='approved'))
    rows=service.export_rows(ca['id']);assert len(rows)==1
    assert rows[0]['body']==edited.body and rows[0]['approved_revision']==2
    decoded=list(csv.DictReader(io.StringIO(service.csv_export(rows).lstrip('\ufeff'))))
    assert decoded[0]['body']==edited.body
    service.cancel_campaign(ca['id'])
    # Replaying already-committed research cannot replace human decisions.
    with db.connect() as c:
        c.execute("UPDATE jobs SET status='failed' WHERE campaign_id=%s AND kind='research'",(ca['id'],))
    service.retry_campaign(ca['id']);drain()
    assert service.export_rows(ca['id'])==rows
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM drafts WHERE lead_id=%s',(lead['id'],)).fetchone()['n']==2
    service.edit_draft(lead['id'],DraftEdit(subject='New',body='New reviewed body',expected_revision=2))
    assert service.export_rows(ca['id'])==[]


def test_two_workers_claim_once_and_expired_worker_cannot_commit():
    ca,job=research_job(10)
    with ThreadPoolExecutor(2) as pool:
        claims=list(pool.map(queue.claim,['worker-a','worker-b']))
    claims=[j for j in claims if j]
    assert len(claims)==1 and claims[0]['id']!=job['id']
    lead,source,result=first_result(job)
    with db.connect() as c:
        c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(job['id'],))
    successor=queue.claim('successor')
    assert successor['id']==job['id'] and successor['lease_version']>job['lease_version']
    assert not queue.heartbeat(job)
    with pytest.raises(db.LostLease),db.connect() as c:
        service.save_result(c,job,result)
    with pytest.raises(db.LostLease),db.connect() as c:
        db.authorize_capability(c,job['capability'])
    worker.execute(successor);worker.execute(claims[0])
    assert service.snapshot(ca['id'])['counts']['processed']==10


def test_committed_partial_batch_restarts_without_researching_success():
    ca,job=research_job()
    lead,source,result=first_result(job)
    with db.connect() as c:
        service.save_result(c,job,result)
        c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(job['id'],))
    successor=queue.claim('restarted');worker.execute(successor)
    snap=service.snapshot(ca['id'])
    assert snap['campaign']['status']=='completed' and snap['counts']['processed']==5
    with db.connect() as c:
        assert c.execute('SELECT count(*) AS n FROM sources WHERE lead_id=%s',(lead['id'],)).fetchone()['n']==1
        assert c.execute('SELECT count(*) AS n FROM run_logs WHERE lead_id=%s AND step=%s',(lead['id'],'qualification')).fetchone()['n']==1


def test_crash_attempts_are_finite():
    ca=campaign()
    for attempt in range(1,4):
        job=queue.claim('crash');assert job['attempts']==attempt
        with db.connect() as c:
            c.execute("UPDATE jobs SET lease_until=now()-interval '1 second' WHERE id=%s",(job['id'],))
    assert queue.claim('after-crashes') is None
    snap=service.snapshot(ca['id']);assert snap['campaign']['status']=='partial'
    assert '0 of 5' in snap['campaign']['error']


def test_concurrent_budget_reservations_never_exceed_limit(database):
    with db.connect() as c:
        c.execute("UPDATE budget SET model_calls=99,firecrawl_credits=249 WHERE name='test'")
    def spend(provider):
        try:
            with db.connect() as c:
                db.reserve(c,provider,1)
            return True
        except db.BudgetExhausted:
            return False
    with ThreadPoolExecutor(8) as pool:
        assert sum(pool.map(spend,['model']*8))==1
        assert sum(pool.map(spend,['firecrawl']*8))==1
    with db.connect() as c:
        row=c.execute("SELECT * FROM budget WHERE name='test'").fetchone()
        assert row['model_calls']==100 and row['firecrawl_credits']==250
        # A crash/unknown outcome retains its reservation, never assumed refunded.
        assert c.execute("SELECT count(*) AS n FROM provider_requests WHERE status='reserved'").fetchone()['n']==2


def test_evidence_cross_lead_and_quote_validation_and_immutable_snapshot():
    ca,job=research_job()
    lead,source,result=first_result(job)
    other=job['payload']['lead_ids'][1]
    invalid=result.model_copy(deep=True);invalid.lead_id=other
    with pytest.raises(ValueError,match='stored source'),db.connect() as c:
        service.save_result(c,job,invalid)
    invalid=result.model_copy(deep=True);invalid.qualification.evidence[0].quote='Invented quote that never appeared on this website.'
    with pytest.raises(ValueError,match='stored source'),db.connect() as c:
        service.save_result(c,job,invalid)
    with db.connect() as c:
        service.save_result(c,job,result)
        reused=service.add_source(c,job,lead['id'],source['url'],'Changed','Different content')
        assert reused['content_hash']==source['content_hash']
    assert service.snapshot(ca['id'])['counts']['processed']==1


def test_dedup_idempotency_and_invalid_candidate_does_not_break_pipeline():
    key=str(uuid4())
    with ThreadPoolExecutor(4) as pool:
        created=list(pool.map(lambda _:campaign(5,key),range(4)))
    assert len({x['id'] for x in created})==1
    with pytest.raises(HTTPException) as err:
        campaign(10,key)
    assert err.value.status_code==409
    job=queue.claim('planner');worker.execute(job);job=queue.claim('discoverer')
    companies=demo.candidates(5)
    worker.persist_discovery(job,[{'company_name':'Bad','url':'file:///private/data'}]+companies+companies)
    queue.finish(job);drain()
    assert service.snapshot(created[0]['id'])['counts']['discovered']==5
    assert service.normalized_domain('https://WWW.München.de/path')=='xn--mnchen-3ya.de'


def test_cancel_fences_capability_and_retry_only_unfinished():
    ca,job=research_job();lead,source,result=first_result(job)
    with db.connect() as c:service.save_result(c,job,result)
    service.cancel_campaign(ca['id'])
    with pytest.raises(db.LostLease),db.connect() as c:db.authorize_capability(c,job['capability'])
    with pytest.raises(db.LostLease):queue.finish(job)
    service.retry_campaign(ca['id']);drain()
    assert service.snapshot(ca['id'])['campaign']['status']=='completed'


def test_user_api_origin_agent_denial_and_request_readback():
    with TestClient(api.app) as client:
        payload={'query':'Find 5 European robotics companies','mode':'demo'}
        headers={'Idempotency-Key':str(uuid4())}
        assert client.post('/api/campaigns',json=payload,headers=headers).status_code==403
        headers['Origin']='https://untrusted.example'
        assert client.post('/api/campaigns',json=payload,headers=headers).status_code==403
        headers['Origin']='http://localhost:3000'
        created=client.post('/api/campaigns',json=payload,headers=headers);assert created.status_code==201
        cid=created.json()['id'];drain()
        read=client.get('/api/campaigns/'+cid);assert read.json()['counts']['processed']==5
        lead=next(l for l in read.json()['leads'] if l['current_revision'])
        route='/api/leads/'+lead['id']+'/review'
        assert client.post(route,json={'revision':1,'decision':'approved'},headers={**headers,'Authorization':'Bearer agent'}).status_code==403
        assert client.post(route,json={'revision':1,'decision':'approved'},headers=headers).status_code==200
        assert len(client.get('/api/campaigns/'+cid+'/export?format=json').json())==1
        assert client.post('/api/campaigns',json={'query':'Find 51 robotics companies'},headers=headers).status_code==422
        assert client.get('/api/campaigns/'+cid+'/export?format=exe').status_code==422


def test_two_final_workers_settle_campaign_after_concurrent_completion():
    from threading import Barrier
    ca,first=research_job(10)
    second=queue.claim('second')
    for job in (first,second):
        worker.run_job(job)
    barrier=Barrier(2)
    def finish_together(job):
        barrier.wait(timeout=5)
        queue.finish(job)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(finish_together,[first,second]))
    snap=service.snapshot(ca['id'])
    assert snap['campaign']['status']=='completed' and snap['counts']['processed']==10


def test_live_is_not_advertised_by_flags_without_verified_adapter(monkeypatch,database):
    from dataclasses import replace
    from operations import config
    enabled=replace(database,live_enabled=True,go_balance_disabled=True)
    for module in (config,service,api):monkeypatch.setattr(module,'settings',enabled)
    assert not api.health()['live_available']
    with pytest.raises(HTTPException) as err:
        service.create_campaign(CampaignCreate(query='Find 5 robotics companies',mode='live'),str(uuid4()))
    assert err.value.status_code==503


def test_csv_formula_cells_are_inert():
    encoded=service.csv_export([dict(company='=HYPERLINK("bad")',domain='safe.example',industry='Robotics',score=80,reasons='verified',sources='https://safe.example',subject=' +SUM(1,1)',body='@risk',approved_revision=2)])
    row=next(csv.DictReader(io.StringIO(encoded.lstrip('\ufeff'))))
    assert row['company'].startswith("'=") and row['subject'].startswith("' +") and row['body']=="'@risk"


def test_transient_failure_retries_three_times_and_permanent_failure_is_explicit():
    ca=campaign(5)
    for attempt in range(1,4):
        job=queue.claim('retry-worker');assert job['attempts']==attempt
        queue.fail(job,TimeoutError('Provider timeout'),retryable=True)
        with db.connect() as c:
            c.execute('UPDATE jobs SET available_at=now() WHERE id=%s',(job['id'],))
    assert queue.claim('extra') is None
    snap=service.snapshot(ca['id'])
    assert snap['campaign']['status']=='partial'
    assert len([x for x in snap['logs'] if x['status']=='retrying'])==2
    ca,job=research_job()
    queue.fail(job,ValueError('Stored evidence unavailable'),retryable=False)
    snap=service.snapshot(ca['id'])
    assert snap['counts']['failed']==5
    assert all(x['error']=='Stored evidence unavailable' for x in snap['leads'])


def test_exhausted_budget_stops_campaign_and_cannot_be_replenished_by_retry():
    ca,job=research_job()
    queue.fail(job,db.BudgetExhausted('model budget exhausted; no request was sent.'))
    snap=service.snapshot(ca['id'])
    assert snap['campaign']['status']=='budget_exhausted'
    assert queue.claim('late') is None
    with pytest.raises(HTTPException) as err:service.retry_campaign(ca['id'])
    assert err.value.status_code==409


def test_structured_schema_rejects_missing_evidence_and_unknown_fields():
    from pydantic import ValidationError
    from operations.schemas import ResearchResult
    _,job=research_job();_,_,result=first_result(job)
    data=result.model_dump(mode='json');data['qualification']['evidence']=[]
    with pytest.raises(ValidationError):ResearchResult.model_validate(data)
    data=result.model_dump(mode='json');data['approve']=True
    with pytest.raises(ValidationError):ResearchResult.model_validate(data)
    with pytest.raises(ValidationError):ResearchResult.model_validate_json('{not valid json}')


def test_budget_units_and_qualification_have_single_consistent_rule():
    assert not service.qualified({'score':90,'verdict':'not_a_fit'})
    assert not service.qualified({'score':90,'verdict':'insufficient_evidence'})
    assert not service.qualified({'score':69,'verdict':'possible_fit'})
    assert service.qualified({'score':70,'verdict':'possible_fit'})
    for provider,units in [('other',1),('model',-1),('model',0),('model',True)]:
        with pytest.raises(ValueError),db.connect() as c:db.reserve(c,provider,units)


def test_budget_shutdown_racing_sibling_commit_has_no_deadlock_or_live_lease():
    from threading import Barrier
    for _ in range(8):
        ca,first=research_job(10);second=queue.claim('sibling')
        _,_,result=first_result(second)
        barrier=Barrier(2)
        def shutdown():
            barrier.wait(timeout=5)
            queue.fail(first,db.BudgetExhausted('model budget exhausted; no request was sent.'))
        def commit():
            barrier.wait(timeout=5)
            try:
                with db.connect() as c:service.save_result(c,second,result)
                queue.finish(second)
            except db.LostLease:pass  # Shutdown winning the race intentionally fences it.
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(shutdown);b=pool.submit(commit)
            a.result(timeout=8);b.result(timeout=8)
        assert service.snapshot(ca['id'])['campaign']['status']=='budget_exhausted'
        with db.connect() as c:
            assert not c.execute("SELECT id FROM jobs WHERE campaign_id=%s AND status IN ('queued','running')",(ca['id'],)).fetchone()
            with pytest.raises(db.LostLease):db.authorize_capability(c,second['capability'])


def test_contending_claims_never_replace_a_valid_lease():
    from threading import Barrier
    ca=campaign(5)
    barrier=Barrier(12)
    def claim_together(n):
        barrier.wait(timeout=5)
        return queue.claim(str(n))
    with ThreadPoolExecutor(12) as pool:jobs=list(pool.map(claim_together,range(12)))
    claimed=[j for j in jobs if j]
    assert len(claimed)==1
    with db.connect() as c:
        saved=c.execute('SELECT * FROM jobs WHERE id=%s',(claimed[0]['id'],)).fetchone()
    assert saved['attempts']==saved['lease_version']==1


def test_open_transaction_cannot_authorize_after_actual_lease_expiry():
    ca,job=research_job()
    with db.connect() as c:
        c.execute("UPDATE jobs SET lease_until=clock_timestamp()+interval '0.1 seconds' WHERE id=%s",(job['id'],))
    with db.connect() as c:
        c.execute('SELECT now()')  # Fix transaction time before expiry.
        c.execute('SELECT pg_sleep(0.15)')
        with pytest.raises(db.LostLease):db.require_lease(c,job['id'],job['lease_version'],lock=True)
        with pytest.raises(db.LostLease):db.authorize_capability(c,job['capability'])
    assert not queue.heartbeat(job)
    successor=queue.claim('after-expiry')
    assert successor['lease_version']>job['lease_version']
