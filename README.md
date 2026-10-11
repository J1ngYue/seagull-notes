# Seagull Notes

English | [简体中文](README_CN.md)

Turn Bilibili, YouTube, and local media into **illustrated notes, mind maps, Markdown, and an offline HTML notebook**.

Seagull Notes combines a Codex skill with local Python helpers. The helpers extract source material and render the notebook; your AI client reads the material and writes the notes. This workflow does not require a separate note-generation API key.

- **Captions first.** Prefer available platform captions, including automatic captions, and retain their timestamps.
- **Automatic Bilibili collection.** BV links use the local collector and reuse complete caption caches. `--anonymous` explicitly skips credentials.
- **Optional local transcription.** Download accessible audio or process a local file only when ASR is explicitly enabled.
- **Browser sign-in when needed.** Let the user complete sign-in in Codex's in-app browser, then read what that session can access.
- **Illustrated delivery.** Summaries, takeaways, chapters, source images, explanatory diagrams, and a mind map in a self-contained HTML file.

![From video link to illustrated notes](examples/workflow-en.svg)

## Quick start

Requires Python 3.10 or later. A dedicated Python environment is recommended.

```bash
git clone https://github.com/J1ngYue/seagull-notes.git
cd seagull-notes
python -m pip install -e ".[notes,browser]"
```

On Windows, use the absolute path to your actual Python installation instead of a Microsoft Store alias. For example:

```powershell
& 'D:\software\Anaconda\python.exe' -m pip install -e '.[notes,browser]'
```

Copy `skill/` into your client's skills directory as `seagull-notes`, for example `~/.agents/skills/seagull-notes/`. Install the Python project first so a copied skill can import its helpers. You can also use the skill directly from the checkout.

Ask Codex:

> Use seagull-notes to turn this video into illustrated Chinese notes: VIDEO_URL

The included skill instructions and notebook interface are currently in Chinese. This English README describes the same workflow.

Send a link; the skill handles collection, import, reading, illustrations, rendering, and review. Your only normal intervention is sign-in or platform verification when required. For accessible captioned videos, the workflow targets a complete illustrated notebook within 45 minutes after sign-in. This is a processing target, not a guarantee for blocked sources, missing captions, or unusually large material.

## Choosing a source path

| Path | Benefits | Trade-offs |
| --- | --- | --- |
| Read platform captions after browser sign-in | Usually faster when captions exist; no ASR model download | Requires user sign-in; captions may contain errors, and access or export can still fail |
| Try anonymous audio transcription | No platform account is needed when the audio is publicly accessible | Requires audio and model downloads; usually slower, with possible recognition errors |

Bilibili BV links automatically use the caption collector. Other sources use available platform captions or browser exports. Anonymous mode remains an explicit option; ASR requires explicit authorization. The skill does not ask the user to repeat an already selected path. Neither path guarantees access to private, paid, region-restricted, or blocked videos. Video descriptions and AI summaries are not substitutes for a full transcript.

An existing, valid sign-in session is reused without asking the user to sign in or choose again. Before offering local ASR, the skill checks the installed dependencies and complete model cache: if the model is missing, it explains that a model download is required (approximately 3 GB for the default large-v3), with additional setup time and disk space.

### Fetch anonymous captions

```bash
python skill/scripts/fetch.py "VIDEO_URL" --anonymous
```

By default, this command does not download the video, run ASR, or download a model. It writes JSON to stdout and progress messages to stderr:

- `content`: extracted text.
- `segments`: available `start`, `end`, and `text` values; times are in seconds.
- `origin`: the actual source, such as `platform_subtitle`, `subtitle_file`, or `asr`.
- `has_more` and `next_offset`: pagination when `--offset` and `--max-chars` are used.

Read every page before writing the note.

### Enable local ASR

```bash
python -m pip install -e ".[notes,asr]"
python -m seagull_notes.cli prepare-model
python skill/scripts/fetch.py "VIDEO_URL" --anonymous --allow-asr
```

The default large-v3 model is approximately 3 GB. Model preparation is an explicit operation. Complete cached models load from their local snapshot; an empty cache directory is not treated as a usable model. Downloaded audio conversion requires FFmpeg and ffprobe.

ASR defaults to CUDA with float16. For CPU operation, set `SEAGULL_NOTES_ASR_DEVICE=cpu` and `SEAGULL_NOTES_ASR_COMPUTE=int8`. `SEAGULL_NOTES_ASR_MODEL` selects the model size.

Local files use the same helper:

```bash
python skill/scripts/fetch.py "/absolute/path/lecture.wav" --allow-asr
python skill/scripts/fetch.py "/absolute/path/captions.srt"
```

Transcription is local speech recognition, not platform-generated captions. Its timestamps are preserved on both fresh runs and cache hits.

## Render an illustrated notebook

```bash
python skill/scripts/notebook.py examples/notebook.json --out data/artifacts/demo
```

Open `data/artifacts/demo.html`. The included example illustrates the interface, rather than claiming to summarize a real video. The warm paper layout includes a cover, takeaway cards, chapter navigation, images, a mind map, Markdown, source details, and PDF printing.

The AI client prepares the JSON input; the renderer does not generate a summary. See [the input format](skill/references/notebook-format.md). Use `source_url` for a web source or `source_ref` for an existing local file's absolute path. Local timestamps are position labels; web timestamps link back to the video.

Use verified video frames for screenshots and label explanatory diagrams clearly. Images are embedded in HTML for offline reading; Markdown retains local image paths, so keep those files when moving the Markdown output.

### LaTeX formulas and one-click copying

Use `$...$` for inline math and `$$...$$` for display math in section Markdown. For example, `$$\theta_{t+1}=\theta_t-\eta\nabla L(\theta_t)$$`. Escape backslashes when writing JSON. Code blocks remain code.

Formulas are typeset with bundled KaTeX. Click a formula, or focus it and press Enter/Space, to copy the original LaTeX without the delimiters. The generated HTML includes the renderer and font files, so math works offline. The vendored KaTeX 0.19.0 assets are MIT-licensed; its license is preserved in `skill/assets/katex/LICENSE`.

### Generate numeric figures

```bash
python -m pip install -e ".[plots]"
python skill/scripts/plot.py examples/gradient-plot.json --out data/artifacts/gradient
```

The helper plots supplied numeric data and ordered update points, with real scales, numbered steps, and separate value labels. It exports SVG and PNG, checks for detected text clipping and overlap, and does not infer data from captions. Mark generated illustrations with `kind: "diagram"` to preserve their aspect ratio. Readers can click notebook images to inspect the full figure. See [figure guidance](skill/references/note-figures.md).

## Browser access, storage, and MCP

### Automatic local Bilibili caption collection

```bash
python -m pip install -e ".[notes,browser]"
python skill/scripts/fetch.py "https://www.bilibili.com/video/BV1LwHv6LEYz/" --local-browser
```

The collector reuses a dedicated Chrome profile in the background and verifies sign-in first. A valid session skips the login page. When authentication is needed, it prints a local `LOGIN_URL`; Codex opens this page visibly in its in-app browser. Scan the Bilibili QR code with the Bilibili app and confirm on your phone once; collection resumes automatically. This avoids relying on a separate Chrome window becoming visible. The collector profile is separate from both the in-app browser and your normal Chrome profile. Installed Chrome is preferred; otherwise install Chromium with `python -m playwright install chromium`.

`--local-browser` is optional for BV links: the default command selects it automatically unless an explicit credential or anonymous option is supplied. Valid full-caption caches are reused before launching Chrome or requesting sign-in. `cache_hit` and `collected_at` retain provenance; `--refresh` requests an updated platform copy. `collection_seconds` measures only the collection stage, not AI note generation.

Full caption JSON and SRT files are saved automatically under `data/captions/`. The existing `content`, `segments`, and `origin` output feeds the note workflow directly, with no manual export or import. The collector preserves the selected `p` and reports the first and last caption times for coverage review. It fetches platform captions, without audio/video downloads or ASR models, and does not export cookie files. Platform restrictions still apply. Currently it accepts full Bilibili BV links; YouTube and other sources retain their existing workflow.

The in-app browser and the Python downloader are separate sessions. Signing in through the browser does not automatically pass cookies to Python. YouTube transcript export and other platform caption access depend on the capabilities exposed by the current browser. See [the browser workflow](skill/references/browser-subtitles.md).

Models, media, cookies, databases, and generated notes remain outside Git. `SEAGULL_NOTES_HOME` overrides the project data location. Source text enters your AI client's context when it writes the notes; whether that context goes to a cloud service depends on the client.

The repository also contains legacy webpage, PDF, CLI, and MCP helpers. MCP is optional:

```bash
python -m pip install -e ".[mcp]"
python -m seagull_notes.server
```

Use a dedicated environment for MCP's server dependencies. The skill, renderer, caption fetcher, and local ASR do not require MCP. The legacy CLI's direct generation mode uses a rule-based fallback when no server-side model is configured; that is different from notes written by the AI client.

## Validation

```bash
python -m pip install -e ".[notes,plots,test]"
python -m pytest tests -q
```

Tests cover captions, cache behavior, anonymous mode, timestamps, local source references, model completeness, notebook rendering, and the original pipeline. They do not require network access, a GPU, or a generation API. Platform restrictions need real-video checks.

The notebook presentation was inspired by [CuteNote](https://cutenote.cc/). This project is not affiliated with CuteNote.

Figure-generation guidance was informed by the Matplotlib and scientific-visualization skills in Scientific Agent Skills: Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). [Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
