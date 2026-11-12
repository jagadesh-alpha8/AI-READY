"""Explicit operator step; downloading weights is never an assessment side effect."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Prepare a local embedding model and print its directory/hash. Use --download to fetch public weights.'

    def add_arguments(self, parser):
        parser.add_argument('--model', default='BAAI/bge-small-en-v1.5')
        parser.add_argument('--cache-dir', required=True)
        parser.add_argument('--download', action='store_true')

    def handle(self, *args, **options):
        from fastembed import TextEmbedding
        from apps.scoring.capability.semantic_retrieval import artifact_hash
        model = TextEmbedding(options['model'], cache_dir=options['cache_dir'],
                              local_files_only=not options['download'], threads=2)
        directory = model.model._model_dir
        self.stdout.write(f'CAPABILITY_EMBEDDING_PATH={directory}')
        self.stdout.write(f'Artifact SHA256: {artifact_hash(directory)}')
