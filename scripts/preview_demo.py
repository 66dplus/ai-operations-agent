"""Serve the recorded assets locally with HTTP byte ranges for video seeking."""
from pathlib import Path
from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
assets = Path(__file__).resolve().parents[1] / 'docs/verification'
app.mount('/', StaticFiles(directory=assets, html=True))
