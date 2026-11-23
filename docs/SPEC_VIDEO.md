# SPEC — Video Studio: an editable storyboard, not a slideshow (issue U10)

Status: specification written 2026-11-23. Implementation: **NOT DONE** (see
`docs/ISSUES.md` U10 / H8). This is the contract for milestones M1–M4.

## 1. Honest ceiling first

This produces an **illustrated animated explainer**: designed motion-graphics
scenes, narration, captions, real transitions — built from HTML/SVG/Canvas frames
captured with Playwright and encoded with ffmpeg. It is **not** cinematic
text-to-video (Sora/Veo-class generation) and will not be described as such.

Before any generative-video idea is proposed, `nvidia-smi` and total RAM are
measured and reported; nothing over 1 GB is downloaded without approval. On a
CPU-only host, local text-to-video is not realistic and that is stated, not
worked around.

## 2. Data model

```
VideoProject {
  id, title, language, voice, target_duration_s, version,
  style_bible { palette, fonts, illustration_prompt, motion_presets, caption_style },
  scenes: [Scene], status, created_at, updated_at
}

Scene {
  id, order, goal,                     # what this scene must teach
  narration_text,                      # spoken
  on_screen_text,                      # <= 12 words, enforced
  visual { type, spec, image_prompt, stock_query, diagram_spec },
  transition_in, transition_out,
  duration_s,
  audio_path, clip_path, content_hash, locked,
  versions: [{ narration_text, visual, duration_s, created_at }]
}
```

`content_hash = sha256(scene spec + referenced asset bytes + renderer version)`.
Clips are cached by that hash, so an unchanged scene never re-renders.

### Where the purple "Freebuff" badge comes from

Investigate before M1 sign-off: candidate sources are (a) the generated
`player.html` template, (b) a shared CSS/asset in `backend/app/static/videos`,
(c) a stock image/illustration. The finding is written here with the file and
line. If it is our own template, it is removed or made a per-project credit.

## 3. Pipeline

1. **Plan** — outline: hook, 3–6 beats, recap, from topic + duration + audience.
2. **Scenes** — each scene generated from the outline *and the neighbour
   summaries*, with limited parallelism (one request at a time on Ollama).
3. **Director pass** — one LLM call over the storyboard JSON with a strict
   validator: continuity, repetition, pacing, transitions, hook and recap. It
   returns a **patch**, never a rewrite of the whole storyboard.
4. **TTS per scene** — voice from the project, duration derived from the audio.
5. **Render per scene** — deterministic frames → MP4 clip per scene.
6. **Stitch** — ffmpeg: crossfade video + audio crossfade + `loudnorm` → MP4.

Failure rule: no fabricated fallback content. If a stage fails, retry the next
provider/Ollama, then surface a clear error with **Retry**.

## 4. Per-chunk editing (the actual feature)

Filmstrip of scenes; click a scene to edit narration, on-screen text, visual
type, image prompt, duration.

Buttons: *Ask AI to change this scene* (natural language → patch for this scene
only), regenerate narration / visuals / both, lock, duplicate, delete, add after,
drag to reorder, version history with restore, instant single-scene preview,
**Apply** to re-stitch.

Rules:
- A locked scene is never touched by the director pass or a global action.
- "Ask AI" scoped to one scene must return a patch containing only that scene's
  fields; the validator rejects anything else.

## 5. Incremental render (acceptance test)

Edit scene 3's narration, then Apply:

- every other scene's `clip_path` keeps the **identical** hash and mtime,
- scene render time ≤ 60 s for a 10 s scene,
- re-stitch time ≤ 15 s,
- the edit-one-scene test prints all three numbers.

## 6. Continuity

After an edit, a text-only check compares the changed scene against its two
neighbours and **suggests** fixes (e.g. "Scene 4 starts with 'As we saw…' but
scene 3 changed"). Neighbours are never regenerated automatically.

## 7. Visual quality

Every scene must carry motion that explains the idea:

- designed animated templates: hero text, building diagram, comparison, steps,
  chart, equation/code — with entrance/emphasis motion, no static slide;
- AI illustrations per scene from free providers (terms, licence and rate limits
  **verified before use**, results cached, one consistent style prompt);
- optional stock footage (Pexels/Pixabay, attribution required);
- camera motion and parallax on illustrations; word-synced animated captions;
- subtle animated background; real transitions (no hard cuts every time).

Quality gate per video: no static stretch > 3 s; ≤ 25 words on screen; an
animated visual in every scene; no identical layout twice in a row; duration
within ±10 % of the request.

## 8. Rendering and voice

- HTML/SVG/Canvas scenes rendered deterministically at 30 fps via the installed
  Playwright, encoded with ffmpeg. Any animation library must be MIT/Apache —
  licence checked before adding.
- Voice: `edge-tts` (verify current terms) with English / Arabic MSA / Egyptian
  voices; Piper as the offline fallback; voice chosen per project.

## 9. No text leaks

Citation markers (`[Web 1: …]`, `[Source: …]`) are stripped from every on-screen
text; sources appear only in a final credits scene.

## 10. Milestones and evidence

| Milestone | Scope | Evidence |
|---|---|---|
| M1 | data model, storyboard generation, director pass, editor UI (text only) | storyboard JSON, director patch, editor screenshot |
| M2 | render pipeline (templates, captions, audio), per-scene cache, edit-one-scene test | 60 s MP4, hashes before/after, timings, ffprobe |
| M3 | illustrations + stock + camera motion | contact sheet (12 frames), motion-energy numbers |
| M4 | Arabic, style presets, MP4/DOCX/SRT exports | Arabic video, exports, ffprobe |

Each milestone needs a real 60 s video produced **from the UI**, a 12-frame
contact sheet, motion-energy numbers, timings and ffprobe output.

## 11. Free keys (`docs/FREE_KEYS.md`)

Documented with the current free terms verified at the time of writing:
Pexels, Pixabay, Hugging Face token, Cloudflare Workers AI (account id + token).
The pipeline must still render a reduced-visual video with **no** keys at all.

## 12. Risks

- CPU-only rendering: 30 fps Playwright capture of 60 s of video is the slowest
  step; per-scene caching is what makes editing tolerable.
- TTS Arabic quality and timing drift; word timestamps must be checked against
  the actual audio duration.
- Free stock APIs change their terms and rate limits; that is why keys are
  optional and the fallback is designed motion graphics.
