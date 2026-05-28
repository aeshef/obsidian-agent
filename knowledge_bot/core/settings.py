"""Planning bot module."""
from pathlib import Path
from functools import lru_cache
from shared.prompts import load_prompt
from shared.yaml_config import load_merged_config
__all__ = ['load_prompt', 'get_config_path', 'get_asr_config']

def get_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / 'config'

@lru_cache(maxsize=1)
def get_asr_config() -> dict:
    return load_merged_config(str(get_config_path()), "asr_config")