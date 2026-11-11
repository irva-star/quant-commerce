import pytest
from backend import config

@pytest.fixture(autouse=True)
def isolate_storage(tmp_path,monkeypatch):
    from backend import storage,extractor,epistemic,channel3
    for module in (config,storage,extractor,epistemic,channel3):
        monkeypatch.setattr(module,'DATA',tmp_path)
    for key in ('CHANNEL3_API_KEY','LLM_API_KEY','PAYPAL_CLIENT_ID','PAYPAL_CLIENT_SECRET'):
        monkeypatch.setenv(key,'')
