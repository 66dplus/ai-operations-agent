import os
from dataclasses import replace
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from operations import api, config, db, queue, service

@pytest.fixture(autouse=True)
def database(monkeypatch):
    # Each test owns a fresh schema in PostgreSQL; no truncation of app/shared data.
    base=os.getenv('TEST_DATABASE_URL','dbname=ai_operations_local')
    schema='test_'+uuid4().hex
    with psycopg.connect(base,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    override=replace(config.settings,database_url=make_conninfo(base,options=f'-c search_path={schema}'),budget_scope='test',live_enabled=False,budget_limits_enabled=True)
    for module in (config,db,queue,service,api):
        monkeypatch.setattr(module,'settings',override)
    monkeypatch.setenv('DEMO_STEP_DELAY','0')
    db.migrate()
    yield override
    with psycopg.connect(base,autocommit=True) as c:
        c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
