import hashlib
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .config import settings

@contextmanager
def connect():
    with psycopg.connect(settings.database_url, row_factory=dict_row) as connection:
        yield connection


def migrate():
    with connect() as c:
        # One migration owner; startup races cannot partially apply the schema.
        c.execute('SELECT pg_advisory_xact_lock(174013)')
        c.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY)')
        for path in sorted((Path(__file__).parents[1] / 'migrations').glob('*.sql')):
            if not c.execute('SELECT 1 FROM schema_migrations WHERE version=%s', (path.name,)).fetchone():
                c.execute(path.read_text())
                c.execute('INSERT INTO schema_migrations VALUES (%s)', (path.name,))
        c.execute('INSERT INTO budget(name) VALUES (%s) ON CONFLICT DO NOTHING', (settings.budget_scope,))


def log(c, campaign_id, step, status, detail='', *, lead_id=None, job_id=None, attempt=1, metadata=None):
    c.execute('INSERT INTO run_logs(campaign_id,lead_id,job_id,step,status,attempt,detail,metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
              (campaign_id, lead_id, job_id, step, status, attempt, detail, Jsonb(metadata or {})))
    c.execute('UPDATE campaigns SET updated_at=now() WHERE id=%s', (campaign_id,))


def enqueue(c, campaign_id, kind, key, payload=None):
    c.execute('INSERT INTO jobs(id,campaign_id,kind,job_key,payload) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(campaign_id,kind,job_key) DO NOTHING',
              (uuid4(), campaign_id, kind, key, Jsonb(payload or {})))


def capability_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class LostLease(Exception):
    pass


class BudgetExhausted(Exception):
    pass


def require_lease(c, job_id, version, *, lock=False):
    if lock:
        # One order for every campaign mutation: campaign -> job -> lead.
        # Shutdown may fence sibling jobs without deadlocking their commits.
        row = c.execute('SELECT campaign_id FROM jobs WHERE id=%s', (job_id,)).fetchone()
        if not row:
            raise LostLease('Unknown task.')
        c.execute('SELECT id FROM campaigns WHERE id=%s FOR UPDATE', (row['campaign_id'],))
    suffix = ' FOR UPDATE OF j' if lock else ''
    job = c.execute("SELECT j.* FROM jobs j JOIN campaigns ca ON ca.id=j.campaign_id WHERE j.id=%s AND j.lease_version=%s AND j.status='running' AND j.lease_until>clock_timestamp() AND ca.status NOT IN ('cancelled','budget_exhausted')" + suffix,
                    (job_id, version)).fetchone()
    if not job:
        raise LostLease('The task lease expired or was cancelled.')
    return job


def authorize_capability(c, token):
    job = c.execute("SELECT j.* FROM jobs j JOIN campaigns ca ON ca.id=j.campaign_id WHERE j.capability_hash=%s AND j.status='running' AND j.lease_until>clock_timestamp() AND ca.status NOT IN ('cancelled','budget_exhausted')", (capability_hash(token),)).fetchone()
    if not job:
        raise LostLease('Expired or unknown research capability.')
    return job


def reserve(c, provider, units, job=None, *, scope=None):
    if provider not in ('model', 'firecrawl') or type(units) is not int or units < 1:
        raise ValueError('A known provider and positive integer reservation are required.')
    scope = scope or settings.budget_scope
    column, maximum = ('model_calls', settings.max_calls) if provider == 'model' else ('firecrawl_credits', settings.max_credits)
    # Field names are fixed application constants, never agent-controlled SQL.
    row = c.execute(f'UPDATE budget SET {column}={column}+%s WHERE name=%s AND (NOT %s OR {column}+%s<=%s) RETURNING *',
                    (units, scope, settings.budget_limits_enabled, units, maximum)).fetchone()
    if not row:
        raise BudgetExhausted(f'{provider} budget exhausted; no request was sent.')
    reservation = uuid4()
    c.execute('INSERT INTO provider_requests(id,scope,job_id,provider,units) VALUES (%s,%s,%s,%s,%s)', (reservation, scope, job['id'] if job else None, provider, units))
    return reservation


if __name__ == '__main__':
    migrate()
    print('Database migrations applied.')
