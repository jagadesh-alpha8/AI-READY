import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError


class Command(BaseCommand):
    help='Offline requirement-owned packet ablation, without evaluator calls or database writes.'

    def add_arguments(self,parser):
        parser.add_argument('--replay-inputs',required=True)
        parser.add_argument('--evidence-cases',required=True)
        parser.add_argument('--output',required=True)
        parser.add_argument('--budget',type=int,default=18000)

    def handle(self,*args,**options):
        from apps.scoring.capability.packet_experiment import compare_packets
        from apps.scoring.capability.semantic_retrieval import configured_policy,ranker_for
        target=Path(options['output']).resolve();repo=Path(settings.BASE_DIR).resolve().parent
        if target.exists() or target==repo or repo in target.parents or not 100<=options['budget']<=100000:
            raise CommandError('Choose an unused private output outside the repository and a budget of 100–100000.')
        replay=json.loads(Path(options['replay_inputs']).read_text())['replay_inputs']
        cases=json.loads(Path(options['evidence_cases']).read_text());policy=configured_policy(mode='hybrid')
        result=compare_packets(replay,cases,ranker_for(policy),budget=options['budget'],
            progress=lambda code:self.stdout.write('Packed '+code))
        result['semantic_policy']=policy
        with target.open('x') as handle:json.dump(result,handle,indent=2)
        self.stdout.write('Private offline comparison complete; no evaluator requests or database writes.')
