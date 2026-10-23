"""A poster that can't reach a sleeping TV is hung once the TV is back in Art Mode."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from birdscreen.config import TvConfig
from birdscreen.web import app

TV = TvConfig(name="Frame", ip="10.0.0.5", enabled=True)


class FakeTv:
    """Stands in for the TV on the network."""

    def __init__(self) -> None:
        self.awake = True
        self.art_mode: bool | None = True
        self.rejects = False  # answers on the network but refuses the upload
        self.probes = 0
        self.probe_timeout: float | None = None
        self.uploads: list[str] = []

    def is_reachable(self, _ip: str, timeout: float = 5.0) -> bool:
        self.probes += 1
        self.probe_timeout = timeout
        return self.awake

    def art_state(self, _ip: str, _token_file: str) -> tuple[bool, bool | None]:
        if not self.awake:
            raise TimeoutError("timed out")
        return True, self.art_mode

    def replace_art(self, _ip: str, image: Path, **_kwargs: object) -> str:
        if not self.awake:
            raise TimeoutError("[Errno 60] Operation timed out")
        if self.rejects:
            raise TimeoutError("waiting for 'Allow' on the TV")
        self.uploads.append(Path(image).read_text())
        return f"MY_F{len(self.uploads):04d}"


@pytest.fixture
def tv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeTv:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "posters").mkdir()
    for name in ("morning.jpg", "evening.jpg"):
        (tmp_path / "posters" / name).write_text(name)
    (tmp_path / "config.yaml").write_text("secret")
    app._tv_token_file(TV.ip).write_text("token")  # paired

    def prepare(src: Path, dst: Path) -> Path:
        # Keep the poster's name in the "frame-ready" file so uploads are identifiable.
        Path(dst).write_text(Path(src).read_text())
        return Path(dst)

    fake = FakeTv()
    monkeypatch.setattr(app, "load_config", lambda: SimpleNamespace(tvs=[TV]))
    monkeypatch.setattr(app, "prepare_for_frame", prepare)
    monkeypatch.setattr(app, "is_reachable", fake.is_reachable)
    monkeypatch.setattr(app, "art_state", fake.art_state)
    monkeypatch.setattr(app, "replace_art", fake.replace_art)
    monkeypatch.setattr(app, "_retry_backoff", {})
    return fake


def pending() -> str | None:
    path = app._tv_pending_file(TV.ip)
    return path.read_text() if path.exists() else None


def test_sleeping_tv_is_skipped_quickly_and_remembered(tv: FakeTv) -> None:
    tv.awake = False
    result = app._send_to_tvs("morning.jpg", automatic=True)

    assert not result.ok
    assert "retry" in result.message
    assert tv.probes == 1  # a quick check, no slow upload attempt
    assert tv.probe_timeout == app._TV_PROBE_TIMEOUT_S
    assert pending() == "morning.jpg"
    assert app._waiting_tvs([TV]) == [TV]


def test_retry_waits_while_asleep_then_hangs_on_wake(tv: FakeTv) -> None:
    tv.awake = False
    app._send_to_tvs("morning.jpg", automatic=True)

    app._retry_pending_hangs()
    assert tv.uploads == []

    tv.awake = True
    app._retry_pending_hangs()
    assert tv.uploads == ["morning.jpg"]
    assert pending() is None
    assert app._tv_art_file(TV.ip).read_text() == "MY_F0001"

    app._retry_pending_hangs()  # nothing left to do
    assert tv.uploads == ["morning.jpg"]


def test_retry_checks_reachability_once(tv: FakeTv) -> None:
    app._tv_pending_file(TV.ip).write_text("morning.jpg")

    app._retry_pending_hangs()
    assert tv.uploads == ["morning.jpg"]
    assert tv.probes == 1


def test_retry_waits_while_the_tv_is_being_watched(tv: FakeTv) -> None:
    app._tv_pending_file(TV.ip).write_text("morning.jpg")
    tv.art_mode = False  # on, showing a TV input

    app._retry_pending_hangs()
    app._retry_pending_hangs()
    assert tv.uploads == []
    assert pending() == "morning.jpg"
    assert app._retry_backoff == {}  # waiting, not failing

    tv.art_mode = True
    app._retry_pending_hangs()
    assert tv.uploads == ["morning.jpg"]


def test_only_the_newest_missed_poster_is_retried(tv: FakeTv) -> None:
    tv.awake = False
    app._send_to_tvs("morning.jpg", automatic=True)
    app._send_to_tvs("evening.jpg", automatic=True)

    tv.awake = True
    app._retry_pending_hangs()
    assert tv.uploads == ["evening.jpg"]


def test_successful_hang_cancels_the_retry(tv: FakeTv) -> None:
    tv.awake = False
    app._send_to_tvs("morning.jpg", automatic=True)

    tv.awake = True
    app._send_to_tvs("evening.jpg")  # e.g. hung by hand from the gallery
    app._retry_pending_hangs()
    assert tv.uploads == ["evening.jpg"]


def test_manual_send_waits_out_the_connect_and_queues_nothing(tv: FakeTv) -> None:
    tv.awake = False
    result = app._send_to_tvs("morning.jpg")

    assert not result.ok
    assert "retry" not in result.message
    assert tv.probes == 0  # a slow-waking TV still gets the full connect timeout
    assert pending() is None


def test_manual_send_does_not_block_behind_another_push(tv: FakeTv) -> None:
    with app._tv_lock:
        result = app._send_to_tvs("morning.jpg")
    assert not result.ok
    assert "right now" in result.message
    assert tv.uploads == []


def test_retry_skips_a_tick_while_another_push_runs(tv: FakeTv) -> None:
    app._tv_pending_file(TV.ip).write_text("morning.jpg")
    with app._tv_lock:
        app._retry_pending_hangs()
    assert tv.uploads == []
    assert pending() == "morning.jpg"


def test_retry_is_dropped_when_the_poster_is_gone(tv: FakeTv) -> None:
    tv.awake = False
    app._tv_pending_file(TV.ip).write_text("deleted.jpg")
    assert app._waiting_tvs([TV]) == []  # Status doesn't claim it's waiting

    app._retry_pending_hangs()
    assert pending() is None
    assert tv.probes == 0


def test_pending_name_cannot_escape_the_posters_folder(tv: FakeTv) -> None:
    app._tv_pending_file(TV.ip).write_text("../config.yaml")

    app._retry_pending_hangs()
    assert tv.uploads == []
    assert pending() is None


def test_pausing_a_tv_drops_its_missed_poster(tv: FakeTv, monkeypatch: pytest.MonkeyPatch) -> None:
    paused = TV.model_copy(update={"enabled": False})
    monkeypatch.setattr(app, "load_config", lambda: SimpleNamespace(tvs=[paused]))
    app._tv_pending_file(TV.ip).write_text("morning.jpg")
    assert app._waiting_tvs([paused]) == []

    app._retry_pending_hangs()
    assert pending() is None

    monkeypatch.setattr(app, "load_config", lambda: SimpleNamespace(tvs=[TV]))
    app._retry_pending_hangs()  # re-enabled: the stale poster isn't hung
    assert tv.uploads == []


def test_unpaired_tv_is_never_contacted_in_the_background(tv: FakeTv) -> None:
    app._tv_token_file(TV.ip).unlink()
    app._tv_pending_file(TV.ip).write_text("morning.jpg")

    app._retry_pending_hangs()
    assert tv.probes == 0
    assert pending() is None


def test_tv_that_refuses_upload_backs_off_then_gives_up(
    tv: FakeTv, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(app.time, "monotonic", lambda: clock[0])
    app._tv_pending_file(TV.ip).write_text("morning.jpg")
    tv.rejects = True

    app._retry_pending_hangs()  # failure 1
    assert pending() == "morning.jpg"

    clock[0] += 120  # next tick: still backing off, no new attempt
    probes = tv.probes
    app._retry_pending_hangs()
    assert tv.probes == probes

    for _ in range(app._RETRY_MAX_FAILURES - 1):
        clock[0] += app._RETRY_BACKOFF_S
        app._retry_pending_hangs()
    assert pending() is None  # gave up; no endless 'Allow' popups
    assert tv.uploads == []


def test_tv_dozing_off_mid_retry_is_not_a_failure(
    tv: FakeTv, monkeypatch: pytest.MonkeyPatch
) -> None:
    app._tv_pending_file(TV.ip).write_text("morning.jpg")

    def probe_then_sleep(ip: str, timeout: float = 5.0) -> bool:
        awake = tv.is_reachable(ip, timeout)
        tv.awake = False  # drops off right after answering
        return awake

    monkeypatch.setattr(app, "is_reachable", probe_then_sleep)
    app._retry_pending_hangs()
    assert app._retry_backoff == {}
    assert pending() == "morning.jpg"
