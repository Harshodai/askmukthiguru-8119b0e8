# Reduce Your Claude Token Usage — Setup Guide

Two lightweight tools. Five minutes. Fewer wasted tokens.

This guide walks you through installing a token-saving skill and a usage tracker so you can get more from every Claude conversation.

## Why This Matters
Claude uses tokens for every word it reads and generates. Verbose reasoning burns through your limits faster. By adding a minimal reasoning skill and a real-time usage tracker, you keep conversations efficient and stay in control of your token spend.

1. **Caveman Skill:** Forces Claude into a minimal, low-token reasoning mode. Less fluff, same answers.
2. **Claude Counter:** Browser extension that shows token count per chat, so you see exactly what each conversation costs.

### Before You Start
You need a Claude.ai account (free or paid) and one of the following browsers: Chrome, Edge, Chromium, or Firefox.

---

## Part 1 — Install the Caveman Skill (Token Saver)
This skill overrides Claude's default verbose style with stripped-down, token-efficient responses. Think of it as Claude on a strict word budget.

1. **Copy the Skill File:** Open [caveman SKILL.md](https://github.com/JuliusBrussee/caveman/blob/main/caveman/SKILL.md) (or `github.com/JuliusBrussee/caveman` -> `refs/heads/main/caveman/SKILL.md`) in your browser. Select all the content on the page and copy it to your clipboard.
2. **Open Skill Settings:** Navigate to [claude.ai/customize/skills](https://claude.ai/customize/skills) — this is where all your custom Claude skills are managed.
3. **Create a New Skill:** Click the `+` button, then select: **Create Skill** -> **Write Skill Instructions**.
4. **Configure the Fields:**
   - **Name:** `Caveman`
   - **Description:** `A minimalistic, primitive-style reasoning assistant that simplifies thinking and responses.`
   - **Instructions:** Paste the content you copied in Step 1.
5. **Save & Use:** Hit **Save**. To activate it, type `/caveman` or say *"use caveman skill"* before your prompt in any chat.

---

## Part 2 — Install Claude Counter (Usage Tracker)
This browser extension displays real-time token counts so you can see exactly how much each conversation uses — and where to cut back.

### Chrome / Edge / Chromium
1. **Download the Extension:** Get the file `claude-counter-0.4.2.zip` from the source provided to you.
2. **Open Extensions Page:** Type `chrome://extensions` in your browser's address bar and press Enter.
3. **Enable Developer Mode:** Toggle on **Developer Mode** using the switch in the top-right corner of the extensions page.
4. **Install:** Drag and drop the `.zip` file directly onto the extensions page. The counter will activate immediately.

### Firefox
1. **Download the Extension:** Get the file `claude-counter-0.4.2.xpi` from the source provided to you.
2. **Open in Firefox:** Drag the `.xpi` file into any open Firefox window.
3. **Confirm Install:** Click **Add** when the installation prompt appears. Done.

---

## ✅ You’re All Set!
- **Caveman skill is active** — Claude now reasons with fewer tokens.
- **Claude Counter is installed** — token usage is visible in real time.
- You’re ready to get more out of every conversation.
