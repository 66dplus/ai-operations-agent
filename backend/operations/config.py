import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'dbname=ai_operations_local')
    origin: str = os.getenv('APP_ORIGIN', 'http://localhost:3000')
    internal_token: str = os.getenv('INTERNAL_TOKEN', '')
    opencode_url: str = os.getenv('OPENCODE_URL', 'http://127.0.0.1:4096')
    opencode_directory: str = os.getenv('OPENCODE_DIRECTORY', str(Path('runtime/agent').resolve()))
    model: str = os.getenv('AI_MODEL', 'deepseek-v4.1-flash')
    provider: str = os.getenv('AI_PROVIDER', 'opencode-go')
    budget_scope: str = os.getenv('BUDGET_SCOPE', 'acceptance')
    max_calls: int = int(os.getenv('MAX_MODEL_CALLS', '100'))
    max_credits: int = int(os.getenv('MAX_FIRECRAWL_CREDITS', '250'))
    lease_seconds: int = int(os.getenv('LEASE_SECONDS', '60'))
    go_balance_disabled: bool = os.getenv('GO_BALANCE_DISABLED', '').lower() == 'true'
    live_enabled: bool = os.getenv('LIVE_ENABLED', '').lower() == 'true'
    runtime_verified: bool = os.getenv('RUNTIME_VERIFIED', '').lower() == 'true'
    gateway_url: str = os.getenv('GATEWAY_URL', 'http://127.0.0.1:8010')
    opencode_bin: str = os.getenv('OPENCODE_BIN', str(Path('../runtime-template/node/node_modules/.bin/opencode').resolve()))
    go_key_file: str = os.getenv('GO_KEY_FILE', '')
    firecrawl_key_file: str = os.getenv('FIRECRAWL_KEY_FILE', '')

settings = Settings()


def live_ready() -> bool:
    if not (settings.live_enabled and settings.go_balance_disabled and settings.runtime_verified):
        return False
    import httpx
    try:
        response = httpx.get(settings.gateway_url + '/health', timeout=2)
        return response.status_code == 200 and response.json().get('ready') is True
    except (httpx.HTTPError, ValueError):
        return False
