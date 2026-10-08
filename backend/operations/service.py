import csv
import hashlib
import io
import json
import re
from urllib.parse import urlparse
from uuid import uuid4
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from . import db
from .config import settings, live_ready
from .schemas import ResearchResult


def normalized_domain(url: str) -> str:
    p = urlparse(url if '://' in url else 'https://' + url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('A public HTTP(S) company URL is required.')
    host = p.hostname.lower().rstrip('.').encode('idna').decode()
    if host.startswith('www.'):
        host = host[4:]
    if '.' not in host or host in ('localhost', 'example.com'):
        raise ValueError('A company domain is required.')
    return host


def target_from_query(query):
    match = re.search(r'(?:find|show|research|найди|найти|покажи|исследуй)\s+(\d+)\b', query, re.I)
    count = int(match.group(1)) if match else 20
    if not 1 <= count <= 50:
        raise HTTPException(422, 'Choose between 1 and 50 companies for this MVP.')
    return count


def create_campaign(body, idempotency_key):
    if body.mode == 'live' and not live_ready():
        raise HTTPException(503, 'Live research needs the verified OpenCode runtime and Go paid fallback disabled. Demo research is available.')
    count = target_from_query(body.query)
    with db.connect() as c:
        existing = c.execute('SELECT * FROM campaigns WHERE idempotency_key=%s', (idempotency_key,)).fetchone()
        if existing:
            if existing['query'] != body.query.strip() or existing['mode'] != body.mode:
                raise HTTPException(409, 'This request key was already used with a different query.')
            return existing
        if body.mode == 'live' and settings.budget_limits_enabled:
            budget = c.execute('SELECT * FROM budget WHERE name=%s', (settings.budget_scope,)).fetchone()
            if budget['model_calls'] >= settings.max_calls or budget['firecrawl_credits'] >= settings.max_credits:
                raise HTTPException(409, 'The shared live verification budget is exhausted. Demo research and saved results remain available.')
        campaign_id = uuid4()
        inserted = c.execute('INSERT INTO campaigns(id,query,mode,target_count,idempotency_key) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(idempotency_key) DO NOTHING RETURNING *',
                  (campaign_id, body.query.strip(), body.mode, count, idempotency_key)).fetchone()
        if not inserted:
            existing = c.execute('SELECT * FROM campaigns WHERE idempotency_key=%s', (idempotency_key,)).fetchone()
            if existing['query'] != body.query.strip() or existing['mode'] != body.mode:
                raise HTTPException(409, 'This request key belongs to a different query.')
            return existing
        db.enqueue(c, campaign_id, 'plan', 'plan')
        db.log(c, campaign_id, 'campaign', 'queued', 'Research queued.')
        return c.execute('SELECT * FROM campaigns WHERE id=%s', (campaign_id,)).fetchone()


def qualified(qualification):
    return bool(qualification and qualification['score'] >= 70 and qualification['verdict'] in ('strong_fit', 'possible_fit'))


def campaign_usage(c, campaign_id):
    requests = c.execute('SELECT r.id,r.provider,r.units,r.status,r.usage,r.created_at,j.kind AS step FROM provider_requests r JOIN jobs j ON j.id=r.job_id WHERE j.campaign_id=%s ORDER BY r.created_at', (campaign_id,)).fetchall()
    for request in requests:
        request['usage'] = request['usage'] or {}
    models = [r for r in requests if r['provider'] == 'model']
    pages = [r for r in requests if r['provider'] == 'firecrawl']
    credits = [r['usage']['credits_used'] for r in pages if 'credits_used' in r['usage']]
    tokens = [r['usage']['tokens'] for r in models if 'tokens' in r['usage']]
    return {'model_requests': len(models), 'firecrawl_requests': len(pages),
            'uncertain_requests': sum(r['status'] == 'reserved' for r in requests),
            'firecrawl_reserved_credits': sum(r['units'] for r in pages),
            'firecrawl_reported_credits': sum(credits) if credits else None,
            'firecrawl_reported_requests': len(credits), 'tokens_reported_requests': len(tokens),
            'tokens': {k: sum(t.get(k, 0) for t in tokens) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')},
            'requests': requests}


def snapshot(campaign_id):
    with db.connect() as c:
        campaign = c.execute('SELECT * FROM campaigns WHERE id=%s', (campaign_id,)).fetchone()
        if not campaign:
            raise HTTPException(404, 'Campaign not found.')
        leads = c.execute('SELECT l.*, d.subject, d.body FROM leads l LEFT JOIN drafts d ON d.lead_id=l.id AND d.revision=l.current_revision WHERE l.campaign_id=%s ORDER BY COALESCE((qualification->>\'score\')::int,-1) DESC, company_name', (campaign_id,)).fetchall()
        for lead in leads:
            lead['qualified'] = qualified(lead['qualification'])
            lead['sources'] = c.execute('SELECT id,url,title,content,content_hash,fetched_at FROM sources WHERE lead_id=%s ORDER BY fetched_at', (lead['id'],)).fetchall()
        logs = c.execute('SELECT * FROM run_logs WHERE campaign_id=%s ORDER BY id DESC LIMIT 300', (campaign_id,)).fetchall()
        budget = c.execute('SELECT * FROM budget WHERE name=%s', (settings.budget_scope,)).fetchone()
        budget.update(limits_enabled=settings.budget_limits_enabled, max_model_calls=settings.max_calls, max_firecrawl_credits=settings.max_credits)
        usage = campaign_usage(c, campaign_id)
    return {'campaign': campaign, 'leads': leads, 'logs': logs, 'budget': budget, 'usage': usage,
            'counts': {'discovered': len(leads), 'processed': sum(x['qualification'] is not None for x in leads),
                       'qualified': sum(x['qualified'] for x in leads),
                       'approved': sum(x['review_status'] == 'approved' for x in leads),
                       'failed': sum(x['status'] == 'failed' for x in leads)}}


def add_source(c, job, lead_id, url, title, content):
    db.require_lease(c, job['id'], job['lease_version'], lock=True)
    if str(lead_id) not in [str(x) for x in job['payload'].get('lead_ids', [])]:
        raise db.LostLease('This company is outside the research task.')
    lead = c.execute('SELECT * FROM leads WHERE id=%s AND campaign_id=%s FOR UPDATE', (lead_id, job['campaign_id'])).fetchone()
    if not lead:
        raise ValueError('Unknown company.')
    existing = c.execute('SELECT * FROM sources WHERE lead_id=%s AND url=%s', (lead_id, url)).fetchone()
    # Quotes in verified results refer to this immutable source snapshot.
    if lead['qualification']:
        if existing:
            return existing
        raise ValueError('Verified source evidence cannot be replaced by a research retry.')
    digest = hashlib.sha256(content.encode()).hexdigest()
    source = c.execute('INSERT INTO sources(id,lead_id,url,title,content,content_hash) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(lead_id,url) DO UPDATE SET title=EXCLUDED.title,content=EXCLUDED.content,content_hash=EXCLUDED.content_hash,fetched_at=now() RETURNING *',
                       (uuid4(), lead_id, url, title, content, digest)).fetchone()
    if not lead['qualification']:
        c.execute("UPDATE leads SET status='scraped' WHERE id=%s", (lead_id,))
    db.log(c, job['campaign_id'], 'scraping', 'completed', title, lead_id=lead_id, job_id=job['id'], attempt=job['attempts'])
    return source


def save_result(c, job, result: ResearchResult):
    db.require_lease(c, job['id'], job['lease_version'], lock=True)
    if str(result.lead_id) not in [str(x) for x in job['payload'].get('lead_ids', [])]:
        raise ValueError('Result references a company outside this task.')
    lead = c.execute('SELECT * FROM leads WHERE id=%s AND campaign_id=%s FOR UPDATE', (result.lead_id, job['campaign_id'])).fetchone()
    if not lead:
        raise ValueError('Unknown company.')
    if lead['qualification']:
        return  # A committed successful result is immutable under research retries.
    sources = {str(s['id']): s for s in c.execute('SELECT * FROM sources WHERE lead_id=%s', (result.lead_id,)).fetchall()}
    for evidence in result.qualification.evidence:
        source = sources.get(str(evidence.source_id))
        if not source:
            raise ValueError(f"{lead['company_name']}: stored source is not assigned to this company. Use its supplied source IDs.")
        if ' '.join(evidence.quote.split()) not in ' '.join(source['content'].split()):
            raise ValueError(f"{lead['company_name']}: quote {evidence.quote[:140]!r} is not an exact excerpt of its stored source. Preserve Markdown markup and Unicode punctuation; do not combine fragments.")
    eligible = qualified(result.qualification.model_dump())
    if eligible and not result.draft:
        raise ValueError('Qualified companies need an introduction draft.')
    if not eligible and result.draft:
        raise ValueError('Below-threshold companies cannot have an outreach draft.')
    c.execute('UPDATE leads SET enrichment=%s,qualification=%s,status=%s,error=NULL WHERE id=%s',
              (Jsonb(result.enrichment.model_dump()), Jsonb(result.qualification.model_dump(mode='json')), 'drafted' if eligible else 'qualified', result.lead_id))
    if result.draft and lead['current_revision'] is None:
        c.execute("INSERT INTO drafts(lead_id,revision,subject,body,author) VALUES (%s,1,%s,%s,'agent')", (result.lead_id, result.draft.subject, result.draft.body))
        c.execute('UPDATE leads SET current_revision=1 WHERE id=%s', (result.lead_id,))
    for step in ['enrichment', 'qualification'] + (['draft'] if eligible else []):
        db.log(c, job['campaign_id'], step, 'completed', lead['company_name'], lead_id=result.lead_id, job_id=job['id'], attempt=job['attempts'])



def locked_lead(c, lead_id):
    row=c.execute('SELECT campaign_id FROM leads WHERE id=%s', (lead_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Company not found.')
    c.execute('SELECT id FROM campaigns WHERE id=%s FOR UPDATE', (row['campaign_id'],))
    return c.execute('SELECT * FROM leads WHERE id=%s FOR UPDATE', (lead_id,)).fetchone()

def edit_draft(lead_id, body):
    with db.connect() as c:
        lead = locked_lead(c, lead_id)
        if not lead:
            raise HTTPException(404, 'Company not found.')
        if lead['current_revision'] != body.expected_revision:
            raise HTTPException(409, 'The draft changed. Reload before editing.')
        revision = body.expected_revision + 1
        c.execute("INSERT INTO drafts(lead_id,revision,subject,body,author) VALUES (%s,%s,%s,%s,'human')", (lead_id, revision, body.subject, body.body))
        c.execute("UPDATE leads SET current_revision=%s,review_status='pending',approved_revision=NULL WHERE id=%s", (revision, lead_id))
        db.log(c, lead['campaign_id'], 'review', 'edited', 'A new draft revision needs review.', lead_id=lead_id, metadata={'revision': revision})
    return {'revision': revision}


def review_draft(lead_id, body):
    with db.connect() as c:
        lead = locked_lead(c, lead_id)
        if not lead:
            raise HTTPException(404, 'Company not found.')
        if lead['current_revision'] != body.revision or not lead['current_revision']:
            raise HTTPException(409, 'Review must refer to the current draft revision.')
        if lead['review_status'] == body.decision:
            return {'status': body.decision, 'revision': body.revision}
        c.execute('INSERT INTO reviews(lead_id,revision,decision) VALUES (%s,%s,%s)', (lead_id, body.revision, body.decision))
        c.execute('UPDATE leads SET review_status=%s,approved_revision=%s WHERE id=%s', (body.decision, body.revision if body.decision == 'approved' else None, lead_id))
        db.log(c, lead['campaign_id'], 'review', body.decision, 'Human review recorded.', lead_id=lead_id, metadata={'revision': body.revision})
    return {'status': body.decision, 'revision': body.revision}


def export_rows(campaign_id):
    with db.connect() as c:
        if not c.execute('SELECT 1 FROM campaigns WHERE id=%s', (campaign_id,)).fetchone():
            raise HTTPException(404, 'Campaign not found.')
        rows = c.execute("SELECT l.id,l.company_name,l.domain,l.enrichment,l.qualification,d.subject,d.body,d.revision FROM leads l JOIN drafts d ON d.lead_id=l.id AND d.revision=l.approved_revision WHERE campaign_id=%s AND review_status='approved' ORDER BY company_name", (campaign_id,)).fetchall()
        return [{'company': x['company_name'], 'domain': x['domain'], 'industry': x['enrichment']['industry'],
                 'score': x['qualification']['score'], 'reasons': '; '.join(x['qualification']['reasons']),
                 'sources': '; '.join(s['url'] for s in c.execute('SELECT DISTINCT url FROM sources WHERE lead_id=%s', (x['id'],)).fetchall()),
                 'subject': x['subject'], 'body': x['body'], 'approved_revision': x['revision']} for x in rows]


def csv_export(rows):
    output = io.StringIO(newline='')
    fields = ['company', 'domain', 'industry', 'score', 'reasons', 'sources', 'subject', 'body', 'approved_revision']
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        # Spreadsheet apps evaluate formulas even in quoted CSV cells.
        writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v for k, v in row.items()})
    return '\ufeff' + output.getvalue()


def cancel_campaign(campaign_id):
    with db.connect() as c:
        campaign = c.execute('SELECT * FROM campaigns WHERE id=%s FOR UPDATE', (campaign_id,)).fetchone()
        if not campaign:
            raise HTTPException(404, 'Campaign not found.')
        c.execute("UPDATE jobs SET status='cancelled',lease_version=lease_version+1,capability_hash=NULL WHERE campaign_id=%s AND status IN ('queued','running')", (campaign_id,))
        c.execute("UPDATE campaigns SET status='cancelled',error=NULL WHERE id=%s", (campaign_id,))
        db.log(c, campaign_id, 'campaign', 'cancelled', 'Research stopped. Saved results remain available.')
    return {'status': 'cancelled'}


def retry_campaign(campaign_id):
    with db.connect() as c:
        ca = c.execute('SELECT * FROM campaigns WHERE id=%s FOR UPDATE', (campaign_id,)).fetchone()
        if not ca:
            raise HTTPException(404, 'Campaign not found.')
        if ca['status'] == 'budget_exhausted' and settings.budget_limits_enabled:
            raise HTTPException(409, 'The shared budget is exhausted; retry cannot increase it.')
        jobs = c.execute("UPDATE jobs SET status='queued',attempts=0,available_at=now(),error=NULL,lease_version=lease_version+1,capability_hash=NULL WHERE campaign_id=%s AND status IN ('failed','cancelled') RETURNING id", (campaign_id,)).fetchall()
        if not jobs:
            # A capped pilot can stop before creating remaining jobs. Release
            # only after explicit retry; completed results/reviews are untouched.
            if ca['status'] != 'budget_exhausted' or ca['live_phase'] != 'pilot':
                raise HTTPException(409, 'There are no failed or cancelled steps to retry.')
            from .queue import settle
            c.execute("UPDATE campaigns SET status='queued',error=NULL WHERE id=%s", (campaign_id,))
            settle(c, campaign_id)
            if not c.execute("SELECT 1 FROM jobs WHERE campaign_id=%s AND status='queued'", (campaign_id,)).fetchone():
                raise HTTPException(409, 'There are no unfinished pilot steps to release.')
        c.execute("UPDATE leads SET status=CASE WHEN EXISTS(SELECT 1 FROM sources s WHERE s.lead_id=leads.id) THEN 'scraped' ELSE 'discovered' END,error=NULL WHERE campaign_id=%s AND qualification IS NULL", (campaign_id,))
        c.execute("UPDATE campaigns SET status='queued',error=NULL WHERE id=%s", (campaign_id,))
        db.log(c, campaign_id, 'campaign', 'retrying', 'Only unfinished work was requeued.')
    return {'status': 'queued'}
