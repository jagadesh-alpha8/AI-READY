"""The back end with the product-flow test's stand-in model, for an end-to-end rehearsal of the front end.

No network, no model credits, no Celery worker or beat: every background task (assessment, second-layer jobs,
recommendations, plan evaluation, document extraction) runs inline when it is dispatched, and every model call is
answered by the stand-in in apps/scoring/test_product_flow.py, which cites only text it was sent, so citations survive
publication. Requests with a schema the stand-in does not know (document classification, fact extraction) get the
smallest answer the schema allows.

Usage (from the repository root):
    python scripts/rehearsal/standin_server.py [--port 8000] [--db /tmp/rehearsal.sqlite3]

It creates a fresh SQLite database each time with one college, one sprint, a three-page self-study report and a
coordinator who signs in as rehearsal@example.com / rehearsal-pass-1. Then run the front end's production build
against it (`npm run build && npx vite preview`, which proxies /api to port 8000) and scripts/rehearsal/rehearse.mjs.
Never point this at a real database: it patches the model service for the whole process.
"""
import argparse
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
EMAIL, PASSWORD = 'rehearsal@example.com', 'rehearsal-pass-1'


def blank(schema, defs=None):
    """The smallest value a JSON schema allows: required properties only, empty arrays, first enum values, and a short
    non-empty string (validators refuse blank reasons)."""
    defs = defs if defs is not None else schema.get('$defs') or schema.get('definitions') or {}
    if '$ref' in schema:
        return blank(defs[schema['$ref'].split('/')[-1]], defs)
    for key in ('anyOf', 'oneOf'):
        if key in schema:
            options = schema[key]
            nullable = [o for o in options if o.get('type') == 'null']
            return None if nullable else blank(options[0], defs)
    kind = schema.get('type')
    if isinstance(kind, list):
        if 'null' in kind:
            return None
        kind = kind[0]
    if 'enum' in schema:
        return schema['enum'][0]
    if kind == 'object':
        props = schema.get('properties') or {}
        return {name: blank(props[name], defs) for name in schema.get('required') or [] if name in props}
    if kind == 'array':
        return []
    if kind in ('number', 'integer'):
        return schema.get('minimum', 0)
    if kind == 'boolean':
        return False
    return 'Stand-in.'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='8000')
    parser.add_argument('--db', default='/tmp/ai-ready-rehearsal.sqlite3')
    args = parser.parse_args()

    db = Path(args.db)
    if db.exists():
        db.unlink()
    os.environ['DATABASE_URL'] = f'sqlite:///{db}'
    os.environ.setdefault('SECRET_KEY', 'rehearsal-only')
    os.environ.setdefault('DEBUG', 'True')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)

    import django
    django.setup()
    from django.core.management import call_command
    from django.test.utils import override_settings

    from apps.scoring.test_product_flow import PAGES, SETTINGS, ProductFlowTests
    override_settings(**SETTINGS, CAPABILITY_PLANS_ENABLED=True, SECOND_LAYER_EXPLAIN_AFTER_PUBLISH=True,
                      MEDIA_ROOT=str(db.with_suffix('.media'))).enable()
    from config.celery import app as celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

    call_command('migrate', verbosity=0)

    # ------------------------------------------------------------------ the stand-in model
    standin = ProductFlowTests.__new__(ProductFlowTests)
    from apps.scoring.capability.engine import release
    standin.credited = {i['code'] for i in release()['indicators']}
    standin.credited = set(sorted(standin.credited)[:6])
    standin.contradict, standin.schemas = set(), []
    lock = threading.Lock()

    def model(**kwargs):
        fmt = kwargs.get('response_format') or {}
        spec = fmt.get('json_schema') or {}
        name = spec.get('name', '')
        with lock:
            reply = getattr(standin, 'reply_' + name, None)
            if reply is not None:
                body = reply(json.loads(kwargs['messages'][1]['content']))
            else:
                body = blank(spec.get('schema') or {'type': 'object'})
        print(f'[stand-in] {name or "unnamed request"}', flush=True)
        return SimpleNamespace(model='stand-in', usage=SimpleNamespace(
            prompt_tokens=400, completion_tokens=200, prompt_tokens_details=None, completion_tokens_details=None,
            total_tokens=600), choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(
                content=json.dumps(body), refusal=None))])

    sdk = MagicMock()
    sdk.with_options.return_value = sdk
    sdk.chat.completions.create.side_effect = model
    from apps.extraction.services import ai_service
    from apps.extraction.services.openai_client import OpenAIExtractionService
    original = ai_service.get_ai_service

    def get_ai_service(*args, **kwargs):
        return OpenAIExtractionService(api_key='sk-rehearsal', model='test-model', client=sdk)

    # Patched at the source first, so modules imported later (views load on the first request) take the stand-in;
    # then every module that already imported get_ai_service / get_router_pool by name.
    from apps.extraction.services import router_pool
    import apps.extraction.services as services_package
    ai_service.get_ai_service = get_ai_service
    router_pool.get_router_pool = lambda *a, **k: None
    if getattr(services_package, 'get_ai_service', None) is original:
        services_package.get_ai_service = get_ai_service
    patched = 0
    for module in list(sys.modules.values()):
        name = getattr(module, '__name__', '') or ''
        if not name.startswith('apps.') or name == 'apps.extraction.services.router_pool':
            continue
        if getattr(module, 'get_ai_service', None) is original:
            module.get_ai_service = get_ai_service
            patched += 1
        if hasattr(module, 'get_router_pool'):
            module.get_router_pool = lambda *a, **k: None
    print(f'[rehearsal] stand-in model patched into {patched} modules', flush=True)

    # ------------------------------------------------------------------ one college
    from apps.accounts.models import User
    from apps.documents.models import Document
    from apps.extraction.models import DocumentPage
    from apps.institutions.models import Institution
    from apps.sprints.models import Sprint
    institution = Institution.objects.create(name='Rehearsal College', institution_type='university')
    sprint = Sprint.objects.create(institution=institution, name='Rehearsal sprint', academic_year='2024-25')
    User.objects.create_user(username='rehearsal', email=EMAIL, password=PASSWORD, first_name='Rehearsal',
                             role=User.Role.IQAC_COORDINATOR, institution=institution)
    ssr = Document.objects.create(sprint=sprint, document_type='naac_ssr', status='processed',
                                  processing_status='processed', title='Self-study report',
                                  original_filename='self-study-report.pdf', page_count=len(PAGES))
    for n, text in enumerate(PAGES, 1):
        DocumentPage.objects.create(document=ssr, page_number=n, text=text)
    print(f'[rehearsal] sprint {sprint.pk}; sign in as {EMAIL} / {PASSWORD}', flush=True)

    call_command('runserver', f'127.0.0.1:{args.port}', use_reloader=False, use_threading=False)


if __name__ == '__main__':
    main()
