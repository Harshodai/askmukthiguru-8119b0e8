---
name: video-generator
description: Professional AI video production workflow. Use when creating videos, short films, commercials, or any video content using AI generation tools.
---

# Video Generation Workflow

A structured, five-phase workflow for professional AI video production, ensuring quality, continuity, and alignment with user requirements.

## Workflow Overview

1. **Phase 1: Initial Gathering** -> Collect requirements, stop for user confirmation.
2. **Phase 2: Global Definitions** -> Specify style, characters, voices, BGM (text only).
3. **Phase 3: Clip & BGM Planning** -> Plan clips (4/6/8s), transition descriptions, and BGM emotional blueprint.
4. **Phase 4: Reference Images** -> Generate reference images (mandatory visual anchors).
5. **Phase 5: Execution** -> Generate keyframes, video clips, TTS narration, and compile audio tracks.

---

## Critical Rules

1. **[PHASE 1 STOP]** Ask clarifying questions if details are missing. DO NOT guess; wait for explicit user confirmation before moving to Phase 2.
2. **[DETAILED VIDEO PROMPT]** Every video prompt must include 2-4 sentences detailing the transition, movement, and visual elements. One-liners are prohibited.
3. **[KEYFRAME DIFFERENCE]** Ensure last keyframe has an interpolatable change (subject pose, position, or composition) compared to the first keyframe to prevent static or unnatural motion.
4. **[PHASE 4 MANDATORY]** Generate all reference images (using `generate_image` or `generate_image_variation`) before generating keyframes or video clips. Never skip.
5. **[ASPECT RATIO]** Use upright 16:9 or 9:16 aspect ratios. Never generate 1:1 or other ratios.
6. **[NO TTS FOR ON-SCREEN]** Do not use TTS for on-screen dialogue or singing (rely on video model's lip sync).
7. **[NARRATION BUDGET]** Scale narration text to fit the clip's duration safely. Count words/characters according to the language rate in the catalog:
   $$\text{max\_text\_units} = \text{Rate} \times \text{narration\_budget} \times 0.85$$
8. **[AUDIO MIXING]** Preserve all audio tracks (video ambient audio, BGM, and narration). Overlay instead of replacing. Keep narration clearly audible and consistent in volume.

---

## Phase 1: Initial (Gathering Information)

Gather the following details from the user:
- **Purpose**: Target goal/audience.
- **Narrative arc**: Story structure.
- **Duration**: Total seconds.
- **Aspect ratio**: 16:9 or 9:16.
- **Visual style**: Artistic direction (e.g. "Makoto Shinkai anime", "Pixar 3D").
- **Recurring elements**: Characters or objects with appearance details.
- **Narration/Dialogue**: Voices, languages, gender, pace, tone.
- **BGM requirements**: Style, mood, instrumentation.

> **[MANDATORY STOP]** Wait for explicit user confirmation of Phase 1 before proceeding.

---

## Phase 2: Global Definitions (Text Only)

Specify style properties:
- **Sub-genre**: Style category.
- **Rendering & Line**: 2D, 3D, outlines, cell-shading.
- **Color & Lighting**: High-neon, natural light, soft glow.
- **Detail Density**: Minimalist vs. complex background.
- **Recurring Elements**: Unique identifier, text description, outfit, physical properties.
- **Voice Profiles**: Tone, pace, gender.
- **BGM Decision**: Embedded (in-prompt) vs. Separate (Phase 5 generation) vs. None. If separate, define Genre, Tempo (BPM), Key, Instrumentation.

---

## Phase 3: Clip & BGM Planning

Plan clip parameters and BGM blueprint:
- **Clips**: Limit segment durations to 4, 6, or 8 seconds.
- **Per-Clip Properties**:
  - `narrative_purpose`: establish, climax, transition, supplementary, etc.
  - `scene` & `content_action`: action details.
  - `transition_description` (2-4 sentences): detailed visual transitions, trajectories, and persistence.
  - `camera_movement`: pan, tilt, dolly, arc, static.
  - `first_keyframe_framing` & `last_keyframe_framing`
  - `last_keyframe_edit_from_first`: `yes` if overlap exists (static, small pan), `no` if no overlap.
  - `narration_budget` & `narration_cue` (text or "continues").
  - `bgm_cue`: mood/emotion, arrangement density.
- **BGM Emotional Arc Blueprint**: Create a second-by-second markdown table summary grouping contiguous sections sharing identical `bgm_cue` settings.

---

## Phase 4: Reference Image Generation

Generate reference images to serve as the visual anchor:
1. **Primary Reference**: Use `generate_image`. Prompt must include full visual style specs + item description, white background, ending with `"no text, no watermarks, no logos, no labels, no annotations"`.
2. **Additional Angles**: Use `generate_image_variation` referencing the primary image. Apply edits relative to the anchor, keeping background white and suffixing with `"no text, no watermarks, no logos, no labels, no annotations"`.

---

## Phase 5: Execution

Produce and mix the final media assets:
1. **Keyframes**: Produce first and last keyframe images keeping aspect ratio strict (16:9/9:16).
2. **Video Generation**: Interpolate between keyframes. Incorporate transition descriptions into prompt.
3. **Narration Audio**: Generate TTS segment-by-segment following budget rules.
4. **BGM & Sound FX**: Generate separate tracks if BGM is separate.
5. **Compositing & Mixing**: Compile clips chronologically. Mix BGM, narration, and background/sfx tracks.
