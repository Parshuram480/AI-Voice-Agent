import yaml
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_PROMPTS_CACHE = None

def get_prompts() -> dict:
    """
    Loads and caches the centralized prompts from prompts.yaml.
    """
    global _PROMPTS_CACHE
    if _PROMPTS_CACHE is None:
        try:
            # We assume the working directory is the root of the project
            config_path = Path("app/config/prompts.yaml")
            with open(config_path, "r", encoding="utf-8") as f:
                _PROMPTS_CACHE = yaml.safe_load(f)
            logger.info("Successfully loaded prompts from app/config/prompts.yaml")
        except Exception as e:
            logger.error(f"Failed to load prompts.yaml: {e}")
            _PROMPTS_CACHE = {}
    
    return _PROMPTS_CACHE
