CREATE TABLE page_fetches (
 lead_id uuid NOT NULL REFERENCES leads(id), url text NOT NULL,
 PRIMARY KEY(lead_id,url)
);
CREATE TABLE step_outputs (
 campaign_id uuid NOT NULL REFERENCES campaigns(id), step text NOT NULL, output jsonb NOT NULL,
 PRIMARY KEY(campaign_id,step)
);
ALTER TABLE campaigns ADD COLUMN live_phase text NOT NULL DEFAULT 'all';
