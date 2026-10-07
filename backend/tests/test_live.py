from dataclasses import replace
import json
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from operations import agent, config, db, gateway, providers, queue, service, worker
from operations.schemas import ResearchBatch
from test_core import campaign, research_job, first_result


@pytest.fixture(autouse=True)
def live_modules(monkeypatch, database):
    for module in (agent, providers, gateway):
        monkeypatch.setattr(module, 'settings', database)


def test_model_gateway_counts_dispatch_and_denies_cross_session_tools_and_cancel(monkeypatch,database):
    ca,job=research_job()
    with db.connect() as c:c.execute('UPDATE jobs SET session_id=%s WHERE id=%s',('owned-session',job['id']))
    enabled=replace(database,live_enabled=True,go_balance_disabled=True,runtime_verified=True)
    monkeypatch.setattr(gateway,'settings',enabled)
    monkeypatch.setattr(providers,'credential',lambda provider:'test-only-credential')
    sent=[]
    def reply(request):
        sent.append(request)
        assert request.url.host=='opencode.ai'
        return httpx.Response(200,content=b'data: [DONE]\n\n')
    original=httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(reply),**kwargs))
    headers={'Authorization':'Bearer '+job['capability'],'x-opencode-session':'owned-session'}
    body={'model':database.model,'stream':True,'messages':[],'tools':[{'function':{'name':'StructuredOutput'}}]}
    # Model proxy needs no MCP lifecycle; the later transport test owns it once.
    client=TestClient(gateway.app)
    try:
        assert client.post('/v1/chat/completions',json=body,headers=headers).status_code==200
        wrong=headers|{'x-opencode-session':'foreign-session'}
        assert client.post('/v1/chat/completions',json=body,headers=wrong).status_code==403
        assert client.post('/v1/chat/completions',json=body|{'tools':[{'function':{'name':'bash'}}]},headers=headers).status_code==403
        service.cancel_campaign(ca['id'])
        assert client.post('/v1/chat/completions',json=body,headers=headers).status_code==403
    finally:
        client.close()
    assert len(sent)==1
    with db.connect() as c:
        assert c.execute("SELECT model_calls FROM budget WHERE name='test'").fetchone()['model_calls']==1
        assert c.execute('SELECT status FROM provider_requests').fetchone()['status']=='received'


@pytest.mark.parametrize('status',[429,500,503,404])
def test_firecrawl_http_failure_reserves_each_physical_attempt(monkeypatch,status):
    ca,job=research_job(); sent=[]
    monkeypatch.setattr(providers,'credential',lambda _: 'test-only-credential')
    def reply(*args,**kwargs):
        sent.append(args[0]);return httpx.Response(status,json={'success':False})
    monkeypatch.setattr(providers.httpx,'post',reply)
    for _ in range(2):
        with pytest.raises(providers.ProviderError) as err:
            providers.firecrawl(job['capability'],'scrape',{'url':'https://public.test'},1)
        assert err.value.retryable==(status==429 or status>=500)
    assert len(sent)==2
    assert service.snapshot(ca['id'])['budget']['firecrawl_credits']==2


def test_unknown_provider_outcome_retains_last_credit_and_blocks_retry(monkeypatch):
    ca,job=research_job();sent=[]
    with db.connect() as c:c.execute("UPDATE budget SET firecrawl_credits=249 WHERE name='test'")
    monkeypatch.setattr(providers,'credential',lambda _: 'test-only-credential')
    def timeout(*args,**kwargs):
        sent.append(1);raise httpx.ReadTimeout('fixture timeout')
    monkeypatch.setattr(providers.httpx,'post',timeout)
    with pytest.raises(providers.ProviderError):providers.firecrawl(job['capability'],'scrape',{},1)
    with pytest.raises(db.BudgetExhausted):providers.firecrawl(job['capability'],'scrape',{},1)
    assert len(sent)==1
    with db.connect() as c:
        assert c.execute('SELECT status FROM provider_requests').fetchone()['status']=='reserved'
        assert c.execute("SELECT firecrawl_credits FROM budget WHERE name='test'").fetchone()['firecrawl_credits']==250


def test_live_disablement_blocks_durable_claims_and_gateway_dispatch(monkeypatch,database):
    ca,job=research_job()
    with db.connect() as c:
        c.execute("UPDATE campaigns SET mode='live' WHERE id=%s",(ca['id'],))
        c.execute("UPDATE jobs SET status='queued' WHERE id=%s",(job['id'],))
    assert queue.claim('restart-with-disabled-live') is None
    with db.connect() as c:c.execute("UPDATE jobs SET status='running' WHERE id=%s",(job['id'],))
    with pytest.raises(db.LostLease):providers.lease(job['capability'],reserve_provider='model')
    assert service.snapshot(ca['id'])['budget']['model_calls']==0


def test_batch_membership_and_semantic_repair_are_exact(monkeypatch):
    ca,job=research_job();lead,source,result=first_result(job)
    batch=ResearchBatch(leads=[result])
    with pytest.raises(ValueError):agent.validate_batch(job,batch,job['payload']['lead_ids'])
    with pytest.raises(ValueError):agent.validate_batch(job,ResearchBatch(leads=[result,result]),[str(lead['id'])])
    agent.validate_batch(job,batch,[str(lead['id'])])
    assert service.snapshot(ca['id'])['counts']['processed']==0
    responses=iter([ValueError('invalid JSON'),ValueError('still invalid')]);calls=[]
    def invalid(*args):
        calls.append(1);raise next(responses)
    monkeypatch.setattr(agent,'ask',invalid)
    with pytest.raises(ValueError):agent.structured(None,None,ResearchBatch,'Fixture')
    assert len(calls)==2


def test_public_urls_reject_private_pdf_auth_and_nonstandard_ports(monkeypatch):
    monkeypatch.setattr(providers.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))])
    for url in ['https://public.test','http://127.0.0.1','https://user:secret@public.test','https://public.test:8000','https://public.test/a.pdf']:
        with pytest.raises(ValueError):providers.public_url(url)


def test_page_scope_cache_and_three_page_limit(monkeypatch):
    ca,job=research_job();lead_id=job['payload']['lead_ids'][0]
    monkeypatch.setattr(providers,'public_url',lambda url:url)
    sent=[]
    def page(*args):
        sent.append(1);return {'markdown':'Public product evidence '*10,'metadata':{'title':'Robotics'}}
    monkeypatch.setattr(providers,'firecrawl',page)
    with db.connect() as c:domain=c.execute('SELECT domain FROM leads WHERE id=%s',(lead_id,)).fetchone()['domain']
    with pytest.raises(ValueError):providers.fetch_page(job['capability'],str(uuid4()),'https://'+domain)
    with pytest.raises(ValueError):providers.fetch_page(job['capability'],lead_id,'https://foreign.test')
    for suffix in ['','/product','/about']:
        providers.fetch_page(job['capability'],lead_id,'https://'+domain+suffix)
    providers.fetch_page(job['capability'],lead_id,'https://'+domain)
    with pytest.raises(ValueError):providers.fetch_page(job['capability'],lead_id,'https://'+domain+'/fourth')
    assert len(sent)==3


def test_research_cache_remaps_source_ids_and_binds_content_model_criteria():
    ca,job=research_job();lead,source,result=first_result(job)
    key=agent.cache_key(lead,[source],{'criteria':'robotics'})
    assert key!=agent.cache_key(lead,[source|{'content_hash':'changed'}],{'criteria':'robotics'})
    assert key!=agent.cache_key(lead,[source],{'criteria':'climate'})
    data=result.model_dump(mode='json');data.pop('lead_id')
    for evidence in data['qualification']['evidence']:evidence['source_url']=source['url'];evidence.pop('source_id')
    from psycopg.types.json import Jsonb
    with db.connect() as c:
        c.execute('INSERT INTO research_cache VALUES (%s,%s,now())',(key,Jsonb(data)))
        cached=agent.cached_result(c,key,lead,[source])
        assert cached.lead_id==lead['id'] and cached.qualification.evidence[0].source_id==source['id']


def test_pilot_exposes_only_five_then_releases_remaining_after_measurement(monkeypatch,database):
    ca=campaign(50)
    job=queue.claim('setup');worker.execute(job)
    job=queue.claim('discovery')
    with db.connect() as c:c.execute("UPDATE campaigns SET mode='live' WHERE id=%s",(ca['id'],))
    from operations import demo
    worker.persist_discovery(job,demo.candidates(50));queue.finish(job)
    with db.connect() as c:
        jobs=c.execute("SELECT * FROM jobs WHERE kind='research'").fetchall()
        assert len(jobs)==1 and len(jobs[0]['payload']['lead_ids'])==5
        c.execute("UPDATE campaigns SET mode='demo' WHERE id=%s",(ca['id'],))
    pilot=queue.claim('pilot');worker.execute(pilot)
    snap=service.snapshot(ca['id']);assert snap['counts']['processed']==5
    assert snap['campaign']['live_phase']=='all'
    assert any(log['step']=='pilot' and log['metadata']['projected_calls']==27 for log in snap['logs'])
    with db.connect() as c:assert c.execute("SELECT count(*) AS n FROM jobs WHERE kind='research' AND status='queued'").fetchone()['n']==9


def test_committed_plan_checkpoint_survives_crash_before_finish(monkeypatch):
    ca=campaign(5);job=queue.claim('plan')
    from operations import demo
    from psycopg.types.json import Jsonb
    criteria=demo.plan(ca['query'],5).model_dump()
    with db.connect() as c:
        c.execute('UPDATE campaigns SET criteria=%s WHERE id=%s',(Jsonb(criteria),ca['id']))
        db.enqueue(c,ca['id'],'discovery','discovery')
        c.execute("UPDATE jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(job['id'],))
    successor=queue.claim('restarted-plan')
    monkeypatch.setattr(agent,'runtime',lambda *_:pytest.fail('A committed plan must not invoke AI again.'))
    agent.run_live_job(successor,service.snapshot(ca['id'])['campaign'])
    assert service.snapshot(ca['id'])['campaign']['criteria']==criteria
    with db.connect() as c:assert c.execute("SELECT count(*) AS n FROM jobs WHERE kind='discovery'").fetchone()['n']==1


def test_malformed_firecrawl_json_is_explicit_and_counted(monkeypatch):
    ca,job=research_job()
    monkeypatch.setattr(providers,'credential',lambda _:'fixture')
    monkeypatch.setattr(providers.httpx,'post',lambda *a,**k:httpx.Response(200,content=b'not JSON'))
    with pytest.raises(providers.ProviderError,match='invalid JSON'):providers.firecrawl(job['capability'],'scrape',{},1)
    assert service.snapshot(ca['id'])['budget']['firecrawl_credits']==1


def test_mcp_transport_completes_slow_tool_and_exposes_only_scoped_tools(monkeypatch):
    import time
    ca,job=research_job()
    def delayed_search(*args):
        time.sleep(16)
        return [{'url':'https://fixture.test','title':'Public robotics fixture'}]
    monkeypatch.setattr(providers,'search',delayed_search)
    headers={'Authorization':'Bearer '+job['capability'],'Accept':'application/json, text/event-stream'}
    def message(method,params):return {'jsonrpc':'2.0','id':1,'method':method,'params':params}
    with TestClient(gateway.app) as client:
        listed=client.post('/mcp/',json=message('tools/list',{}),headers=headers).json()['result']['tools']
        assert {tool['name'] for tool in listed}=={'search','fetch_page','task_context'}
        started=time.monotonic()
        result=client.post('/mcp/',json=message('tools/call',{'name':'search','arguments':{'query':'fixture'}}),headers=headers).json()['result']
        assert time.monotonic()-started>=16
        assert not result.get('isError') and 'fixture.test' in json.dumps(result)
        assert client.post('/mcp/',json=message('tools/list',{})).status_code==403
    assert service.snapshot(ca['id'])['budget']['model_calls']==0


def test_company_fetch_preserves_discovered_www_url(monkeypatch):
    ca,job=research_job(1)
    with db.connect() as c:
        domain=c.execute('SELECT domain FROM leads WHERE campaign_id=%s',(ca['id'],)).fetchone()['domain']
        from psycopg.types.json import Jsonb
        c.execute("INSERT INTO step_outputs VALUES (%s,'discovery',%s)",(ca['id'],Jsonb({'companies':[{'company_name':'Fixture','url':'https://www.'+domain}]})))
    requests=[]
    def intercept(*args,**kwargs):
        requests.append(kwargs['json'])
        return httpx.Response(503,text='temporary gateway failure')
    monkeypatch.setattr(agent.httpx,'post',intercept)
    with pytest.raises(providers.ProviderError) as error:agent.run_live_job(job,ca)
    assert error.value.retryable
    assert requests[0]['url']=='https://www.'+domain
    assert 'HTTP 503' in str(error.value)


def test_upstream_error_redacts_secrets_and_retains_model_reservation(monkeypatch,database):
    ca,job=research_job()
    with db.connect() as c:c.execute('UPDATE jobs SET session_id=%s WHERE id=%s',('owned-session',job['id']))
    monkeypatch.setattr(gateway,'settings',replace(database,live_enabled=True,go_balance_disabled=True,runtime_verified=True))
    key='fixture-secret-value'
    monkeypatch.setattr(providers,'credential',lambda _:key)
    original=httpx.AsyncClient
    def reply(request):return httpx.Response(400,json={'error':{'message':'Failure '+key+' '+job['capability']}})
    monkeypatch.setattr(gateway.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(reply),**kw))
    with_client=TestClient(gateway.app)
    try:
        response=with_client.post('/v1/chat/completions',headers={'Authorization':'Bearer '+job['capability'],'x-opencode-session':'owned-session'},json={'model':database.model,'stream':True,'messages':[]})
        assert response.status_code==400
        assert key not in response.text and job['capability'] not in response.text
        assert response.json()['error']['message']=='Failure [redacted] [redacted]'
    finally:with_client.close()
    assert service.snapshot(ca['id'])['budget']['model_calls']==1
    with db.connect() as c:assert c.execute('SELECT status FROM provider_requests').fetchone()['status']=='received'


def test_batch_repair_feedback_identifies_each_invalid_company_quote():
    from operations import demo
    ca,job=research_job(2);results=[];names=[]
    with db.connect() as c:
        for lead_id in job['payload']['lead_ids']:
            lead=c.execute('SELECT * FROM leads WHERE id=%s',(lead_id,)).fetchone()
            source=service.add_source(c,job,lead_id,**demo.page(lead))
            result=demo.research(lead,source)
            result.qualification.evidence[0].quote='Invented continuous quote, not in any source.'
            results.append(result);names.append(lead['company_name'])
    with pytest.raises(ValueError) as error:agent.validate_batch(job,ResearchBatch(leads=results),job['payload']['lead_ids'])
    assert all(name in str(error.value) for name in names)
    assert 'Unicode punctuation' in str(error.value)
    assert service.snapshot(ca['id'])['counts']['processed']==0


def test_five_company_diagnostics_reach_the_single_repair_prompt(monkeypatch):
    from operations import demo
    ca,job=research_job(5);invalid=[];valid=[];names=[]
    with db.connect() as c:
        for lead_id in job['payload']['lead_ids']:
            lead=c.execute('SELECT * FROM leads WHERE id=%s',(lead_id,)).fetchone()
            source=service.add_source(c,job,lead_id,**demo.page(lead))
            result=demo.research(lead,source);valid.append(result)
            broken=result.model_copy(deep=True)
            broken.qualification.evidence[0].quote='Unverified invented evidence with Markdown **markup** and Unicode punctuation. '*2
            invalid.append(broken);names.append(lead['company_name'])
    calls=[]
    def reply(client,session,schema,prompt):
        calls.append(prompt)
        return ResearchBatch(leads=invalid if len(calls)==1 else valid)
    monkeypatch.setattr(agent,'ask',reply)
    result=agent.structured(None,None,ResearchBatch,'Research five companies.',
                            lambda batch:agent.validate_batch(job,batch,job['payload']['lead_ids']))
    assert len(calls)==2 and len(result.leads)==5
    assert all(name in calls[1] for name in names)
    assert calls[1].count('Unicode punctuation; do not combine fragments.')==5
    assert service.snapshot(ca['id'])['counts']['processed']==0


@pytest.mark.parametrize('column,spent',[('model_calls',100),('firecrawl_credits',250)])
def test_exhausted_live_budget_rejects_new_run_before_any_job_or_dispatch(monkeypatch,database,column,spent):
    from operations import api
    monkeypatch.setattr(service,'live_ready',lambda:True)
    with db.connect() as c:
        c.execute(f"UPDATE budget SET {column}=%s WHERE name='test'",(spent,))
    with TestClient(api.app) as client:
        headers={'Origin':database.origin,'Idempotency-Key':str(uuid4())}
        response=client.post('/api/campaigns',headers=headers,json={'query':'Find 5 robotics companies.','mode':'live'})
        assert response.status_code==409 and 'budget is exhausted' in response.json()['detail']
        with db.connect() as c:
            assert c.execute('SELECT count(*) AS n FROM campaigns').fetchone()['n']==0
            assert c.execute('SELECT count(*) AS n FROM jobs').fetchone()['n']==0
            assert c.execute('SELECT count(*) AS n FROM provider_requests').fetchone()['n']==0
        assert client.post('/api/campaigns',headers=headers,json={'query':'Find 5 robotics companies.','mode':'demo'}).status_code==201
