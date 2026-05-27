#!/usr/bin/env python3
import os
import sys
import re
import json
import time
import shutil
import urllib.request
import urllib.error
from pathlib import Path

# Paths
WORKSPACE = "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8"
LOCAL_SKILLS_DIR = Path(WORKSPACE) / ".agents" / "skills"
GLOBAL_SKILLS_DIR = Path("~/.config/agents/skills").expanduser()
BOOKS_DIR = Path("/Users/harshodaikolluru/Downloads/technical_books")
EXTRACT_SCRIPT = Path(WORKSPACE) / "book-to-skill" / "scripts" / "extract.py"
LOG_FILE = Path(WORKSPACE) / "scripts" / "generation_progress.log"
STATUS_FILE = Path(WORKSPACE) / "scripts" / "books_status.json"

BOOKS = [
    {
        "filename": "AI Agents and Applications With LangChain, LangGraph, and MCP (Roberto Infante) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "ai-agents-langchain-mcp",
    },
    {
        "filename": "AI Agents in Action (Micheal Lanham) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "ai-agents-in-action",
    },
    {
        "filename": "AI Engineering Building Applications with Foundation Models (Chip Huyen) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "ai-engineering-chip-huyen",
    },
    {
        "filename": "Build an LLM Application (from Scratch) (MEAP Version 3) (Hamza Farooq) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "build-llm-app-scratch",
    },
    {
        "filename": "Building Applications with AI Agents Designing and Implementing Multiagent Systems (Michael Albada) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "building-apps-ai-agents",
    },
    {
        "filename": "Designing Data-Intensive Applications, 2nd Edition (Martin Kleppmann, Chris Riccomini) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "designing-data-intensive-apps-2e",
    },
    {
        "filename": "Martin_Kleppmann_Designing_Data_Intensive_Applications_The_Big_Ideas.pdf",
        "slug": "kleppmann-ddia-big-ideas",
    },
    {
        "filename": "RAG Made Simple The Complete Visual Guide to Retrieval-Augmented Generation (Nir Diamant) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "rag-made-simple",
    },
    {
        "filename": "System Design for the LLM Era.pdf",
        "slug": "system-design-llm-era",
    },
    {
        "filename": "[IEEE 2019 International Conference on Innovative Trends and Advances in Engineering and Technology (ICITAET) - SHEGAON, India… (Muddinagiri, Ruchika Ambavane etc.) (z-library.sk, 1lib.sk, z-lib.sk).pdf",
        "slug": "ieee-innovative-trends-2019",
    }
]

def log(msg):
    print(msg)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def load_status():
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_status(status):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)

def update_book_status(slug, status_str):
    status = load_status()
    status[slug] = status_str
    save_status(status)

def call_ollama(prompt, system_prompt=""):
    url = "http://localhost:11434/api/generate"
    data = {
        "model": "deepseek-r1:7b",
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "options": {
            "num_ctx": 32768,
            "temperature": 0.3
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    backoff = 2
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))
                full_response = res.get("response", "")
                cleaned = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL).strip()
                return cleaned
        except Exception as e:
            log(f"Ollama API call error: {e}. Attempt {attempt+1}/4. Retrying in {backoff}s...")
            if attempt < 3:
                time.sleep(backoff)
                backoff *= 2
    return ""

def split_into_chapters(text):
    lines = text.splitlines()
    chapters = []
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        match_ch = re.search(r"^\s*(?:CHAPTER|Chapter)\s+(\d+|[IVXLCDM]+)\b", line_stripped)
        if match_ch:
            chapters.append((i, line_stripped))
            continue
            
        match_num = re.search(r"^\s*(\d+)\.?\s+([A-Z][a-zA-Z\s,:-]{3,60})$", line_stripped)
        if match_num:
            chapters.append((i, line_stripped))
            
    cleaned = []
    prev_line = -100
    for idx, title in chapters:
        if idx - prev_line > 50:
            cleaned.append((idx, title))
            prev_line = idx
            
    if len(cleaned) < 3:
        pages = text.split("\f")
        if len(pages) > 5:
            num_pages = len(pages)
            pages_per_chapter = max(1, num_pages // 12)
            cleaned = []
            for ch_idx in range(0, num_pages, pages_per_chapter):
                ch_num = (ch_idx // pages_per_chapter) + 1
                page_start_line = sum(len(pages[p].splitlines()) for p in range(ch_idx))
                cleaned.append((page_start_line, f"Section {ch_num} (Pages {ch_idx+1}-{min(num_pages, ch_idx+pages_per_chapter)})"))
                
    if len(cleaned) < 3:
        lines_count = len(lines)
        chunk_size = lines_count // 10
        cleaned = [(i * chunk_size, f"Section {i+1}") for i in range(10)]
        
    return cleaned

def generate_skill_for_book(book):
    filename = book["filename"]
    slug = book["slug"]
    pdf_path = BOOKS_DIR / filename
    work_dir = Path(f"/tmp/book_skill_work_{slug}")
    
    log(f"\n==================================================")
    log(f"PROCESSING BOOK: {filename}")
    log(f"SLUG: {slug}")
    log(f"==================================================")
    
    update_book_status(slug, "in-progress")
    
    # 1. Run extraction script
    os.environ["BOOK_SKILL_WORKDIR"] = str(work_dir)
    cmd = f'python3 "{EXTRACT_SCRIPT}" "{pdf_path}" --mode text --install-missing yes'
    log(f"Running extraction: {cmd}")
    ret = os.system(cmd)
    if ret != 0:
        log(f"Extraction failed for {filename}!")
        update_book_status(slug, "failed")
        return False
        
    full_text_file = work_dir / "full_text.txt"
    metadata_file = work_dir / "metadata.json"
    
    if not full_text_file.exists() or not metadata_file.exists():
        log(f"Extracted files not found!")
        update_book_status(slug, "failed")
        return False
        
    with open(full_text_file, "r", encoding="utf-8") as f:
        text = f.read()
        
    with open(metadata_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    # 2. Slice into chapters
    chapters = split_into_chapters(text)
    log(f"Detected {len(chapters)} chapters/sections.")
    
    local_out = LOCAL_SKILLS_DIR / slug
    local_out.mkdir(parents=True, exist_ok=True)
    (local_out / "chapters").mkdir(parents=True, exist_ok=True)
    
    chapter_summaries = []
    lines = text.splitlines()
    
    for i, (line_idx, title) in enumerate(chapters):
        start_line = line_idx
        end_line = chapters[i+1][0] if i+1 < len(chapters) else len(lines)
        
        chapter_lines = lines[start_line:end_line]
        chapter_text = "\n".join(chapter_lines[:30000])
        
        ch_num = i + 1
        ch_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        ch_filename = f"ch{ch_num:02d}-{ch_slug}.md"
        
        log(f"Generating summary for Chapter {ch_num}: {title}...")
        prompt = f"""
You are compiling a technical book into an agent skill.
Below is the text of a chapter/section:
---
{chapter_text}
---

Your task is to write a dense, structured markdown summary of this chapter according to these quality rules:
1. Extract structure, not summaries. Capture named frameworks (mental models with clear application), actionable principles (rules that guide decisions), techniques (step-by-step methods), and anti-patterns.
2. Preserve the author's precision. Capture exact formulations and names (e.g., "The 5 Whys", not "ask why multiple times").
3. Keep the output under 1,000 tokens. Write in a concise practitioner voice ("Use X when Y", not "The book explains X").
4. Include a "Code Examples" section with the most instructive code snippet (if any) and a "Reference Tables" section for any parameter/decision tables.

Format the output exactly as follows:
# Chapter {ch_num}: {title}

## Core Idea
<1-2 sentences: the single most important thing this chapter teaches>

## Frameworks Introduced
- **<Framework Name>**: <exact formulation>
  - When to use: <specific situation>
  - How: <steps or criteria>

## Key Concepts
- **<Term>**: <precise definition in 1 sentence>

## Mental Models
- Use X when Y / Think of X as Y

## Anti-patterns
- **<What to avoid>**: <why it fails>

## Code Examples
```
<key code example>
```
- **What it demonstrates**: <one line>

## Reference Tables
<markdown table or decision matrix>

## Key Takeaways
1. <Actionable insight>
2. <Actionable insight>
3. <Actionable insight>

## Connects To
- <Relates to which concepts or chapters>

Write only the markdown content, starting with the `# Chapter` heading. Do not include thinking traces or meta-commentary in your output.
"""
        ch_content = call_ollama(prompt)
        if not ch_content:
            log(f"Failed to generate summary for Chapter {ch_num}!")
            ch_content = f"# Chapter {ch_num}: {title}\n\nSummary generation failed."
            
        ch_path = local_out / "chapters" / ch_filename
        with open(ch_path, "w", encoding="utf-8") as f:
            f.write(ch_content)
            
        chapter_summaries.append({
            "num": ch_num,
            "title": title,
            "filename": ch_filename,
            "content": ch_content
        })
        
    # 3. Generate supporting files
    log("Generating glossary.md...")
    glossary_prompt = f"Based on the following chapter titles, generate an alphabetical glossary of key terms with definitions and chapter references. Keep it structured as: **Term** — definition (Ch N).\nChapters:\n" + "\n".join([f"Ch {c['num']}: {c['title']}" for c in chapter_summaries])
    glossary_content = call_ollama(glossary_prompt)
    with open(local_out / "glossary.md", "w", encoding="utf-8") as f:
        f.write(f"# Glossary\n\n{glossary_content}")
        
    log("Generating patterns.md...")
    patterns_prompt = f"Based on the following chapter titles, extract and list the concrete technical techniques, patterns, or algorithms introduced. For each pattern include: ## Pattern Name\\n**When to use**: ...\\n**How**: ...\\n**Trade-offs**: ...\nChapters:\n" + "\n".join([f"Ch {c['num']}: {c['title']}" for c in chapter_summaries])
    patterns_content = call_ollama(patterns_prompt)
    with open(local_out / "patterns.md", "w", encoding="utf-8") as f:
        f.write(f"# Technical Patterns\n\n{patterns_content}")
        
    log("Generating cheatsheet.md...")
    cheatsheet_prompt = f"Based on the following chapter titles, compile a cheatsheet featuring decision tables, comparison matrices, and quick reference rules for practitioners. Keep it under 1000 tokens.\nChapters:\n" + "\n".join([f"Ch {c['num']}: {c['title']}" for c in chapter_summaries])
    cheatsheet_content = call_ollama(cheatsheet_prompt)
    with open(local_out / "cheatsheet.md", "w", encoding="utf-8") as f:
        f.write(f"# Cheatsheet\n\n{cheatsheet_content}")
        
    # 4. Generate master skill.md
    log("Generating skill.md...")
    toc_rows = []
    for c in chapter_summaries:
        toc_rows.append(f"| [ch{c['num']:02d}](chapters/{c['filename']}) | {c['title']} | Key concepts and frameworks |")
        
    skill_md_content = f"""---
name: {slug}
description: "Knowledge base from '{filename}'. Use when referencing concepts, patterns, or frameworks from this book."
allowed-tools:
  - Read
  - Grep
argument-hint: [topic or chapter number]
---

# {filename}

## How to Use This Skill
- **Without arguments** — load core frameworks for reference
- **With a topic** — ask about a specific topic; I find and read the relevant chapter
- **With chapter** — ask for `chXX`; I load that chapter file

---

## Core Frameworks & Mental Models

{glossary_content[:2000] if glossary_content else "Refer to glossary.md for terms."}

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
""" + "\n".join(toc_rows) + """

## Supporting Files
- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and design patterns
- [cheatsheet.md](cheatsheet.md) — quick reference tables and decision guides
"""
    with open(local_out / "skill.md", "w", encoding="utf-8") as f:
        f.write(skill_md_content)
        
    # 5. Mirror to global directory
    log(f"Mirroring skill to global directory: {GLOBAL_SKILLS_DIR / slug}")
    global_out = GLOBAL_SKILLS_DIR / slug
    if global_out.exists():
        shutil.rmtree(global_out)
    shutil.copytree(local_out, global_out)
    
    # 6. Cleanup work directory
    shutil.rmtree(work_dir, ignore_errors=True)
    log(f"SUCCESS: Skill {slug} created!")
    update_book_status(slug, "completed")
    return True

def main():
    log("Starting Generation Script...")
    GLOBAL_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize status file if it doesn't exist
    status = load_status()
    for book in BOOKS:
        if book["slug"] not in status:
            status[book["slug"]] = "pending"
    save_status(status)
    
    for book in BOOKS:
        slug = book["slug"]
        current_status = load_status().get(slug, "pending")
        if current_status == "completed":
            log(f"Skipping already completed book: {book['filename']}")
            continue
            
        success = False
        try:
            success = generate_skill_for_book(book)
        except Exception as e:
            log(f"Exception while generating skill for {book['filename']}: {e}")
            update_book_status(slug, "failed")
            
        if success:
            log(f"Completed {slug}")
        else:
            log(f"FAILED {slug}")
            
    log("\nFinished processing all books!")

if __name__ == "__main__":
    main()
