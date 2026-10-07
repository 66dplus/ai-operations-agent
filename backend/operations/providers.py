"""Credential-owning gateway services. Every dispatch follows a durable reservation."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import time
from contextlib import contextmanager
from urllib.parse import urlparse, urlunparse
import httpx
from psycopg.types.json import Jsonb
from . import db, service
from .config import settings


class ProviderError(Exception):
    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = retryable


def credential(provider):
    if provider == 'go':
        direct = os.getenv('OPENCODE_GO_API_KEY')
        path = settings.go_key_file
        if direct:
            return direct
        if path:
            return json.loads(Path(path).read_text())['opencode-go']['key']
    elif provider == 'firecrawl':
        direct = os.getenv('FIRECRAWL_API_KEY')
        path = settings.firecrawl_key_file
        if direct:
            return direct
        if path:
            return json.loads(Path(path).read_text())['apiKey']
    raise ProviderError(f'{provider} credential is not configured.')


def public_url(url):
    p = urlparse(url)
    host = service.normalized_domain(url)
    if p.scheme not in ('http', 'https') or p.port not in (None, 80, 443):
        raise ValueError('Only public HTTP(S) pages on standard ports are allowed.')
    if host.endswith(('.local', '.internal', '.example')) or p.path.lower().endswith('.pdf'):
        raise ValueError('A public HTML company page is required.')
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ProviderError('Company domain could not be resolved.', retryable=True) from error
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError('Private, loopback and link-local targets are forbidden.')
    return urlunparse(p._replace(fragment=''))


def lease(token, *, session=None, reserve_provider=None, units=1):
    with db.connect() as c:
        initial = db.authorize_capability(c, token)
        job = db.require_lease(c, initial['id'], initial['lease_version'], lock=True)
        mode = c.execute('SELECT mode FROM campaigns WHERE id=%s', (job['campaign_id'],)).fetchone()['mode']
        if mode == 'live' and not (settings.live_enabled and settings.go_balance_disabled and settings.runtime_verified):
            raise db.LostLease('Live dispatch is disabled; no provider request was sent.')
        if session is not None and (not job['session_id'] or job['session_id'] != session):
            raise db.LostLease('This OpenCode session does not own the task.')
        reservation = db.reserve(c, reserve_provider, units, job) if reserve_provider else None
    # The transaction is committed before a provider can receive a request.
    return job, reservation


def receipt(reservation, status, usage):
    with db.connect() as c:
        c.execute('UPDATE provider_requests SET status=%s,usage=%s WHERE id=%s',
                  (status, Jsonb(usage), reservation))


@contextmanager
def firecrawl_slot(token):
    # Session advisory locks bound concurrency across all processes and replicas.
    with db.connect() as c:
        deadline = time.monotonic() + 90
        slot = None
        while slot is None:
            lease(token)
            for candidate in range(2):
                if c.execute('SELECT pg_try_advisory_lock(174014,%s) AS acquired', (candidate,)).fetchone()['acquired']:
                    slot = candidate
                    break
            if slot is None:
                if time.monotonic() >= deadline:
                    raise ProviderError('Firecrawl concurrency timeout.', retryable=True)
                time.sleep(.2)
        try:
            yield
        finally:
            c.execute('SELECT pg_advisory_unlock(174014,%s)', (slot,))


def firecrawl(token, endpoint, body, units):
    key = credential('firecrawl')
    with firecrawl_slot(token):
        job, reservation = lease(token, reserve_provider='firecrawl', units=units)
        lease(token)
        try:
            response = httpx.post('https://api.firecrawl.dev/v2/' + endpoint, json=body,
                                  headers={'Authorization': 'Bearer ' + key}, timeout=90)
        except httpx.HTTPError as error:
            # Unknown delivery outcomes retain their full reservation.
            raise ProviderError('Firecrawl transport timeout or connection failure.', retryable=True) from error
        receipt(reservation, 'received', {'http_status': response.status_code, 'reserved_credits': units})
        if response.status_code != 200:
            raise ProviderError(f'Firecrawl returned HTTP {response.status_code}.',
                                retryable=response.status_code == 429 or response.status_code >= 500)
        try:
            data = response.json()
        except ValueError as error:
            raise ProviderError('Firecrawl returned invalid JSON.') from error
        if not isinstance(data, dict) or not data.get('success') or not isinstance(data.get('data'), (dict,list)):
            raise ProviderError('Firecrawl could not retrieve this public page.')
        with db.connect() as c:
            db.require_lease(c, job['id'], job['lease_version'], lock=True)
            db.log(c, job['campaign_id'], endpoint, 'received', f'Firecrawl {endpoint}: {units} credits reserved.',
                   job_id=job['id'], attempt=job['attempts'])
        return data['data']


def search(token, query, limit=10):
    job, _ = lease(token)
    if job['kind'] != 'discovery':
        raise ValueError('Search is available only during company discovery.')
    if type(limit) is not int or not 1 <= limit <= 100 or not 2 <= len(query) <= 500:
        raise ValueError('Search needs a short query and 1–100 results.')
    data = firecrawl(token, 'search', {'query': query, 'limit': limit, 'sources': ['web'], 'timeout': 60000},
                     2 * ((limit + 9) // 10))
    # Search snippets are untrusted discovery hints, never qualification evidence.
    return data.get('web', []) if isinstance(data, dict) else data


def task_context(token):
    job, _ = lease(token)
    with db.connect() as c:
        ca = c.execute('SELECT query,target_count,criteria FROM campaigns WHERE id=%s', (job['campaign_id'],)).fetchone()
        leads = []
        for lead_id in job['payload'].get('lead_ids', []):
            lead = c.execute('SELECT id,company_name,domain FROM leads WHERE id=%s AND campaign_id=%s', (lead_id, job['campaign_id'])).fetchone()
            lead['sources'] = c.execute('SELECT id,url,title,content FROM sources WHERE lead_id=%s', (lead_id,)).fetchall()
            leads.append(lead)
    return {'step': job['kind'], **ca, 'leads': leads}


def fetch_page(token, lead_id, url):
    job, _ = lease(token)
    if job['kind'] != 'research' or str(lead_id) not in job['payload'].get('lead_ids', []):
        raise ValueError('This company is outside the research task.')
    url = public_url(url)
    with db.connect() as c:
        db.require_lease(c, job['id'], job['lease_version'], lock=True)
        lead = c.execute('SELECT * FROM leads WHERE id=%s FOR UPDATE', (lead_id,)).fetchone()
        if service.normalized_domain(url) != lead['domain']:
            raise ValueError('Fetch is limited to this company domain.')
        existing = c.execute('SELECT * FROM sources WHERE lead_id=%s AND url=%s', (lead_id, url)).fetchone()
        if existing:
            return existing
        if lead['qualification']:
            raise ValueError('Verified company evidence is immutable under research retries.')
        count = c.execute('SELECT count(*) AS n FROM page_fetches WHERE lead_id=%s', (lead_id,)).fetchone()['n']
        recorded = c.execute('SELECT 1 FROM page_fetches WHERE lead_id=%s AND url=%s', (lead_id, url)).fetchone()
        if count >= 3 and not recorded:
            raise ValueError('Three distinct pages per company is the maximum.')
        c.execute('INSERT INTO page_fetches(lead_id,url) VALUES (%s,%s) ON CONFLICT DO NOTHING', (lead_id,url))
        cached = c.execute("SELECT * FROM source_cache WHERE url=%s AND fetched_at>now()-interval '24 hours'", (url,)).fetchone()
        if cached:
            return service.add_source(c, job, lead_id, url, cached['title'], cached['content'])
    data = firecrawl(token, 'scrape', {'url': url, 'formats': ['markdown'], 'onlyMainContent': True,
                                     'parsers': [], 'timeout': 60000, 'maxAge': 0}, 1)
    if not isinstance(data, dict) or not isinstance(data.get('markdown'), str):
        raise ProviderError('Firecrawl returned an invalid page payload.')
    metadata = data.get('metadata', {})
    if not isinstance(metadata, dict):
        raise ProviderError('Firecrawl returned invalid page metadata.')
    redirected = metadata.get('sourceURL', url)
    if service.normalized_domain(public_url(redirected)) != lead['domain']:
        raise ProviderError('The page redirected outside the company domain.')
    content = data.get('markdown', '')
    if metadata.get('statusCode', 200) >= 400 or len(content.strip()) < 80:
        raise ProviderError('This page has no usable public company evidence.')
    # shortcut: a snapshot is capped at 24k characters; add chunked retrieval for larger sites.
    content = content[:24000]
    title = str(metadata.get('title') or lead['company_name'])[:500]
    digest = hashlib.sha256(content.encode()).hexdigest()
    with db.connect() as c:
        db.require_lease(c, job['id'], job['lease_version'], lock=True)
        c.execute('INSERT INTO source_cache(url,title,content,content_hash) VALUES (%s,%s,%s,%s) ON CONFLICT(url) DO UPDATE SET title=EXCLUDED.title,content=EXCLUDED.content,content_hash=EXCLUDED.content_hash,fetched_at=now()', (url,title,content,digest))
        return service.add_source(c, job, lead_id, url, title, content)
