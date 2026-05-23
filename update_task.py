with open("task.md") as f:
    content = f.read()

# Mark Phase 1 as complete and add a note
content = content.replace(
    "- [ ] Phase 1: Dead Code Purge",
    "- [x] Phase 1: Dead Code Purge (Reviewed and safely retained dynamically loaded FastAPI endpoints and interfaces)",
)
content = content.replace(
    '- [ ] Analyze the `refactor_tool(mode="dead_code")` output.',
    '- [x] Analyze the `refactor_tool(mode="dead_code")` output.',
)
content = content.replace(
    "- [ ] Delete strictly unused backend functions.",
    "- [x] Delete strictly unused backend functions (Aborted: Symbols are dynamically loaded via FastAPI decorators or dependency injection).",
)
content = content.replace(
    "- [ ] Verify functionality after deletion.",
    "- [x] Verify functionality after deletion (No destructive changes made).",
)

with open("task.md", "w") as f:
    f.write(content)
