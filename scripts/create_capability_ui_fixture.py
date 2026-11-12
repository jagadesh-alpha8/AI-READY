"""Synthetic browser fixture only. No database queries or model calls; not a quality benchmark."""
import os,sys,json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,'backend'); os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
import django;django.setup()
from types import SimpleNamespace
from apps.scoring.capability.engine import release,assess
from apps.scoring.capability.planning import actions_for,roadmap
from apps.scoring.capability.storage import digest
from apps.scoring.capability.recommendations import build_inputs
rubric=release(); decisions={c['id']: ('met' if n<8 else 'unknown') for n,i in enumerate(rubric['indicators']) for c in i['conditions']}
result=assess(decisions,rubric);records=[{'condition_id':cid,'state':state,'reason':'Synthetic UI fixture; no real institutional evidence.','citations':[]} for cid,state in decisions.items()]
inputs={'profile':{'name':'Synthetic College — UI Test','institution_type':'university','student_count':None,'faculty_count':None},'population':'All faculty and students','reference_period':'2025–26','rubric':rubric,'sources':[]}
run=SimpleNamespace(inputs=inputs,inputs_hash=digest(inputs));payload={'result':result,'records':records,'actions':actions_for(result),'pathways':[roadmap(decisions,t['name'],rubric) for t in rubric['tiers']],'inputs_hash':run.inputs_hash}
plan=build_inputs(run,SimpleNamespace(pk=1,payload=payload),{})
obj={'id':'11111111-1111-4111-8111-111111111111','status':'completed','created_at':'2026-10-30T10:00:00Z','requests_reserved':0,'reserved_cost_usd':'0','inputs_hash':run.inputs_hash,'profile':inputs['profile'],'population':inputs['population'],'reference_period':inputs['reference_period'],'source_manifest':[],'assessment':payload,'deterministic_plan':plan,'partial_decisions':[],'error':None}
if len(sys.argv) != 2:
    raise SystemExit('Usage: python scripts/create_capability_ui_fixture.py /absolute/path/to/synthetic-fixture.json')
Path(sys.argv[1]).write_text(json.dumps(obj))
