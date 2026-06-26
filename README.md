# BirdScreen

Turn the birds you actually hear into a living piece of art on the wall.

BirdScreen listens for birds with [BirdNET-Go](https://github.com/tphakala/birdnet-go),
then generates a watercolor field-guide poster of the species heard — set in the real
location, season, time of day and weather — and displays it on a **Samsung The Frame** TV.
As the day goes on and new birds are heard (and the light and weather change), the poster
is regenerated so the art on the wall stays current.

> Status: the **TV integration** and the **Gemini poster pipeline** (prompt → image →
> upscale → labels → TV) are working end-to-end. Still to come: wiring BirdNET-Go's detections
> into the pipeline, and deciding the runtime/cadence model (see [Roadmap](#roadmap)).

## How it works

```
BirdNET-Go (audio → species)          ← detections over a rolling daily window
        │
        ▼
make-poster:  lat/lon + time + species
        │  ├─ reverse geocode (OpenStreetMap Nominatim) → place name
        │  ├─ current weather (yr.no / MET Norway)
        │  └─ season + scenery + light (Gemini text model, location-aware)
        ▼
   dynamic prompt  →  Gemini image model  →  poster
        │
        ├─ (optional) Real-ESRGAN super-resolution → native 4K (3840×2160)
        ├─ (optional) composite our own title + species labels (Pillow)
        ▼
   Samsung The Frame TV  (Art Mode)
```

Everything is driven by structured, *dynamic* inputs so the image reflects the real moment:
the **season/foliage** (tiny spring leaves, lush summer, golden autumn, bare snowy winter),
the **time-of-day light** (incl. Nordic white-night summer evenings), and the **live weather**
(sun, cloud, rain, snow) are each turned into descriptive text and fed to the model.

## Project layout

A [uv](https://docs.astral.sh/uv/) Python project (package `birdscreen`, `src/` layout).

| Module | Purpose |
|---|---|
| `samsung_tv.py` | Connect to / identify Frame TVs; upload + display art (`check-tv`, `upload-art`) |
| `geocode.py` | Reverse geocode lat/lon → place name (Nominatim) |
| `weather.py` | Current weather from yr.no (MET Norway) |
| `season.py` | Location-aware season/foliage/scenery/light via a Gemini text model |
| `poster.py` | Build the dynamic image prompt (`build-prompt`) |
| `gemini.py` | Gemini image generation + retry (`generate-poster`) |
| `images.py` | Frame-fit / resize helpers |
| `upscale.py` | Real-ESRGAN super-resolution to native 4K (`upscale`) |
| `labels.py` | Composite our own title + species legend (Pillow) |
| `usage.py` | Token-usage + estimated-cost logging |
| `pipeline.py` | End-to-end orchestration (`make-poster`) |

## Quick start

```bash
# 1. Install dependencies (uv manages the venv + Python 3.13)
uv sync                     # core
uv sync --extra upscale     # + Real-ESRGAN upscaler (pulls torch/spandrel)

# 2. Configure your Gemini API key
cp .env.example .env        # then edit: GEMINI_API_KEY=...   (from aistudio.google.com/apikey)

# 3. Generate a poster
uv run make-poster --lat 63.446827 --lon 10.421906 \
  --bird "Pica pica=Skjære" --bird "Erithacus rubecula=Rødstrupe"
```

Posters are written to `posters/` with a date-first, lexically-sortable filename that
includes the location, species, model and an auto-incrementing counter, e.g.
`2026-09-15T1400_Trondheim-Norway_Blameis-…-Ringdue_gemini-3-pro-image_01.jpg`.

### Commands

| Command | What it does |
|---|---|
| `make-poster` | Full pipeline: inputs → prompt → image → (upscale) → (labels) → file (+ optional `--tv`) |
| `build-prompt` | Just build + print the prompt (no image) |
| `generate-poster` | Generate an image from a raw prompt |
| `upscale` | Super-resolve an image to native 4K (Real-ESRGAN) |
| `check-tv` | Identify a Frame TV / verify Art Mode |
| `upload-art` | Upload + display an image on a Frame TV |

Key `make-poster` flags: `--when`, `--weather-condition/--weather-temp`, `--language`
(default Norwegian), `--title` (default "Hørt i dag"), `--size`, `--model`, `--image-size`,
`--upscale`, `--no-labels`, `--tv`. Every run prints token usage and an estimated cost.

## Image model options

Gemini's native image models ("Nano Banana"). Pricing is image-output per 1M tokens
(paid tier); per-image figures are what we measured on these posters.

| Model | Per image | Craft | Text / labels | Notes |
|---|---|---|---|---|
| **`gemini-3-pro-image`** (Nano Banana Pro) | ~$0.21–0.33 | ★★★ best | ✅ correct, *beside each bird* | Default. 4K. |
| `gemini-3.1-flash-image` (Nano Banana 2) | ~$0.07–0.15 | ★★ | ↑ better than 2.5 (untested here) | Middle ground; 1K–4K tiers. |
| `gemini-2.5-flash-image` (Nano Banana) | **~$0.039** | ★★ good | ❌ garbled Latin, mislabels | Cheapest; pair with `--no-labels` + our labels. |
| ~~Imagen 4~~ | — | — | — | Deprecated. |

**Pros / cons**

- **Pro** — the premium choice: richest linework/washes and depth, and it renders the
  Norwegian + Latin captions correctly next to each bird. Cost is the downside, and note that
  **lowering the resolution tier barely reduces Pro's cost** — its "reasoning core" spends a
  roughly fixed pool of reasoning tokens (we measured 1K $0.25 / 2K $0.23 / 4K $0.31, i.e.
  within run-to-run noise). So generate Pro at 4K; don't drop resolution to save money.
- **Flash (2.5)** — ~5–8× cheaper and the *art* is genuinely lovely, but it renders text
  badly (misspelled/mislabelled species). Solution below: have it paint **no** text and add
  the labels ourselves. Its native output is only ~1 MP, so it also needs upscaling.
- **Flash (3.1 / Nano Banana 2)** — newer, better text and explicit 1K–4K tiers, priced
  between the two; not yet evaluated in this project.

**Recommendation:** Pro for the premium / "hero" poster; **Flash + our labels + upscaler** for
cheap, frequent intra-day regenerations.

## Super-resolution (upscale to 4K)

The Samsung Frame panel is native **3840×2160 (4K UHD, 16:9)**. Gemini's output rarely matches
that exactly, so `make-poster` normalizes to native:

- **Pro at 4K** renders *larger* than UHD (~5504×3072) → we **downscale** to 3840×2160 (crisp).
- **Flash** renders only ~1344×768 → we **upscale** with `--upscale`.

Upscaling uses **Real-ESRGAN** (`RealESRGAN_x4plus`) via
[spandrel](https://github.com/chaiNNer-org/spandrel) + PyTorch, running on the Apple GPU
(**MPS**), tiled to bound memory. It's a *restoration* model, not a plain resize — it cleans up
edges/linework and compression artifacts, so the upscaled flash art genuinely looks higher
quality, not just bigger. Model weights auto-download to `models/` on first use.

```bash
uv run --extra upscale make-poster … --model gemini-2.5-flash-image --upscale
uv run --extra upscale upscale some_image.png -o out.jpg          # standalone, → 4K
uv run --extra upscale upscale some_image.png --model realesrgan-x4plus-anime
```

It's an **optional** dependency group (`uv sync --extra upscale`) so torch doesn't burden the
core install.

## Our own labels (the cheap flash path)

Because flash can't spell, we decouple text from the model:

1. `--no-labels` tells the prompt to paint **only birds and scenery — no text at all**, and to
   leave breathing room around the edges.
2. We upscale to 4K.
3. `labels.py` composites the **title** and a **species legend** (common name + italic Latin)
   ourselves with Pillow (Georgia), matted into slim parchment margins so nothing overlaps the
   artwork. The text is always correct because we own it.

Result: flash-quality art with perfect labels at **~$0.04** — e.g.
`uv run --extra upscale make-poster … --model gemini-2.5-flash-image --no-labels --upscale`.

## Samsung The Frame TVs

Uses [`samsungtvws`](https://github.com/xchwarze/samsung-tv-ws-api). Two TVs are targeted:

| TV | IP | Model | Art API | Note |
|---|---|---|---|---|
| 55" 2nd floor (main target) | `192.168.1.219` | `UE55LS003` (2017) | `1.07` | Needs the WebSocket-binary upload fallback |
| 75" 3rd floor | `192.168.1.28` | `TQ75LS03FWUXXC` (2024) | `5.0.1.0` | Standard D2D-socket upload |

The older 2017 Frame rejects the modern D2D-socket upload (`send_image error -1`); `upload_image`
automatically falls back to the single-frame WebSocket-binary path. Connecting prompts an
"Allow" popup on the TV; per-TV auth tokens are cached in `.tv-token*` (gitignored).

```bash
uv run check-tv 192.168.1.219 --art-ws
uv run upload-art 192.168.1.219 poster.jpg --token-file .tv-token-219
# or end-to-end:
uv run --extra upscale make-poster … --tv 192.168.1.219 --token-file .tv-token-219
```

---

## BirdNET-Go (the audio source)

BirdNET-Go does the real-time bird-sound identification; BirdScreen will read the day's
detections from its HTTP API. Installed as a manual binary on macOS (Apple Silicon).

| Component | Location |
|---|---|
| Binary | `~/birdnet-go/birdnet-go` |
| Libraries (system-wide) | `/usr/local/lib/libonnxruntime.dylib`, `…/libtensorflowlite_c.dylib` |
| Config | `~/.config/birdnet-go/config.yaml` |
| Web dashboard / API | <http://localhost:8080> |

### Install

```bash
brew install ffmpeg sox                       # RTSP/audio + spectrograms
mkdir -p ~/birdnet-go && cd ~/birdnet-go
curl -fL -o birdnet-go-darwin-arm64.tar.gz \
  https://github.com/tphakala/birdnet-go/releases/latest/download/birdnet-go-darwin-arm64.tar.gz
tar xzf birdnet-go-darwin-arm64.tar.gz
sudo cp libonnxruntime.dylib libtensorflowlite_c.dylib /usr/local/lib/   # run in a real terminal
```

> [!IMPORTANT]
> **macOS rpath fix (required).** The binary references its libraries as `@rpath/…` but ships
> with **no `LC_RPATH`**, so on macOS 26 it crashes at launch (`dyld: … no LC_RPATH's found`)
> even with the libraries in `/usr/local/lib`. Fix it (no `sudo`), and **re-apply after any
> binary update**:
> ```bash
> install_name_tool -add_rpath /usr/local/lib ~/birdnet-go/birdnet-go
> codesign -f -s - ~/birdnet-go/birdnet-go    # re-sign; editing load commands voids the signature
> ```

```bash
~/birdnet-go/birdnet-go serve     # → http://localhost:8080  (set your lat/lon in config)
```

## Configuration

- `.env` — `GEMINI_API_KEY` (required), optional `BIRDSCREEN_IMAGE_MODEL`,
  `BIRDSCREEN_TEXT_MODEL`. Gitignored.
- External APIs used keyless: yr.no (MET Norway) weather, OpenStreetMap Nominatim geocoding —
  both require only a descriptive User-Agent (already set).

## Roadmap

- **BirdNET-Go integration** — read the day's species from its HTTP API and feed `make-poster`.
- **Runtime model** — persistent service vs. scheduled job; polling vs. push for new detections.
- **Cadence & update rules** — regenerate on each new species vs. a fixed interval (e.g. 4×/day
  to bound cost while keeping light/weather dynamic), with a daily generation cap.
- Durable TV pairing for the 55" Frame; old-poster cleanup in the TV gallery.

## References

- BirdNET-Go: <https://github.com/tphakala/birdnet-go> ·
  [install guide](https://github.com/tphakala/birdnet-go/wiki/installation)
- Gemini image generation: <https://ai.google.dev/gemini-api/docs/image-generation>
- samsung-tv-ws-api: <https://github.com/xchwarze/samsung-tv-ws-api>
- Real-ESRGAN: <https://github.com/xinntao/Real-ESRGAN> · spandrel:
  <https://github.com/chaiNNer-org/spandrel>
- yr.no / MET Norway API: <https://api.met.no/> · Nominatim:
  <https://nominatim.org/>
