export type Evidence = { source_id:string; quote:string; claim:string };
export type Lead = {
  id:string; company_name:string; domain:string; status:string; error:string|null; qualified:boolean;
  enrichment:{ industry:string; summary:string; product:string; geography:string; signals:string[] }|null;
  qualification:{ score:number; verdict:string; reasons:string[]; evidence:Evidence[] }|null;
  current_revision:number|null; review_status:'pending'|'approved'|'rejected'; approved_revision:number|null;
  subject:string|null; body:string|null;
  sources:{ id:string; url:string; title:string; content:string; content_hash:string; fetched_at:string }[];
};
export type Campaign = { id:string; query:string; mode:'demo'|'live'; status:string; target_count:number; error:string|null; created_at:string; criteria:{ title?:string; geography?:string; ideal_customer?:string } };
export type Snapshot = { campaign:Campaign; leads:Lead[]; logs:{ id:number; step:string; status:string; attempt:number; detail:string; created_at:string; metadata:Record<string,unknown> }[]; budget:{ model_calls:number; firecrawl_credits:number }; counts:{ discovered:number; processed:number; qualified:number; approved:number; failed:number } };
