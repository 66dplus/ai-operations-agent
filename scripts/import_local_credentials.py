"""Copy only existing Go/Firecrawl keys to ignored, private runtime files; never print keys."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / 'runtime/credentials'
target.mkdir(parents=True, exist_ok=True, mode=0o700)
target.chmod(0o700)
go_path = Path(os.getenv('GO_AUTH_SOURCE', str(Path.home()/'.local/share/opencode/auth.json')))
fire_path = Path(os.getenv('FIRECRAWL_AUTH_SOURCE', str(Path.home()/'Library/Application Support/firecrawl-cli/credentials.json')))
go = json.loads(go_path.read_text())['opencode-go']['key']
fire = json.loads(fire_path.read_text())['apiKey']
for filename, value in [('go.json', {'opencode-go': {'key':go}}), ('firecrawl.json', {'apiKey':fire})]:
    path = target / filename
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor,'w') as stream:
        json.dump(value,stream)
    path.chmod(0o600)
print('Existing provider keys saved to ignored runtime files. No global configuration changed.')
