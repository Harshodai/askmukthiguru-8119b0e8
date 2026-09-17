"""Eval harness package.

Exists so tests/test_settings_guards.py's _discover_guard_dirs() walks this
tree: without it the directory is a PEP-420 namespace package and every
direct os.environ read here is invisible to the ratchet. 2026-09-16: the
three runners under it were converted to app.config.settings, so the guard
starts green with zero baselined debt for this directory.
"""
