import json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # workspace root; repo sits one level down
state_path = ROOT / 'conda/envs/medical_ai_agent/conda-meta/state'
state = json.loads(state_path.read_text(encoding='utf-8'))
for name in ('DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'DEEPSEEK_MODEL'):
    os.environ[name] = state['env_vars'][name]
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
sys.path.insert(0, str(ROOT / 'medical_ai_agent'))
from martin.llm.chat_model import get_chat_model

report = {'python': sys.executable, 'python_version': sys.version.split()[0],
          'base_url': os.environ['DEEPSEEK_BASE_URL'], 'model': os.environ['DEEPSEEK_MODEL'], 'checks': []}
model = get_chat_model(timeout=40, max_retries=0, max_tokens=1024)

def run_check(name, function):
    start = time.monotonic()
    try:
        details = function()
        report['checks'].append({'name': name, 'passed': True, 'seconds': round(time.monotonic()-start, 2), **details})
    except Exception as exc:
        # Only record classified errors, never exception strings, request headers or credentials.
        body = getattr(exc, 'body', {}) or {}
        err = body.get('error', body) if isinstance(body, dict) else {}
        code = err.get('code') if isinstance(err, dict) else None
        report['checks'].append({'name': name, 'passed': False, 'seconds': round(time.monotonic()-start, 2),
                                'error_type': type(exc).__name__, 'status': getattr(exc, 'status_code', None), 'code': code,
                                'cause_type': type(exc.__cause__).__name__ if exc.__cause__ else None})
    print(json.dumps(report['checks'][-1], ensure_ascii=True), flush=True)

def text_check():
    response = model.invoke('Connectivity test with no personal or clinical data. Reply with exactly MARTIN_OK.')
    if 'MARTIN_OK' not in str(response.content):
        raise AssertionError('Expected marker absent')
    return {'expected_marker_received': True, 'reported_model': response.response_metadata.get('model_name')}

def tool_check():
    probe = {'type': 'function', 'function': {'name': 'connectivity_probe', 'description': 'Return a synthetic connectivity marker.',
             'parameters': {'type': 'object', 'properties': {'marker': {'type': 'string'}}, 'required': ['marker']}}}
    response = model.bind_tools([probe], tool_choice='connectivity_probe').invoke('Call connectivity_probe with marker MARTIN_TOOL_OK. No patient data is involved.')
    calls = response.tool_calls
    assert len(calls) == 1 and calls[0]['name'] == 'connectivity_probe'
    assert calls[0]['args'].get('marker') == 'MARTIN_TOOL_OK' and calls[0].get('id')
    return {'tool_name_matched': True, 'arguments_matched': True, 'tool_call_id_present': True}

run_check('martin_chat_model_text', text_check)
if report['checks'][0]['passed']:
    run_check('martin_chat_model_tool_call', tool_check)
Path(ROOT / 'validation' / 'ark-model-smoke.json').write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='utf-8')
sys.exit(0 if all(c['passed'] for c in report['checks']) else 1)