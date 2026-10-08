from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from operations import agent, api, config, db, demo, gateway, providers, queue, service, worker
from operations.schemas import ResearchBatch, Review
from test_core import campaign, first_result, research_job


def limits(monkeypatch, database, enabled):
    override = replace(database, budget_limits_enabled=enabled)
    for module in (config, db, agent, api, gateway, providers, queue, service):
        monkeypatch.setattr(module, 'settings', override)
    return override


@pytest.mark.parametrize('value,expected', [(None, True), ('', True), ('true', True), ('fales', True), ('0', True), ('false', False), (' FALSE ', False)])
def test_enforcement_requires_explicit_opt_out(value, expected):
    assert config.budget_limits_enabled(value) is expected


def test_uncapped_atomic_accounting_and_reenabling_preserves_spend(monkeypatch, database):
    limits(monkeypatch, database, False)
    with db.connect() as c:
        c.execute("UPDATE budget SET model_calls=100,firecrawl_credits=250 WHERE name='test'")
    def reserve(provider):
        with db.connect() as c:
            return db.reserve(c, provider, 1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(reserve, ['model', 'firecrawl'] * 8))
    assert len(set(ids)) == 16
    with db.connect() as c:
        spent = c.execute("SELECT * FROM budget WHERE name='test'").fetchone()
        assert spent['model_calls'] == 108 and spent['firecrawl_credits'] == 258
        assert c.execute('SELECT count(*) AS n FROM provider_requests').fetchone()['n'] == 16
    limits(monkeypatch, database, True)
    for provider in ['model', 'firecrawl']:
        with pytest.raises(db.BudgetExhausted), db.connect() as c:
            db.reserve(c, provider, 1)
    with db.connect() as c:
        assert c.execute("SELECT * FROM budget WHERE name='test'").fetchone() == spent


def test_uncapped_live_start_readback_and_origin_denial(monkeypatch, database):
    limits(monkeypatch, database, False)
    monkeypatch.setattr(service, 'live_ready', lambda: True)
    with db.connect() as c:
        c.execute("UPDATE budget SET model_calls=130,firecrawl_credits=350 WHERE name='test'")
    with TestClient(api.app) as client:
        headers = {'Origin': database.origin, 'Idempotency-Key': str(uuid4())}
        body = {'query': 'Find 5 robotics companies.', 'mode': 'live'}
        for extra in [{'Origin': 'https://foreign.test'}, {'Authorization': 'Bearer agent'}]:
            assert client.post('/api/campaigns', headers=headers | extra, json=body).status_code == 403
        response = client.post('/api/campaigns', headers=headers, json=body)
        assert response.status_code == 201
        assert client.post('/api/campaigns', headers=headers, json=body).json()['id'] == response.json()['id']
        snap = client.get('/api/campaigns/' + response.json()['id']).json()
        assert snap['budget']['limits_enabled'] is False
        assert snap['budget']['model_calls'] == 130 and snap['budget']['firecrawl_credits'] == 350
        assert snap['usage']['model_requests'] == snap['usage']['firecrawl_requests'] == 0


def test_usage_scoped_to_campaign_and_reports_not_estimates(monkeypatch, database):
    limits(monkeypatch, database, False)
    ca, job = research_job(1)
    other = campaign(1)
    with db.connect() as c:
        r1 = db.reserve(c, 'model', 1, job)
        r2 = db.reserve(c, 'firecrawl', 6, job)
        db.reserve(c, 'firecrawl', 1, job)
        foreign = c.execute('SELECT * FROM jobs WHERE campaign_id=%s', (other['id'],)).fetchone()
        db.reserve(c, 'model', 1, foreign)
    providers.receipt(r1, 'received', {'tokens': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120}})
    providers.receipt(r2, 'received', {'credits_used': 2})
    snap = service.snapshot(ca['id']); u = snap['usage']
    assert snap['budget']['model_calls'] == 2 and u['model_requests'] == 1
    assert u['firecrawl_requests'] == 2 and u['tokens']['total_tokens'] == 120
    assert u['tokens_reported_requests'] == 1 and u['firecrawl_reserved_credits'] == 7
    assert u['firecrawl_reported_credits'] == 2 and u['firecrawl_reported_requests'] == 1
    assert u['uncertain_requests'] == 1 and len(u['requests']) == 3


@pytest.mark.parametrize('credits,reported', [(0, 0), (2, 2), (None, None), (-1, None), ('2', None), (True, None)])
def test_firecrawl_only_valid_reported_credit_fields(monkeypatch, database, credits, reported):
    limits(monkeypatch, database, False)
    ca, job = research_job(1)
    monkeypatch.setattr(providers, 'credential', lambda _: 'fixture')
    monkeypatch.setattr(providers.httpx, 'post', lambda *a, **k: httpx.Response(200, json={'success': True, 'data': {'web': []}, 'creditsUsed': credits}))
    providers.firecrawl(job['capability'], 'search', {}, 6)
    u = service.snapshot(ca['id'])['usage']
    assert u['firecrawl_reserved_credits'] == 6 and u['firecrawl_reported_credits'] == reported


@pytest.mark.parametrize('complete', [False, True])
def test_fragmented_model_stream_preserves_bytes_and_uncertainty(monkeypatch, database, complete):
    limits(monkeypatch, database, False)
    ca, job = research_job(1)
    with db.connect() as c:
        c.execute("UPDATE budget SET model_calls=100 WHERE name='test'")
        c.execute("UPDATE jobs SET session_id='owned' WHERE id=%s", (job['id'],))
    monkeypatch.setattr(gateway, 'settings', replace(db.settings, live_enabled=True, go_balance_disabled=True, runtime_verified=True))
    monkeypatch.setattr(providers, 'credential', lambda _: 'fixture')
    data = b'data: {"choices":[{"delta":{"content":"[DONE] is text"}}]}\r\n\r\ndata: {"usage":{"prompt_tokens":123,"completion_tokens":45,"total_tokens":168}}\n\n'
    if complete: data += b'data: [DONE]\n\n'
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for i in range(0, len(data), 3): yield data[i:i+3]
    original = httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Chunks())), **kw))
    client = TestClient(gateway.app)
    try:
        body = {'model': database.model, 'stream': True, 'messages': []}
        headers = {'Authorization': 'Bearer ' + job['capability'], 'x-opencode-session': 'owned'}
        assert client.post('/v1/chat/completions', headers=headers, json=body).content == data
        assert client.post('/v1/chat/completions', headers=headers | {'x-opencode-session': 'foreign'}, json=body).status_code == 403
    finally: client.close()
    snap = service.snapshot(ca['id'])
    assert snap['budget']['model_calls'] == 101 and snap['usage']['tokens']['total_tokens'] == 168
    assert snap['usage']['uncertain_requests'] == (0 if complete else 1)


def test_uncapped_runtime_error_not_misclassified_as_exhaustion(monkeypatch, database):
    limits(monkeypatch, database, False)
    with db.connect() as c: c.execute("UPDATE budget SET model_calls=150,firecrawl_credits=400 WHERE name='test'")
    with httpx.Client(base_url='http://fixture', transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'info': {'error': {'name': 'APIError', 'data': {'message': 'temporary upstream failure'}}}}))) as client:
        with pytest.raises(providers.ProviderError, match='temporary upstream failure'):
            agent.ask(client, 'session', ResearchBatch, 'Fixture')


def test_explicit_uncapped_retry_keeps_approval_and_fences_old_capability(monkeypatch, database):
    limits(monkeypatch, database, True)
    ca, job = research_job(5)
    lead, source, result = first_result(job)
    with db.connect() as c: service.save_result(c, job, result)
    service.review_draft(lead['id'], Review(revision=1, decision='approved'))
    before = service.export_rows(ca['id'])
    queue.fail(job, db.BudgetExhausted('Model budget exhausted.'))
    limits(monkeypatch, database, False)
    assert queue.claim('before-explicit-retry') is None
    service.retry_campaign(ca['id'])
    with pytest.raises(db.LostLease): providers.lease(job['capability'], reserve_provider='model')
    worker.execute(queue.claim('new-worker'))
    assert service.snapshot(ca['id'])['counts']['processed'] == 5
    assert service.export_rows(ca['id']) == before


def test_explicit_uncapped_retry_releases_completed_pilot_without_rerun(monkeypatch, database):
    limits(monkeypatch, database, True)
    ca = campaign(10); worker.execute(queue.claim('plan'))
    job = queue.claim('discovery')
    with db.connect() as c: c.execute("UPDATE campaigns SET mode='live' WHERE id=%s", (ca['id'],))
    worker.persist_discovery(job, demo.candidates(10)); queue.finish(job)
    with db.connect() as c:
        c.execute("UPDATE campaigns SET mode='demo' WHERE id=%s", (ca['id'],))
        c.execute("UPDATE budget SET firecrawl_credits=250 WHERE name='test'")
    worker.execute(queue.claim('pilot'))
    before = service.snapshot(ca['id'])
    assert before['campaign']['status'] == 'budget_exhausted' and before['counts']['processed'] == 5
    approved = next(x for x in before['leads'] if x['current_revision'])
    service.review_draft(approved['id'], Review(revision=1, decision='approved'))
    exported = service.export_rows(ca['id'])
    limits(monkeypatch, database, False)
    assert queue.claim('before-explicit-retry') is None
    service.retry_campaign(ca['id'])
    with db.connect() as c:
        assert c.execute("SELECT count(*) AS n FROM jobs WHERE status='queued' AND kind='research'").fetchone()['n'] == 1
        assert c.execute("SELECT count(*) AS n FROM jobs WHERE status='done' AND kind='research'").fetchone()['n'] == 1
    worker.execute(queue.claim('remaining'))
    snap = service.snapshot(ca['id'])
    assert snap['counts']['processed'] == 10 and snap['campaign']['status'] == 'completed'
    assert snap['budget']['firecrawl_credits'] == 250 and service.export_rows(ca['id']) == exported
