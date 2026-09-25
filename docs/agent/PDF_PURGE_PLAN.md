# Plan: Git History Purge for Copyrighted Reference PDFs

> **Status**: INVESTIGATED & DOCUMENTED ONLY — DO NOT EXECUTE WITHOUT EXPLICIT SEPARATE HUMAN SIGN-OFF.  
> **Boundary**: N8 / History Rewrite Boundary.

---

## 1. Background & Target Files

Per `CONTENT-RIGHTS.md:25`, two copyrighted third-party reference PDFs were previously committed to the root of the repository:
1. `RAG Made Simple The Complete Visual Guide to Retrieval-Augmented Generation (Nir Diamant) (z-library.sk, 1lib.sk, z-lib.sk).pdf`
2. `System Design for the LLM Era.pdf`

Both files represent copyright compliance liabilities and must be completely excised from the repository's git object database.

---

## 2. Git History & Current Status

### A. Introduction Commit
- **Commit SHA**: `99805e845faeb9350685dddffedda1ca9cffd55b`
- **Author**: `Harshodai <kharshaengineer@gmail.com>`
- **Date**: `Fri May 15 10:54:25 2026 +0530`
- **Commit Message**: `Fix production glitches: ingestion checkpoint logic, LangGraph streaming state, Docker health checks, and FeedbackStore integration`

### B. Removal from Working Tree
- **Commit SHA**: `b2124244ee7fba5b0b09a7db857d73839a96d52a`
- **Author**: `Harshodai <kharshaengineer@gmail.com>`
- **Date**: `Fri Jun 5 12:12:08 2026 +0530`
- **Commit Message**: `chore: remove outdated docs, plans, unused folders, reference PDFs, and legacy scratch/test scripts`

### C. Working Tree Presence
- **Current `HEAD`**: `0` instances present. Both files were deleted from the tree in `b2124244`.
- Verified via `git ls-tree -r --name-only HEAD | grep -i "\.pdf$"`.

### D. History Containment
- While absent from the working tree, both files reside permanently within the git packfiles for all commits between `99805e84` and `b2124244`.
- **Commits following `99805e84` on `main`**: **2,818 commits**.
- Present across all 18 local branches and worktrees.

---

## 3. Remote Exposure & Blast Radius

### A. Remote Repository
- **Remote**: `origin` (`https://github.com/Harshodai/askmukthiguru-8119b0e8.git`)

### B. Remote Branches Containing the Commits
Commit `99805e84` has been pushed to the following remote tracking branches on GitHub:
- `origin/main` (default branch)
- `origin/codex/complete-open-pr-integration`
- `origin/docs/current-hld-lld-2026-09`
- `origin/feat/profile-cross-page-ux-2026-09`
- `origin/feat/ruthless-e2e-ux-hardening-2026-09`
- `origin/feat/ruthless-product-ux-hardening`
- `origin/feat/ruthless-production-readiness`
- `origin/feat/speaker-attribution-verbatim`
- `origin/pr-22`
- `origin/pr14-review`

### C. Blast Radius of Running `git-filter-repo`
1. **Commit SHA Invalidation**:
   - Rewriting history removes `99805e84` and changes the tree hash of its commit object.
   - Every single one of the **2,818+ subsequent commits** will receive a completely new commit SHA.
2. **Force-Push Requirement**:
   - Requires `git push origin --force --all` across all active remote branches.
3. **Local Clones & Worktrees**:
   - Every existing clone, worktree, CI worker cache, or contributor checkout will fail fast on `git pull` due to non-fast-forward divergence.
   - Every developer must perform a fresh clone (`git clone ...`) or a hard fetch-and-reset (`git fetch origin && git reset --hard origin/main`).
4. **Pull Requests & Issue References**:
   - Existing open pull requests (e.g., `pr-22`, `pr14-review`) will lose their common merge base and need interactive rebase onto rewritten branches.
   - Any links referencing past commit hashes (`https://github.com/.../commit/<sha>`) will fail or point to unreachable objects.
5. **GitHub Server Caching**:
   - Force-pushing does not immediately delete dangling commit objects from GitHub's backends. GitHub retains cached objects until garbage collected (requires opening a GitHub Support ticket to purge cached commit views).

---

## 4. Proposed Execution Commands (For Future Execution)

> **DO NOT RUN WITHOUT EXPLICIT SIGN-OFF AND COORDINATION WITH ALL ACTIVE REPO USERS.**

### Step 1: Pre-Execution Full Backup
```bash
# Create an independent mirror clone backup outside the working directory
git clone --mirror /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8 /Users/harshodaikolluru/Public/askmukthiguru-pre-purge-backup.git
```

### Step 2: History Filter Execution
```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8

# Ensure git-filter-repo is installed
# brew install git-filter-repo || pip install git-filter-repo

# Run filter-repo to scrub the two exact paths from all refs and commits
git-filter-repo \
  --path "RAG Made Simple The Complete Visual Guide to Retrieval-Augmented Generation (Nir Diamant) (z-library.sk, 1lib.sk, z-lib.sk).pdf" \
  --path "System Design for the LLM Era.pdf" \
  --invert-paths \
  --force
```

### Step 3: Verification
```bash
# Verify no traces remain in any branch, tag, or commit
git log --all --full-history -- "RAG Made Simple*" "*System Design for the LLM Era*"
# Expected output: (empty)
```

### Step 4: Re-Add Remote & Force Push
*Note: `git-filter-repo` automatically deletes the `origin` remote to prevent accidental premature pushes.*
```bash
# Re-attach remote
git remote add origin https://github.com/Harshodai/askmukthiguru-8119b0e8.git

# Force-push all rewritten branches to GitHub
git push origin --force --all
```

### Step 5: Upstream Cache Clearance
Contact GitHub Support to request an explicit garbage collection / reflog flush on `Harshodai/askmukthiguru-8119b0e8` so orphaned commit objects containing the copyrighted PDF payloads are cleared from GitHub's internal caches.
