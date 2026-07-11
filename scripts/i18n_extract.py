#!/usr/bin/env python3
"""
Batch i18n string extraction script.

This script finds hardcoded UI strings in React component files and
replaces them with t() calls using the react-i18next translation hook.

Run from repo root:
  python3 scripts/i18n_extract.py

Only processes files listed in FILES_TO_PROCESS.
"""

import os
import re
import json
from pathlib import Path

SRC = Path("src")

# Files to process (relative to src/)
FILES_TO_PROCESS = [
    # Common components
    "components/common/PushPermissionPrompt.tsx",
    "components/common/SessionExpiredHandler.tsx",
    "components/common/BrandedSpinner.tsx",
    "components/common/UserMenu.tsx",
    "components/common/SafetyDisclaimer.tsx",
    "components/common/CommandPalette.tsx",
    "components/common/ChatErrorBoundary.tsx",
    "components/common/RootErrorBoundary.tsx",
    # Chat components
    "components/chat/ChatHeader.tsx",
    "components/chat/ChatEmptyState.tsx",
    "components/chat/ChatErrorBanner.tsx",
    "components/chat/ThinkingPills.tsx",
    "components/chat/SereneMindModal.tsx",
    "components/chat/SpiritualWelcomeBanner.tsx",
    "components/chat/DesktopSidebar.tsx",
    "components/chat/MobileConversationSheet.tsx",
    "components/chat/PrePracticeGate.tsx",
    "components/chat/DailyTeaching.tsx",
    "components/chat/ConversationSourcesPanel.tsx",
    "components/chat/CitationPanel.tsx",
    "components/chat/SlashCommandMenu.tsx",
    "components/chat/ScrollToBottomFab.tsx",
    "components/chat/WisdomCardGenerator.tsx",
    "components/chat/MessageList.tsx",
    "components/chat/AssistantSwitcher.tsx",
    "components/chat/InlineActions.tsx",
    "components/chat/MeditationStats.tsx",
    # Layout
    "components/layout/AppShell.tsx",
    "components/layout/AnimatedLayout.tsx",
    # Profile
    "components/profile/MemoryManager.tsx",
    "components/profile/NotesPanel.tsx",
    # Auth
    "components/auth/TwoFactorSettings.tsx",
    # Meditation
    "components/meditation/GuidedMeditationFlow.tsx",
    # KG
    "components/kg/KGConceptMap.tsx",
    # ai-elements
    "components/ai-elements/prompt-input.tsx",
    "components/ai-elements/message.tsx",
    "components/ai-elements/conversation.tsx",
    "components/ai-elements/shimmer.tsx",
    # Pages
    "pages/NotFound.tsx",
    "pages/AuthPage.tsx",
    "pages/Index.tsx",
    "pages/ChatPage.tsx",
    "pages/ProfilePage.tsx",
    "pages/PracticesPage.tsx",
    "pages/PracticeDetailPage.tsx",
    "pages/PrivacyPage.tsx",
    "pages/TermsPage.tsx",
    "pages/ResetPasswordPage.tsx",
    "pages/KnowledgeGraphPage.tsx",
    "pages/StudyNotebookPage.tsx",
    "pages/guides/SpiritGuidesPage.tsx",
    # Admin
    "admin/pages/AdminLoginPage.tsx",
    "admin/layout/AdminShell.tsx",
    "admin/layout/AdminTopbar.tsx",
    "admin/components/EmptyState.tsx",
    "admin/components/AdminPageStates.tsx",
    "admin/components/AdminErrorBoundary.tsx",
]


def add_i18n_import(content: str) -> tuple[str, bool]:
    """Add react-i18next import if not present. Check specifically for useTranslation named import."""
    # Check if useTranslation is already imported from react-i18next
    if ("useTranslation" in content and "from 'react-i18next'" in content) or ('from "react-i18next"' in content and "useTranslation" in content):
        return content, False
    # Also check if useTranslation is imported from anywhere (any import containing useTranslation)
    if "useTranslation" in content:
        return content, False
    # Find the last import line and add after it
    last_import = -1
    for m in re.finditer(r'^import .+$', content, re.MULTILINE):
        # Skip CSS imports
        if '.css' not in m.group() and '.json' not in m.group():
            last_import = m.end()
    if last_import == -1:
        return content, False
    # Find the end of line
    line_end = content.find('\n', last_import)
    if line_end == -1:
        line_end = len(content)
    new_content = content[:line_end] + "\nimport { useTranslation } from 'react-i18next';" + content[line_end:]
    return new_content, True


def add_t_hook(content: str) -> tuple[str, bool]:
    """Add `const { t } = useTranslation();` inside component functions that don't have it."""
    if 'const { t } = useTranslation()' in content or 'const {t} = useTranslation()' in content:
        return content, False

    # Find the first function component opening brace after export
    # Match patterns: export const Component = () => {, export function Component() {
    match = re.search(r'export (?:const|function) \w+\s*(?:=|:)\s*(?:\([^)]*\)\s*(?::\s*\w+[^=]*)?=>\s*)?\{', content)
    if not match:
        # Try simpler function patterns
        match = re.search(r'export (?:const|function) \w+\s*[=(]', content)
        if match:
            # Find the opening brace of the component
            rest = content[match.end():]
            depth = 0
            idx = 0
            for i, ch in enumerate(rest):
                if ch == '{':
                    depth += 1
                    if depth == 1:
                        idx = i
                        break
            if depth == 0:
                return content, False
            insert_pos = match.end() + idx + 1
            indent = _get_indent(content, insert_pos)
            new_content = content[:insert_pos] + f"\n{indent}const {{ t }} = useTranslation();" + content[insert_pos:]
            return new_content, True
        return content, False

    # The regex already consumes the opening brace, so match.end() is positioned right after it
    insert_pos = match.end()
    indent = _get_indent(content, insert_pos)
    new_content = content[:insert_pos] + f"\n{indent}const {{ t }} = useTranslation();" + content[insert_pos:]
    return new_content, True


def _get_indent(content: str, pos: int) -> str:
    """Get the indentation at the given position."""
    line_start = content.rfind('\n', 0, pos)
    if line_start == -1:
        return "  "
    line = content[line_start+1:pos]
    indent = ""
    for ch in line:
        if ch in ' \t':
            indent += ch
        else:
            break
    return indent


def process_file(filepath: Path) -> bool:
    """Process a single file. Returns True if modified."""
    if not filepath.exists():
        print(f"  SKIP: {filepath} not found")
        return False

    original = filepath.read_text(encoding='utf-8')
    content = original
    modified = False

    # Add import
    content, imp_added = add_i18n_import(content)
    if imp_added:
        modified = True
        print(f"  + import in {filepath.name}")

    # Add t hook
    content, hook_added = add_t_hook(content)
    if hook_added:
        modified = True
        print(f"  + t() hook in {filepath.name}")

    if modified:
        filepath.write_text(content, encoding='utf-8')

    return modified


def main():
    processed = 0
    modified = 0

    for rel_path in FILES_TO_PROCESS:
        filepath = SRC / rel_path
        processed += 1
        if process_file(filepath):
            modified += 1

    print(f"\nProcessed {processed} files, modified {modified}")


if __name__ == "__main__":
    main()
