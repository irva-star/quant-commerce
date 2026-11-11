import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)

def setting(name: str, default: str = '') -> str:
    return os.getenv(name, default)
