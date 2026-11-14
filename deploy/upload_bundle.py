"""Upload the demo data bundle to the public Hugging Face dataset the hosted build downloads from (D-037).
Resumable: re-running continues an interrupted upload instead of starting over."""
import time
from huggingface_hub import HfApi

REPO = "mithilyr/meeting-memory-demo-data"
api = HfApi()
api.create_repo(REPO, repo_type="dataset", exist_ok=True)
start = time.time()
api.upload_file(path_or_fileobj="deploy/memory-bundle.tar.gz", path_in_repo="memory-bundle.tar.gz", repo_id=REPO,
                repo_type="dataset", commit_message="Demo data for the hosted read-only app (D-037)")
print(f"UPLOADED in {time.time() - start:.0f}s")
