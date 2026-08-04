"""Service for introspecting databases to map schema for LLMs."""

import logging
from typing import Dict, Any, List
import time

from app.dynamic_db_client import DynamicDbClient

logger = logging.getLogger(__name__)

# Global cache for schema metadata
_schema_cache: Dict[tuple, Dict[str, Any]] = {}
_schema_cache_time: Dict[tuple, float] = {}

class SchemaService:
    """Introspects schema using DynamicDbClient."""

    CACHE_TTL_SECONDS = 1800  # 30 minutes

    def __init__(self, db_config: dict):
        self.db_config = db_config
        self.db_client = DynamicDbClient(db_config)
        self._cache_key = (
            self.db_config.get("db_type", "sqlite"),
            self.db_config.get("server_name", "localhost"),
            self.db_config.get("port", ""),
            self.db_config.get("db_name", ""),
            self.db_config.get("username", "")
        )

    async def get_schema_metadata(self) -> Dict[str, Any]:
        """
        Fetch tables, columns, and foreign keys using the db_client
        and return a structured metadata dictionary. Uses a 30-min TTL cache.
        """
        if self._cache_key in _schema_cache:
            if (time.time() - _schema_cache_time[self._cache_key]) < self.CACHE_TTL_SECONDS:
                logger.info(f"Using cached schema metadata for {self._cache_key[3]}")
                return _schema_cache[self._cache_key]
        
        try:
            metadata = await self.db_client.introspect_schema_full()
            _schema_cache[self._cache_key] = metadata
            _schema_cache_time[self._cache_key] = time.time()
            return metadata
        except Exception as e:
            logger.error(f"Failed to introspect schema: {e}")
            raise e
            
    async def refresh(self) -> Dict[str, Any]:
        """Force-refresh the schema cache."""
        _schema_cache.pop(self._cache_key, None)
        _schema_cache_time.pop(self._cache_key, None)
        return await self.get_schema_metadata()
