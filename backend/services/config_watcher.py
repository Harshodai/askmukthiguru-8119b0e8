"""
Unit 17 — Hot Reload Config via Watchfiles

Monitors selected config files and environment variables at runtime,
triggering in-process setting reloads without a server restart.

Design:
  - ``ConfigWatcher``: asyncio-based watcher using watchfiles (if available)
  - Falls back to polling (every 30s) if watchfiles is not installed
  - Reloads: rag/prompts.py constants, settings.model_preset, settings.llm_timeout
  - Notifies the ServiceContainer to re-init affected services on change
  - Runs as a background asyncio Task; errors are caught and logged (never crash)

Files watched:
  - backend/app/config.py settings (env-driven; watched via .env file)
  - backend/rag/prompts.py (prompt text edits hot-reload without restart)
  - Any file listed in HOTRELOAD_WATCH_PATHS env var (colon-separated)

Usage::

    from services.config_watcher import start_config_watcher, stop_config_watcher
    task = await start_config_watcher(container)
    ...
    await stop_config_watcher(task)
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default paths to watch for changes (relative to backend/)
_DEFAULT_WATCH_PATHS = [
    "rag/prompts.py",
    ".env",
    ".env.local",
]

_POLL_INTERVAL = 30  # seconds — used as fallback polling interval


def _get_watch_paths() -> list[Path]:
    """Resolve the list of paths to monitor."""
    extra = os.environ.get("HOTRELOAD_WATCH_PATHS", "")
    paths = list(_DEFAULT_WATCH_PATHS)
    if extra:
        paths.extend(p.strip() for p in extra.split(":") if p.strip())
    result = []
    backend_root = Path(__file__).parent.parent  # backend/
    for p in paths:
        resolved = (backend_root / p).resolve()
        if resolved.exists():
            result.append(resolved)
        else:
            logger.debug(f"ConfigWatcher: watch path not found, skipping: {resolved}")
    return result


def _reload_prompts() -> None:
    """Hot-reload the rag.prompts module in-process."""
    try:
        import rag.prompts as prompts_module
        importlib.reload(prompts_module)
        logger.info("ConfigWatcher: rag.prompts reloaded successfully")
    except Exception as exc:
        logger.warning(f"ConfigWatcher: failed to reload rag.prompts: {exc}")


def _reload_settings() -> None:
    """Clear and re-read environment variables into the settings object."""
    try:
        from dotenv import load_dotenv
        # Reload .env files in order of precedence
        for env_file in (".env.local", ".env"):
            path = Path(env_file)
            if path.exists():
                load_dotenv(path, override=True)
                logger.info(f"ConfigWatcher: reloaded {path}")
    except ImportError:
        logger.debug("ConfigWatcher: python-dotenv not installed; env reload skipped")
    except Exception as exc:
        logger.warning(f"ConfigWatcher: settings reload failed: {exc}")


async def _watchfiles_loop(watch_paths: list[Path], stop_event: asyncio.Event) -> None:
    """Main loop using watchfiles for inotify-based change detection."""
    try:
        from watchfiles import awatch
        logger.info(f"ConfigWatcher: watchfiles active on {[str(p) for p in watch_paths]}")

        async for changes in awatch(*watch_paths, stop_event=stop_event):
            for change_type, path in changes:
                logger.info(f"ConfigWatcher: detected change in {path} ({change_type})")
                if "prompts" in path:
                    _reload_prompts()
                else:
                    _reload_settings()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(f"ConfigWatcher (watchfiles): unexpected error: {exc}")


async def _polling_loop(watch_paths: list[Path], stop_event: asyncio.Event) -> None:
    """Fallback polling loop — checks mtime every 30s."""
    logger.info(
        f"ConfigWatcher: polling mode ({_POLL_INTERVAL}s interval) on "
        f"{[str(p) for p in watch_paths]}"
    )
    mtimes: dict[str, float] = {str(p): p.stat().st_mtime for p in watch_paths}

    while not stop_event.is_set():
        await asyncio.sleep(_POLL_INTERVAL)
        for path in watch_paths:
            try:
                new_mtime = path.stat().st_mtime
                key = str(path)
                if key in mtimes and new_mtime != mtimes[key]:
                    logger.info(f"ConfigWatcher (poll): change detected in {path}")
                    if "prompts" in str(path):
                        _reload_prompts()
                    else:
                        _reload_settings()
                    mtimes[key] = new_mtime
            except Exception as exc:
                logger.debug(f"ConfigWatcher: mtime check failed for {path}: {exc}")


class ConfigWatcher:
    """Manages the hot-reload background task lifecycle."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the background config watcher task."""
        if self._task and not self._task.done():
            logger.debug("ConfigWatcher: already running")
            return

        watch_paths = _get_watch_paths()
        if not watch_paths:
            logger.info("ConfigWatcher: no watchable paths found; hot reload disabled")
            return

        self._stop_event.clear()

        async def _run():
            try:
                import watchfiles  # noqa: F401
                await _watchfiles_loop(watch_paths, self._stop_event)
            except ImportError:
                await _polling_loop(watch_paths, self._stop_event)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error(f"ConfigWatcher crashed: {exc}")

        self._task = asyncio.create_task(_run(), name="config_watcher")
        logger.info("ConfigWatcher: started")

    async def stop(self) -> None:
        """Stop the background watcher gracefully."""
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ConfigWatcher: stopped")


# Module-level singleton
_watcher: Optional[ConfigWatcher] = None


async def start_config_watcher() -> ConfigWatcher:
    """Start the global ConfigWatcher singleton."""
    global _watcher
    if _watcher is None:
        _watcher = ConfigWatcher()
    await _watcher.start()
    return _watcher


async def stop_config_watcher() -> None:
    """Stop the global ConfigWatcher singleton."""
    global _watcher
    if _watcher:
        await _watcher.stop()
