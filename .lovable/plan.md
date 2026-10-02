# Complete Profile and Knowledge Graph Rebuild

## Goal
Finish both areas as one coherent seeker experience across web, Android, and iOS. Remove dense duplication, unify graph behavior, and verify every important state and interaction.

## Profile
- Reduce six competing tabs into four clear destinations: **Journey**, **Personalise**, **Memory**, and **Settings**.
- Move conversation history into Journey, where it supports returning to chat instead of behaving like account administration.
- Merge repeated activity cards into one calm overview; remove duplicated identity and metric blocks.
- Keep avatar, language, guidance tone, and depth together under Personalise with one sticky save action.
- Keep privacy, security, audio, reminders, appearance, export, and deletion under Settings using clear grouped sections.
- Make tab navigation horizontally scrollable on phones, preserve URL deep links, 44px targets, safe areas, and visible return-to-chat navigation.

## Knowledge Graph
- Use the same card-node visual language, selection behavior, controls, loading/error/empty states, and details presentation for public and personal graphs.
- Replace the personal graph’s custom moving SVG interaction with the existing React Flow graph foundation used by the public map; preserve personal data, search, node relationships, deletion, and insights.
- Stop continuous distracting motion. Use a stable fitted layout, restrained selection highlighting, reduced-motion support, pan/zoom, reset, and fullscreen.
- Use a bottom detail sheet on phones and a side details panel on large screens; never cover controls, legends, or important nodes.
- Replace dense overlays with compact controls and collapsible filters. Ensure every icon control has a label or tooltip.
- Make empty and unavailable states truthful: personal map never substitutes fabricated memories; public map may use clearly labelled demonstration data only where already supported.

## End-to-end verification
- Cover Profile tab switching, URL persistence, save state, mobile overflow, return to chat, graph/list switching, search, selection, close, pan/zoom/reset, fullscreen, empty/loading/error states, and memory deletion confirmation.
- Test 384px phone, tablet, and desktop layouts; inspect screenshots for overlap and contrast.
- Run focused component tests, full frontend typecheck/build signal, and relevant accessibility checks.

## Technical details
- Extract a reusable graph canvas/detail presentation instead of maintaining two unrelated rendering engines.
- Preserve existing memory APIs, privacy boundaries, metrics formulas, local/cloud deletion semantics, and authentication requirements.
- Frontend-only scope: no backend, schema, corpus, or retrieval changes.
