"""V1.1 live A (three new threads), C REST/WS, and current-case degradation."""
import json
import re

import store_v1_live_acceptance as h
from martin.memory.output_preferences import answer_length
from websockets.sync.client import connect

h.evidence['version'] = 'V1.1'
h.evidence['scope'] = 'Live A: 3 independent report threads; live C: REST, WebSocket and current-case analysis. B unchanged.'


def check_answer(answer):
    return {
        'Conclusion First': bool(re.match(r'^\s*(?:结论|诊断结论|影像结论)\s*[：:]', answer)),
        'Length <= 200': bool(answer) and answer_length(answer) <= 200,
        'Focus Constraint': '毛刺' in answer,
    }


def check_degraded(answer):
    return {
        'Historical warning': bool(re.search(r'历史|既往|上次', answer)) and bool(re.search(r'不可用|无法|缺失|未能|不能', answer)),
        'No fabricated previous 6mm': not bool(re.search(r'6(?:\.0)?\s*(?:mm|毫米)', answer, re.I)),
        'No fabricated +2mm': not bool(re.search(r'[+＋]\s*2(?:\.0)?\s*(?:mm|毫米)', answer, re.I)),
    }


def run(client):
    login = client.post('/api/auth/login', json={'username':'doctor_a','password':'SyntheticLiveDoctorA!2026'})
    login.raise_for_status()
    h.phase = 'A_thread_A'
    first = h.new_thread(client, 'C002')
    h.chat(client, first, '以后报告请结论前置、200字以内、重点毛刺征。', 'set_preference')
    item = h.get_default_store().get(('doctor','D001','preferences'), 'report_style')
    pref = item.value if item else {}
    trials = []
    for index in range(1, 4):
        h.phase = f'A_report_{index}'
        thread = h.new_thread(client, 'C002')
        response, body = h.chat(client, thread, '生成报告', 'new_thread_report')
        answer = body.get('output', '')
        calls = [c for c in h.evidence['model_calls'] if c['phase'] == h.phase]
        rewrites = [c for c in calls if any('你是格式编辑器' in p for p in c['system_prompts'])]
        checks = {
            'HTTP success': response.status_code == 200,
            'Retrieval': any(x['phase'] == h.phase and x['namespace'] == ['doctor','D001','preferences'] and
                             any(i['key']=='report_style' and i['value']==pref for i in x.get('items',[])) for x in h.evidence['store_reads']),
            'Prompt Injection': any('[DOCTOR OUTPUT PREFERENCES — MUST FOLLOW]' in p and '200' in p and '毛刺' in p for p in h.actual_prompts(h.phase)),
            'Max one rewrite': len(rewrites) <= 1,
            **check_answer(answer),
        }
        trials.append({'thread':thread,'checks':checks,'han_characters':chinese_length(answer),'total_characters':len(answer),'rewrite_count':len(rewrites),
                       'status':'PASS' if all(checks.values()) else 'FAIL'})
        h.flush()
        print(f'A report {index}: '+trials[-1]['status'], flush=True)
    stored = pref.get('conclusion_first') is True and pref.get('max_words')==200 and '毛刺征' in pref.get('focus',[])
    h.evidence['checks']['Doctor Preference']={'status':'PASS' if stored and all(t['status']=='PASS' for t in trials) else 'FAIL',
                                               'saved_by_real_agent':stored,'trials':trials}
    h.flush()

    h.fault = True
    try:
        h.phase='C_store_failure_REST'
        thread=h.new_thread(client,'C002')
        response,body=h.chat(client,thread,'和上次相比有没有变化','store_read_failure')
        answer=body.get('output','')
        checks={'No premature 503':response.status_code==200,
                'LLM still called':any(c['phase']==h.phase for c in h.evidence['model_calls']),
                'Memory status injected':any('[MEMORY STATUS]' in p and 'store_unavailable' in p for p in h.actual_prompts(h.phase)),
                **check_degraded(answer)}
        rest={'checks':checks,'answer':answer,'status':'REVIEW' if all(checks.values()) else 'FAIL'}

        h.phase='C_current_analysis'
        current_thread=h.new_thread(client,'C002')
        rc,bc=h.chat(client,current_thread,'只总结当前病例已确认的结节事实。','current_case_under_store_failure')
        current_answer=bc.get('output','')
        current_ok=rc.status_code==200 and bool(re.search(r'8(?:\.0)?\s*(?:mm|毫米)',current_answer,re.I))

        h.phase='C_store_failure_WS'
        ws_thread=h.new_thread(client,'C002')
        cookie='; '.join(f'{k}={v}' for k,v in client.cookies.items())
        with connect(f'ws://127.0.0.1:8001/api/ws/agent/{ws_thread}',additional_headers={'Cookie':cookie},open_timeout=20) as ws:
            ws.recv(timeout=20)
            ws.send(json.dumps({'message':'和上次相比有没有变化'},ensure_ascii=False))
            events=[]
            while True:
                event=json.loads(ws.recv(timeout=240))
                events.append(event)
                if event['type'] in ('final','error'):
                    break
        final=events[-1]
        h.evidence['http'].append({'phase':h.phase,'label':'websocket','status':101,
                                  'body':{'output':final['content'] if final['type']=='final' else '', 'events':h.clean(events)}})
        ws_checks={'No premature error':final['type']=='final','LLM still called':any(c['phase']==h.phase for c in h.evidence['model_calls']),
                   **check_degraded(final['content'])}
        h.evidence['checks']['Store Failure Degradation']={
            'status':'REVIEW' if all(checks.values()) and current_ok and all(ws_checks.values()) else 'FAIL',
            'REST':rest,'Current analysis':{'passed':current_ok,'answer':current_answer},'WebSocket':{'checks':ws_checks,'answer':final['content']},
            'semantic_review_required':'Ensure no no-change assertion or invented prior value; current 8mm may be stated.'}
        h.flush()
        print('Store Failure Degradation: '+h.evidence['checks']['Store Failure Degradation']['status'],flush=True)
    finally:
        h.fault=False


h.run_scenarios=run
if __name__=='__main__':
    h.main()
