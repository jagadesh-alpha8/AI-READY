"""Download bge-small (fastembed's ONNX build) once at image build time and copy its files to a fixed folder.

    python scripts/bake_embedding_model.py /opt/embeddings/bge-small-en-v1.5

Fails (exit 1) unless the folder ends up with an ONNX model and tokenizer.json and the model embeds a test sentence
from those files alone, so a broken download breaks the image build, not a run.
"""
import shutil
import sys
import tempfile
from pathlib import Path

MODEL = 'BAAI/bge-small-en-v1.5'


def main(target):
    from fastembed import TextEmbedding
    target = Path(target)
    with tempfile.TemporaryDirectory() as cache:
        model = TextEmbedding(MODEL, cache_dir=cache)
        source = Path(model.model._model_dir)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, symlinks=False)   # the hub cache holds symlinks: copy the files themselves
    if not (target / 'tokenizer.json').is_file() or not any(target.rglob('*.onnx')):
        sys.exit(f'{target}: model files incomplete')
    check = TextEmbedding(MODEL, specific_model_path=str(target), local_files_only=True)
    vector = next(iter(check.embed(['The institution keeps student records in an ERP system.'])))
    if len(vector) != 384:
        sys.exit(f'{target}: unexpected vector size {len(vector)}')
    print(f'Baked {MODEL} into {target} ({sum(p.stat().st_size for p in target.rglob("*") if p.is_file()):,} bytes).')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/opt/embeddings/bge-small-en-v1.5')
