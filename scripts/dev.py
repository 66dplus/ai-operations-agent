"""Run owned development process groups; stop children without touching shared services."""
import os
from pathlib import Path
import signal
import subprocess
import time

root=Path(__file__).resolve().parents[1]
processes=[]
stopping=False

def request_stop(*_):
    global stopping
    stopping=True

signal.signal(signal.SIGINT,request_stop)
signal.signal(signal.SIGTERM,request_stop)
exit_code=0
try:
    commands=[(['uv','run','uvicorn','operations.api:app','--host','127.0.0.1','--port','8000'],root/'backend'),(['uv','run','python','-m','operations.worker'],root/'backend'),(['npm','run','dev'],root/'frontend')]
    if os.getenv('LIVE_ENABLED','').lower()=='true':
        commands.insert(0,(['uv','run','uvicorn','operations.gateway:app','--host','127.0.0.1','--port','8010'],root/'backend'))
    for command,cwd in commands:
        processes.append(subprocess.Popen(command,cwd=cwd,env=os.environ.copy(),start_new_session=True))
    while not stopping and all(p.poll() is None for p in processes):time.sleep(.5)
    if not stopping:
        exit_code=1
        print('A development process exited. See its error above.',flush=True)
finally:
    for process in processes:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    for process in processes:
        try:process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait()
raise SystemExit(exit_code)
