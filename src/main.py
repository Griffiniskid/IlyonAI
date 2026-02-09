"""
Ilyon AI - Main entry point for the Web API.
"""

import logging
import sys
from aiohttp import web

from src.config import settings
from src.api.app import create_api_app

def setup_logging():
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%H:%M:%S',
        force=True
    )
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

async def on_startup(app: web.Application):
    logger = logging.getLogger('Ilyon_AI')
    logger.info("🛡️  ILYON AI API - Starting Up")

    # Initialize database
    try:
        from src.storage.database import init_database
        await init_database()
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}")

    # Initialize cache
    try:
        from src.storage.cache import init_cache
        await init_cache()
    except Exception as e:
        logger.warning(f"Cache initialization failed: {e}")

    logger.info(f"✅ API Server ready on port {settings.web_api_port}")

async def on_cleanup(app: web.Application):
    logger = logging.getLogger('Ilyon_AI')
    logger.info("🛡️  ILYON AI API - Shutting Down")
    
    try:
        from src.storage.database import get_database
        db = await get_database()
        await db.close()
    except Exception:
        pass

def main():
    setup_logging()
    app = create_api_app()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    web.run_app(
        app, 
        host=settings.web_api_host, 
        port=settings.web_api_port,
        print=None
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
