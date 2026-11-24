"""Drive the stand-in back end (standin_server.py) through the API to a Stage 1 result, and optionally to a final one,
so the screens can be looked at with data in every state. No browser.

    python scripts/rehearsal/seed_flow.py [--final] [--base http://127.0.0.1:8000]
"""
import argparse
import json
import urllib.request
import uuid

EMAIL, PASSWORD = 'rehearsal@example.com', 'rehearsal-pass-1'


def call(base, method, path, token=None, body=None, key=None):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    if key:
        req.add_header('Idempotency-Key', key)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b'null')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', default='http://127.0.0.1:8000')
    p.add_argument('--final', action='store_true')
    a = p.parse_args()
    token = call(a.base, 'POST', '/api/v1/auth/login', body={'email': EMAIL, 'password': PASSWORD})['access_token']
    sprint = call(a.base, 'GET', '/api/v1/sprints', token)
    sprint = (sprint.get('results') if isinstance(sprint, dict) else sprint)[0]['id']
    base = f'/api/v1/sprints/{sprint}/capability-runs'
    run = call(a.base, 'POST', base, token, {}, key=str(uuid.uuid4()))['id']
    print('Stage 1 run', run, call(a.base, 'GET', f'{base}/{run}', token)['status'])
    jobs = f'{base}/{run}/second-layer/jobs'
    call(a.base, 'POST', jobs, token, {'operation': 'questions'}, key=str(uuid.uuid4()))
    listed = call(a.base, 'GET', f'{base}/{run}/questions?list=1', token)
    qs = [q for q in listed['questions'] if q['status'] == 'open']
    print('questions', len(qs))
    call(a.base, 'POST', f'{base}/{run}/questions/{qs[0]["id"]}/to-check', token, {'to_check': True})
    call(a.base, 'POST', f'{base}/{run}/questions/{qs[1]["id"]}/responses', token, {'choice': 'not_yet', 'answer': 'Planned for 2027.'})
    if a.final:
        call(a.base, 'POST', jobs, token, {'operation': 'rejudge', 'options': {'close': True}}, key=str(uuid.uuid4()))
        print('final published', call(a.base, 'GET', f'{base}/{run}/questions', token)['progress'].get('final_run_id'))


if __name__ == '__main__':
    main()
