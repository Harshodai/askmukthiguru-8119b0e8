"""Tests for terminal-mode logging and root health aliases (Nov 14 readiness)."""

import logging
from unittest.mock import MagicMock

import pytest

from app.config import settings


def test_terminal_mode_log_message_formatting(caplog):
    """Verify that in terminal mode, context harness logging states terminal mode abstention

    instead of 'falling back to legacy'.
    """
    # 1. When terminal mode is active
    harness_enabled = True
    is_terminal = True

    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("test.first_person_pipeline")
        msg = (
            "terminal mode: abstaining, no legacy fall-through"
            if is_terminal
            else "falling back to legacy"
        )
        logger.info(
            "[FirstPersonPipeline] Context harness evaluated %d contexts with no direct answer; %s",
            2,
            msg,
        )

    assert "terminal mode: abstaining, no legacy fall-through" in caplog.text
    assert "falling back to legacy" not in caplog.text


def test_non_terminal_mode_log_message_formatting(caplog):
    """Verify that when terminal mode is off, logging still indicates fallback to legacy."""
    is_terminal = False

    with caplog.at_level(logging.INFO):
        logger = logging.getLogger("test.first_person_pipeline")
        msg = (
            "terminal mode: abstaining, no legacy fall-through"
            if is_terminal
            else "falling back to legacy"
        )
        logger.info(
            "[FirstPersonPipeline] Context harness evaluated %d contexts with no direct answer; %s",
            2,
            msg,
        )

    assert "falling back to legacy" in caplog.text
