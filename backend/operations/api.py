import asyncio
import json
from contextlib import asynccontextmanager
from uuid import UUID
from fastapi import FastAPI, Header, Request, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from . import db, service
from .config import settings, live_ready
from .schemas import CampaignCreate, DraftEdit, Review

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(db.migrate)
    yield

app = FastAPI(title='AI Operations Agent', lifespan=lifespan)

@app.middleware('http')
async def check_origin(request: Request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin') != settings.origin:
        return JSONResponse({'detail':'This action must originate from the configured application address.'},status_code=403)
    # The internal service credential never authorizes human review actions.
    if request.headers.get('authorization'):
        return JSONResponse({'detail':'Agent credentials cannot access the user API.'},status_code=403)
    return await call_next(request)

@app.get('/api/health')
def health():
    return {'ok':True,'live_available':live_ready(),'model':settings.model}

@app.post('/api/campaigns',status_code=201)
def create(body:CampaignCreate,idempotency_key:str=Header(min_length=8,max_length=120)):
    return service.create_campaign(body,idempotency_key)

@app.get('/api/campaigns')
def recent():
    with db.connect() as c:
        # shortcut: single-user MVP loads its complete history; add cursor
        # pagination when histories grow, without making older runs inaccessible.
        return c.execute('SELECT * FROM campaigns ORDER BY created_at DESC').fetchall()

@app.get('/api/campaigns/{campaign_id}')
def snapshot(campaign_id:UUID):
    return service.snapshot(campaign_id)

@app.get('/api/campaigns/{campaign_id}/events')
async def events(campaign_id:UUID,request:Request):
    await asyncio.to_thread(service.snapshot,campaign_id)
    async def generate():
        last = None
        while not await request.is_disconnected():
            state=await asyncio.to_thread(service.snapshot,campaign_id)
            encoded=json.dumps(state,default=str,ensure_ascii=False)
            if encoded!=last:
                yield f'data: {encoded}\n\n'
                last=encoded
            else:
                yield ': heartbeat\n\n'
            if state['campaign']['status'] in ('completed','partial','cancelled','budget_exhausted'):
                return
            await asyncio.sleep(1)
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/campaigns/{campaign_id}/cancel')
def cancel(campaign_id:UUID):
    return service.cancel_campaign(campaign_id)

@app.post('/api/campaigns/{campaign_id}/retry')
def retry(campaign_id:UUID):
    return service.retry_campaign(campaign_id)

@app.patch('/api/leads/{lead_id}/draft')
def edit(lead_id:UUID,body:DraftEdit):
    return service.edit_draft(lead_id,body)

@app.post('/api/leads/{lead_id}/review')
def review(lead_id:UUID,body:Review):
    return service.review_draft(lead_id,body)

@app.get('/api/campaigns/{campaign_id}/export')
def export(campaign_id:UUID,format:str='csv'):
    rows=service.export_rows(campaign_id)
    if format=='json':
        return Response(json.dumps(rows,ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="approved-companies.json"'})
    if format!='csv':
        raise HTTPException(422,'Choose csv or json export.')
    return Response(service.csv_export(rows),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="approved-companies.csv"'})
