"""Download only the exact files declared by the assignment and verify SHA-256."""
import json,hashlib,os
from pathlib import Path
os.environ.setdefault('HF_HOME','.cache/huggingface')
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
from huggingface_hub import hf_hub_download
manifest=json.loads(Path('Day3/Day3_Resources/embedding_model_manifest.json').read_text())
root=Path('Day3/Day3_Resources/embedding_model')
for f in manifest['files']:
    path=root/f['path']
    def valid(): return path.exists() and path.stat().st_size==f['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
    if not valid():
        hf_hub_download(repo_id=manifest['model_id'],revision=manifest['revision'],filename=f['path'],local_dir=root)
    if not valid(): raise RuntimeError('Integrity check failed: '+f['path'])
    print('Verified',f['path'],flush=True)
print('All declared model files verified.')
