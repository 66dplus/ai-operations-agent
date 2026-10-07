import secrets
from . import db
from .config import settings


def claim(worker_id):
    token = secrets.token_urlsafe(32)
    with db.connect() as c:
        # Lock the campaign first. Claims for different campaigns can proceed
        # independently; short claims on the same campaign serialize safely.
        enabled = settings.live_enabled and settings.go_balance_disabled and settings.runtime_verified
        job = c.execute("SELECT j.* FROM jobs j JOIN campaigns ca ON ca.id=j.campaign_id WHERE ((j.status='queued' AND j.available_at<=now() AND j.attempts<3) OR (j.status='running' AND j.lease_until<clock_timestamp())) AND ca.status NOT IN ('cancelled','budget_exhausted') AND (ca.mode='demo' OR %s) ORDER BY j.available_at,j.id FOR UPDATE OF ca SKIP LOCKED LIMIT 1", (enabled,)).fetchone()
        if not job:
            return None
        # Re-read eligibility after acquiring the campaign lock: the selection
        # snapshot can predate another claim that committed just before this lock.
        job = c.execute("SELECT * FROM jobs WHERE id=%s AND ((status='queued' AND available_at<=now() AND attempts<3) OR (status='running' AND lease_until<clock_timestamp())) FOR UPDATE", (job['id'],)).fetchone()
        if not job:
            return None
        if job['attempts'] >= 3:
            message='Worker lease expired after three attempts.'
            c.execute("UPDATE jobs SET status='failed',error=%s,capability_hash=NULL,lease_version=lease_version+1 WHERE id=%s", (message, job['id']))
            if job['kind']=='research':
                c.execute("UPDATE leads SET status='failed',error=%s WHERE campaign_id=%s AND id=ANY(%s::uuid[]) AND qualification IS NULL", (message,job['campaign_id'],job['payload']['lead_ids']))
            db.log(c,job['campaign_id'],job['kind'],'failed',message,job_id=job['id'],attempt=job['attempts'])
            settle(c,job['campaign_id'])
            return None
        job = c.execute("UPDATE jobs SET status='running',attempts=attempts+1,worker_id=%s,lease_version=lease_version+1,lease_until=clock_timestamp()+(%s*interval '1 second'),capability_hash=%s,session_id=NULL WHERE id=%s RETURNING *", (worker_id, settings.lease_seconds, db.capability_hash(token), job['id'])).fetchone()
        c.execute("UPDATE campaigns SET status='running' WHERE id=%s", (job['campaign_id'],))
        db.log(c, job['campaign_id'], job['kind'], 'running', 'Research step started.', job_id=job['id'], attempt=job['attempts'])
    job['capability'] = token
    return job


def heartbeat(job):
    with db.connect() as c:
        result = c.execute("UPDATE jobs SET lease_until=clock_timestamp()+(%s*interval '1 second') WHERE id=%s AND lease_version=%s AND status='running' AND lease_until>clock_timestamp() RETURNING id", (settings.lease_seconds, job['id'], job['lease_version'])).fetchone()
        return bool(result)


def finish(job):
    with db.connect() as c:
        db.require_lease(c, job['id'], job['lease_version'], lock=True)
        c.execute("UPDATE jobs SET status='done',capability_hash=NULL WHERE id=%s", (job['id'],))
        db.log(c, job['campaign_id'], job['kind'], 'completed', 'Research step completed.', job_id=job['id'], attempt=job['attempts'])
        settle(c, job['campaign_id'])


def settle(c, campaign_id):
    # Serialize terminal settlement explicitly; concurrent final jobs must see
    # each other's committed state even if logging changes in the future.
    ca = c.execute('SELECT * FROM campaigns WHERE id=%s FOR UPDATE', (campaign_id,)).fetchone()
    outstanding = c.execute("SELECT 1 FROM jobs WHERE campaign_id=%s AND status IN ('queued','running') LIMIT 1", (campaign_id,)).fetchone()
    if outstanding:
        return
    failed = c.execute("SELECT 1 FROM jobs WHERE campaign_id=%s AND status='failed' LIMIT 1", (campaign_id,)).fetchone()
    if ca['status'] in ('cancelled', 'budget_exhausted'):
        return
    count = c.execute('SELECT count(*) AS count FROM leads WHERE campaign_id=%s AND qualification IS NOT NULL', (campaign_id,)).fetchone()['count']
    if ca['live_phase'] == 'pilot' and count == 5 and not failed:
        from .agent import release_after_pilot
        release_after_pilot(c, ca)
        return
    status = 'completed' if count == ca['target_count'] and not failed else 'partial'
    error = None if status == 'completed' else f'{count} of {ca["target_count"]} companies verified. Open failed steps or retry unfinished work.'
    c.execute('UPDATE campaigns SET status=%s,error=%s WHERE id=%s', (status, error, campaign_id))
    db.log(c, campaign_id, 'campaign', status, error or 'All requested companies researched.')


def fail(job, error, retryable=False):
    message = str(error)[:600]
    with db.connect() as c:
        try:
            db.require_lease(c, job['id'], job['lease_version'], lock=True)
        except db.LostLease:
            return
        exhausted = isinstance(error, db.BudgetExhausted)
        retry = retryable and job['attempts'] < 3 and not exhausted
        status = 'queued' if retry else 'failed'
        c.execute("UPDATE jobs SET status=%s,error=%s,available_at=now()+(%s*interval '1 second'),capability_hash=NULL WHERE id=%s", (status, message, 2 ** job['attempts'], job['id']))
        db.log(c, job['campaign_id'], job['kind'], 'retrying' if retry else 'failed', message, job_id=job['id'], attempt=job['attempts'])
        if not retry and job['kind'] == 'research':
            c.execute("UPDATE leads SET status='failed',error=%s WHERE campaign_id=%s AND id=ANY(%s::uuid[]) AND qualification IS NULL", (message, job['campaign_id'], job['payload']['lead_ids']))
        if exhausted:
            c.execute("UPDATE jobs SET status='cancelled',lease_version=lease_version+1,capability_hash=NULL WHERE campaign_id=%s AND status IN ('queued','running')", (job['campaign_id'],))
            c.execute("UPDATE campaigns SET status='budget_exhausted',error=%s WHERE id=%s", (message, job['campaign_id']))
        else:
            settle(c, job['campaign_id'])
