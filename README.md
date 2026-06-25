# BirdNET-Go

Setup notes and documentation for running [BirdNET-Go](https://github.com/tphakala/birdnet-go)
on macOS (Apple Silicon). This directory will be expanded with more code and documentation
over time.

## Overview

BirdNET-Go is a real-time bird (and bat) sound identification application. It listens to an
audio source (microphone or RTSP stream), runs neural-network inference, and serves a web
dashboard of detections.

This project documents a **manual binary installation** following the official
[installation guide](https://github.com/tphakala/birdnet-go/wiki/installation#manual-binary-installation-all-platforms),
with the macOS-specific adjustments required to get it running.

## Environment

| Item | Value |
|---|---|
| Platform | macOS 26 (Tahoe), Apple Silicon (`arm64`) |
| BirdNET-Go version | `nightly-20260615` |
| Inference backends | ONNX Runtime + TensorFlow Lite (both bundled in the release tarball) |

## Layout

| Component | Location |
|---|---|
| Binary | `~/birdnet-go/birdnet-go` |
| Bundled libraries | `~/birdnet-go/libonnxruntime.dylib`, `~/birdnet-go/libtensorflowlite_c.dylib` |
| System-wide libraries | `/usr/local/lib/libonnxruntime.dylib`, `/usr/local/lib/libtensorflowlite_c.dylib` |
| Config | `~/.config/birdnet-go/config.yaml` (auto-created on first run) |
| Web dashboard | <http://localhost:8080> → redirects to `/ui/dashboard` |

## Installation

### 1. Dependencies (Homebrew)

```bash
brew install ffmpeg   # RTSP capture + non-WAV audio export (MP3/AAC/FLAC/Opus)
brew install sox      # spectrogram rendering in the web UI
```

### 2. Download and extract the binary

```bash
mkdir -p ~/birdnet-go && cd ~/birdnet-go
curl -fL -o birdnet-go-darwin-arm64.tar.gz \
  https://github.com/tphakala/birdnet-go/releases/latest/download/birdnet-go-darwin-arm64.tar.gz
tar xzf birdnet-go-darwin-arm64.tar.gz
```

The tarball bundles **both** shared libraries (`libonnxruntime.dylib`,
`libtensorflowlite_c.dylib`), so no separate library downloads are needed.

### 3. Install the libraries system-wide

```bash
sudo cp ~/birdnet-go/libonnxruntime.dylib \
        ~/birdnet-go/libtensorflowlite_c.dylib \
        /usr/local/lib/
```

> `sudo` needs a real interactive terminal — run this in **Terminal.app/iTerm**, not through
> a wrapper that can't prompt for a password.

### 4. macOS rpath fix (required)

> [!IMPORTANT]
> The shipped binary references its libraries as `@rpath/libtensorflowlite_c.dylib` but ships
> with **no `LC_RPATH` entries**. On macOS 26, `@rpath` with an empty rpath list is a hard
> failure — the app crashes at launch with `dyld: Library not loaded ... no LC_RPATH's found`,
> even with the libraries correctly installed in `/usr/local/lib`. Setting `DYLD_LIBRARY_PATH`
> works for direct launches but is stripped by System Integrity Protection under
> `nohup`/`sudo`/`launchd`.

Fix it permanently by adding an rpath to the binary and re-signing it (no `sudo` needed):

```bash
install_name_tool -add_rpath /usr/local/lib ~/birdnet-go/birdnet-go
codesign -f -s - ~/birdnet-go/birdnet-go   # re-sign: editing load commands invalidates the ad-hoc signature
```

> [!WARNING]
> Re-apply both commands whenever the binary is **updated or re-downloaded** — a fresh binary
> has no rpath and will fail to launch again.

## Running

```bash
~/birdnet-go/birdnet-go serve
```

Then open <http://localhost:8080>.

- First launch downloads the BirdNET v2.4 model (~45 MB), so the web server takes a few extra
  seconds to come up the first time.
- macOS prompts for **microphone permission** the first time an audio source is opened —
  grant it for live detection from the Mac's mic, or configure an RTSP stream in Settings.

To stop a background instance:

```bash
pkill -f "birdnet-go serve"
```

## Configuration

The config file is created on first run at `~/.config/birdnet-go/config.yaml` and can also be
edited from the web UI's **Settings** page. Key items:

- **Location (latitude/longitude)** — required for range filtering and the daylight filter;
  without it, species tracking defaults to `latitude=0` / equatorial hemisphere.
- **Audio source** — microphone device or RTSP stream URL.

## Useful commands

```bash
~/birdnet-go/birdnet-go --help        # list subcommands and flags
~/birdnet-go/birdnet-go serve         # start the realtime analyzer + web server
~/birdnet-go/birdnet-go benchmark     # run an inference benchmark
~/birdnet-go/birdnet-go authors       # print authors
otool -l ~/birdnet-go/birdnet-go | grep -A2 LC_RPATH   # verify the rpath fix is present
```

## References

- Installation guide: <https://github.com/tphakala/birdnet-go/wiki/installation>
- ONNX Runtime install notes: <https://github.com/tphakala/birdnet-go/wiki/ONNX-Runtime-Installation>
- Project: <https://github.com/tphakala/birdnet-go>
- Documentation: <https://birdnet-go.dev>
