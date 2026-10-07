CREATE TABLE IF NOT EXISTS budget (
 name text PRIMARY KEY, model_calls integer NOT NULL DEFAULT 0,
 firecrawl_credits integer NOT NULL DEFAULT 0
);
CREATE TABLE campaigns (
 id uuid PRIMARY KEY, query text NOT NULL, mode text NOT NULL CHECK(mode IN ('demo','live')),
 status text NOT NULL DEFAULT 'queued', target_count integer NOT NULL CHECK(target_count BETWEEN 1 AND 50),
 criteria jsonb NOT NULL DEFAULT '{}', error text, idempotency_key text UNIQUE NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE leads (
 id uuid PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES campaigns(id), company_name text NOT NULL,
 domain text NOT NULL, status text NOT NULL DEFAULT 'discovered', enrichment jsonb, qualification jsonb,
 current_revision integer, review_status text NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','approved','rejected')),
 approved_revision integer, error text, UNIQUE(campaign_id,domain)
);
CREATE TABLE sources (
 id uuid PRIMARY KEY, lead_id uuid NOT NULL REFERENCES leads(id), url text NOT NULL,
 title text NOT NULL, content text NOT NULL, content_hash text NOT NULL, fetched_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(lead_id,url)
);
CREATE TABLE source_cache (
 url text PRIMARY KEY, title text NOT NULL, content text NOT NULL, content_hash text NOT NULL,
 fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE research_cache (
 cache_key text PRIMARY KEY, result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE drafts (
 lead_id uuid NOT NULL REFERENCES leads(id), revision integer NOT NULL, subject text NOT NULL, body text NOT NULL,
 author text NOT NULL CHECK(author IN ('agent','human')), created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(lead_id,revision)
);
CREATE TABLE reviews (
 id bigserial PRIMARY KEY, lead_id uuid NOT NULL, revision integer NOT NULL,
 decision text NOT NULL CHECK(decision IN ('approved','rejected')), created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(lead_id,revision) REFERENCES drafts(lead_id,revision)
);
CREATE TABLE jobs (
 id uuid PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES campaigns(id), kind text NOT NULL,
 job_key text NOT NULL, payload jsonb NOT NULL DEFAULT '{}', status text NOT NULL DEFAULT 'queued',
 attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 lease_version integer NOT NULL DEFAULT 0, lease_until timestamptz, worker_id text,
 capability_hash text, session_id text UNIQUE, error text, UNIQUE(campaign_id,kind,job_key)
);
CREATE INDEX job_queue ON jobs(status,available_at);
CREATE TABLE run_logs (
 id bigserial PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES campaigns(id), lead_id uuid REFERENCES leads(id),
 job_id uuid REFERENCES jobs(id), step text NOT NULL, status text NOT NULL, attempt integer NOT NULL DEFAULT 1,
 detail text NOT NULL DEFAULT '', metadata jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE provider_requests (
 id uuid PRIMARY KEY, scope text NOT NULL REFERENCES budget(name), job_id uuid REFERENCES jobs(id),
 provider text NOT NULL, units integer NOT NULL, status text NOT NULL DEFAULT 'reserved',
 usage jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
