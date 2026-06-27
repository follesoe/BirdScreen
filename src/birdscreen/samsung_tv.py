"""Test connectivity to a Samsung TV (specifically The Frame).

This is the first verification step for BirdScreen: confirm we can reach the TV,
identify the model, and verify it supports Art Mode (required for displaying the
generated bird poster).

Two levels of check:

1. **REST device info** (no pairing needed) — a plain HTTP request to the TV that
   returns model, name, and power state, and whether it is a Frame TV. This never
   triggers a popup on the TV.
2. **Art websocket** (opt-in, ``--art-ws``) — connects over the secure websocket
   (port 8002) and queries the Art API version / current artwork. The first time
   this runs, **the TV shows an "Allow / Deny" popup** that must be accepted; an
   auth token is then cached in the token file for future connections.

Usage::

    uv run check-tv 192.168.1.50
    uv run check-tv 192.168.1.50 --art-ws        # also do the websocket art test
    uv run check-tv --discover                    # find Samsung TVs via SSDP
    BIRDSCREEN_TV_HOST=192.168.1.50 uv run check-tv
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

import urllib3
from samsungtvws import SamsungTVWS, exceptions

from birdscreen.images import prepare_for_frame

# The Frame uses a self-signed cert on its secure websocket/REST endpoint;
# silence the noisy "InsecureRequestWarning" that results.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Secure websocket port used by The Frame for the Art API.
ART_WS_PORT = 8002
# Friendly name shown on the TV's "allow connection" popup.
CLIENT_NAME = "BirdScreen"
# Where the TV auth token is cached after the popup is accepted.
DEFAULT_TOKEN_FILE = os.environ.get("BIRDSCREEN_TV_TOKEN_FILE", ".tv-token")


def discover(timeout: float = 3.0) -> list[str]:
    """Find Samsung TVs on the local network via SSDP M-SEARCH.

    Best effort: a TV in deep standby may not respond. Returns a sorted list of
    responding IP addresses. macOS may prompt for local-network permission the
    first time this runs.
    """
    search_targets = [
        "urn:samsung.com:device:RemoteControlReceiver:1",
        "urn:dial-multiscreen-org:device:dial:1",
    ]
    found: set[str] = set()
    for target in search_targets:
        request = "\r\n".join(
            [
                "M-SEARCH * HTTP/1.1",
                "HOST: 239.255.255.250:1900",
                'MAN: "ssdp:discover"',
                "MX: 2",
                f"ST: {target}",
                "",
                "",
            ]
        ).encode()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        try:
            sock.sendto(request, ("239.255.255.250", 1900))
            while True:
                try:
                    _data, addr = sock.recvfrom(2048)
                except TimeoutError:
                    break
                found.add(addr[0])
        finally:
            sock.close()
    return sorted(found)


def get_device_info(host: str) -> dict[str, Any]:
    """Return the TV's REST device-info dict (raises on connection failure)."""
    tv = SamsungTVWS(host=host, name=CLIENT_NAME)
    return tv.rest_device_info()


def supports_art_mode(host: str) -> bool:
    """True if the TV reports Frame/Art-Mode support (REST only, no popup)."""
    tv = SamsungTVWS(host=host, name=CLIENT_NAME)
    return tv.art().supported()


def art_state(host: str, token_file: str) -> tuple[bool, bool | None]:
    """``(supports_art_mode, currently_in_art_mode)`` over the Art websocket.

    Authoritative (unlike REST ``FrameTVSupport``, which is unreliable on older
    Frames). Uses the cached token, so no popup once paired; the first call on an
    unpaired TV triggers the "Allow" popup. ``currently_in_art_mode`` is None if
    the TV doesn't report it.
    """
    tv = SamsungTVWS(host=host, port=ART_WS_PORT, token_file=token_file, name=CLIENT_NAME)
    art: Any = tv.art()
    supported = bool(art.supported())
    current: bool | None = None
    with contextlib.suppress(Exception):
        current = str(art.get_artmode()).lower() == "on"
    return supported, current


def check_art_websocket(host: str, token_file: str) -> dict[str, Any]:
    """Connect over the Art websocket and return version + current artwork.

    Triggers the TV "Allow" popup on first use. Returns a dict with the Art API
    version and the currently displayed artwork id.
    """
    tv = SamsungTVWS(host=host, port=ART_WS_PORT, token_file=token_file, name=CLIENT_NAME)
    art: Any = tv.art()
    result = {"api_version": art.get_api_version()}
    try:
        result["current"] = art.get_current()
    except Exception as exc:  # current artwork is a nice-to-have, not essential
        result["current_error"] = str(exc)
    return result


def _print_device_summary(info: dict[str, Any]) -> None:
    device = info.get("device", {})
    rows = [
        ("Name", device.get("name")),
        ("Model", device.get("modelName")),
        ("Type", device.get("type")),
        ("Frame support", device.get("FrameTVSupport")),
        ("Power state", device.get("PowerState")),
        ("Token auth", device.get("TokenAuthSupport")),
        ("OS", device.get("OS")),
        ("Wifi MAC", device.get("wifiMac")),
        ("Firmware", info.get("version")),
    ]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        if value is not None:
            print(f"  {label:<{width}} : {value}")


def _check_art_ws(host: str, token_file: str, *, as_json: bool, result: dict[str, Any]) -> bool:
    """Run the Art-websocket check, populate ``result``, return True on success."""
    if not as_json:
        print(
            f"\nConnecting over the Art websocket (port {ART_WS_PORT})...\n"
            "→ Accept the 'Allow' popup on the TV if it appears."
        )
    try:
        art = check_art_websocket(host, token_file)
    except Exception as exc:  # report and signal failure to the caller
        result["art_error"] = str(exc)
        if not as_json:
            print(f"✗ Art websocket failed: {exc}")
            print("  If a popup appeared on the TV, accept it and re-run.")
        return False

    result["art"] = art
    if not as_json:
        print(f"✓ Art API version: {art.get('api_version')}")
        if "current" in art:
            print(f"  Current artwork: {art['current']}")
        token = Path(token_file)
        if token.exists() and token.stat().st_size > 0:
            print(f"  Auth token cached in: {token_file}")
        else:
            print(
                "  Note: TV did not persist an auth token; the Allow popup "
                "may reappear on future connections."
            )
    return True


def check_connection(host: str, *, token_file: str, do_art_ws: bool, as_json: bool) -> int:
    """Run the connection checks against ``host``. Returns a process exit code."""
    result: dict[str, Any] = {"host": host}

    # 1) REST device info -----------------------------------------------------
    try:
        info = get_device_info(host)
    except Exception as exc:
        msg = f"Could not reach TV at {host}: {exc}"
        if as_json:
            print(json.dumps({"host": host, "ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"✗ {msg}")
            print("  Check the IP address and that the TV is powered on / on the network.")
        return 1

    result["device_info"] = info
    is_frame = str(info.get("device", {}).get("FrameTVSupport")).lower() == "true"
    result["is_frame"] = is_frame

    if not as_json:
        print(f"✓ Connected to TV at {host}")
        _print_device_summary(info)
        if is_frame:
            print("✓ Art Mode supported — this is a Frame TV. 🖼️")
        else:
            print("✗ This TV does not report Frame/Art-Mode support.")

    # 2) Optional Art websocket check ----------------------------------------
    if do_art_ws and not _check_art_ws(host, token_file, as_json=as_json, result=result):
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        return 2

    if as_json:
        print(json.dumps(result, indent=2, default=str))
    return 0 if is_frame else 3


def _upload_ws_binary(art: Any, data: bytes, *, file_type: str, matte: str) -> str:
    """Upload via the single-frame WebSocket-binary path (older Frames).

    Uses library internals because the public ``upload()`` only auto-selects this
    path for Art API 0.97, while the 2017 Frame (1.07) needs it too.
    """
    upload_id = art._new_request_uuid()
    art._upload_ws_binary_send_image(
        upload_id=upload_id, data=data, matte=matte or "none", file_type=file_type
    )
    done = art._wait_for_d2d(request_uuid=upload_id, wait_for_sub_event="image_added")
    return str(done["content_id"])


def upload_image(
    host: str,
    image_path: str | Path,
    *,
    token_file: str,
    file_type: str = "jpg",
    matte: str = "none",
    show: bool = True,
    art_mode: bool = True,
) -> str:
    """Upload an image to The Frame and (optionally) display it.

    Returns the ``content_id`` assigned by the TV. Connecting may trigger the
    TV's "Allow" popup if the device is not already paired (token cached).
    """
    tv = SamsungTVWS(host=host, port=ART_WS_PORT, token_file=token_file, name=CLIENT_NAME)
    art: Any = tv.art()
    data = Path(image_path).read_bytes()
    try:
        content_id = art.upload(data, file_type=file_type, matte=matte)
    except exceptions.ResponseError:
        # Older Frames (e.g. the 2017 first-gen, Art API 1.x) reject the modern
        # D2D-socket upload ("send_image ... error number -1"). Fall back to the
        # single-frame WebSocket-binary upload path, which those models accept.
        content_id = _upload_ws_binary(art, data, file_type=file_type, matte=matte)
    if show:
        art.select_image(content_id, show=True)
    if art_mode:
        # Not fatal: the image is uploaded and selected; the TV may just not switch
        # into Art Mode (e.g. it is currently powered on a TV input).
        with contextlib.suppress(Exception):
            art.set_artmode(True)
    return str(content_id)


def upload_main() -> None:
    parser = argparse.ArgumentParser(
        prog="upload-art",
        description="Upload an image (poster) to a Samsung The Frame TV and display it.",
    )
    parser.add_argument("host", help="TV IP address.")
    parser.add_argument("image", help="Path to the source image (PNG/JPG/...).")
    parser.add_argument(
        "--token-file",
        default=DEFAULT_TOKEN_FILE,
        help=f"Path to the TV auth token (default: {DEFAULT_TOKEN_FILE}).",
    )
    parser.add_argument("--matte", default="none", help="Frame matte style (default: none).")
    parser.add_argument(
        "--no-prepare",
        action="store_true",
        help="Upload the file as-is (skip JPEG conversion / Frame resize).",
    )
    parser.add_argument(
        "--no-show", action="store_true", help="Upload but do not select for display."
    )
    parser.add_argument(
        "--no-art-mode",
        action="store_true",
        help="Do not switch the TV into Art Mode after uploading.",
    )
    args = parser.parse_args()

    if args.no_prepare:
        upload_path = Path(args.image)
        file_type = upload_path.suffix.lstrip(".").lower() or "jpg"
        print(f"Uploading {upload_path} as-is ({file_type}).")
    else:
        out = Path("cache") / f"{Path(args.image).stem}-frame.jpg"
        upload_path = prepare_for_frame(args.image, dst=out)
        file_type = "jpg"
        print(f"Prepared Frame-ready JPEG: {upload_path}")

    print(f"Uploading to {args.host} (accept the TV popup if it appears)...")
    try:
        content_id = upload_image(
            args.host,
            upload_path,
            token_file=args.token_file,
            file_type=file_type,
            matte=args.matte,
            show=not args.no_show,
            art_mode=not args.no_art_mode,
        )
    except Exception as exc:
        print(f"✗ Upload failed: {type(exc).__name__}: {exc}")
        print("  If a popup appeared on the TV, accept it and re-run.")
        sys.exit(1)

    print(f"✓ Uploaded. content_id = {content_id}")
    if not args.no_show:
        print("  Selected for display. Put the TV in Art Mode to view it.")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="check-tv",
        description="Test connection to a Samsung TV (The Frame) for BirdScreen.",
    )
    parser.add_argument(
        "host",
        nargs="?",
        default=os.environ.get("BIRDSCREEN_TV_HOST"),
        help="TV IP address (or set BIRDSCREEN_TV_HOST).",
    )
    parser.add_argument(
        "--art-ws",
        action="store_true",
        help="Also test the Art websocket (may show an Allow popup on the TV).",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Scan the local network for Samsung TVs via SSDP and exit.",
    )
    parser.add_argument(
        "--token-file",
        default=DEFAULT_TOKEN_FILE,
        help=f"Path to cache the TV auth token (default: {DEFAULT_TOKEN_FILE}).",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON.")
    args = parser.parse_args()

    if args.discover:
        print("Searching for Samsung TVs via SSDP (a few seconds)...")
        hosts = discover()
        if hosts:
            print("Found candidate device(s):")
            for ip in hosts:
                print(f"  {ip}")
            print("\nRe-run with the IP, e.g.:  uv run check-tv <ip>")
        else:
            print("No devices responded. The TV may be off or not on this network.")
        sys.exit(0 if hosts else 1)

    if not args.host:
        parser.error("no TV host given — pass an IP, set BIRDSCREEN_TV_HOST, or use --discover")

    exit_code = check_connection(
        args.host,
        token_file=args.token_file,
        do_art_ws=args.art_ws,
        as_json=args.json,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
