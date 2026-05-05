import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def sync_youtube_playlist():
    """
    Weekly background task to synchronize Preethaji & Krishnaji YouTube playlists (BE-5).
    """
    logger.info("Starting weekly YouTube playlist auto-sync...")
    try:
        from app.dependencies import get_container
        container = get_container()
        
        # O&O Channel URL
        playlist_url = "https://www.youtube.com/@theonenessmovement/videos"
        
        # We start the ingestion asynchronously. 
        # ingest_url will discover videos and skip already indexed ones.
        await container.ingestion.ingest_url(
            url=playlist_url,
            max_accuracy=False,  # faster sync mode
            on_progress=lambda msg, pct: logger.info(f"Auto-Sync: {msg} ({pct*100:.1f}%)")
        )
        # Invalidate semantic cache after new data
        from app.main import response_cache
        response_cache.invalidate_all()
        
        logger.info("Weekly YouTube playlist sync completed successfully.")
        
    except Exception as e:
        logger.error(f"Weekly YouTube playlist sync failed: {e}", exc_info=True)

def start_scheduler():
    """Start the APScheduler for recurring background tasks."""
    # Run every Sunday at 02:00 AM
    scheduler.add_job(
        sync_youtube_playlist,
        CronTrigger(day_of_week='sun', hour=2, minute=0, timezone='UTC'),
        id="weekly_youtube_sync",
        replace_existing=True
    )
    scheduler.start()
    logger.info("APScheduler started (Weekly sync configured for Sunday 02:00 AM)")

def shutdown_scheduler():
    """Gracefully shutdown the scheduler."""
    scheduler.shutdown()
    logger.info("APScheduler stopped")
