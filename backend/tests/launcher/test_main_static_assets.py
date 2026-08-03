from __future__ import annotations

from pathlib import Path

import pytest

from pelican_town_specials.launcher.main import LauncherDependencies, run_launcher


class _Lock:
    def acquire(self) -> bool:
        return True

    def release(self) -> None:
        pass


class _Records:
    def read(self) -> None:
        return None

    def write(self, _record: object) -> None:
        raise AssertionError("server must not start for an outside-root index")

    def clear(self) -> None:
        pass

    def clear_if_matches(self, _record: object) -> bool:
        return False


class _ServerRunner:
    def __call__(self, *_args: object) -> object:
        raise AssertionError("server must not start for an outside-root index")


def test_outside_root_index_symlink_returns_stable_launcher_error(
    tmp_path: Path,
) -> None:
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    outside_index = tmp_path / "outside-index.html"
    outside_index.write_text("<main>outside</main>", encoding="utf-8")
    try:
        (static_dir / "index.html").symlink_to(outside_index)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    result = run_launcher(
        ["--workspace", str(tmp_path / "workspace"), "--port", "43127"],
        dependencies=LauncherDependencies(
            instance_lock_factory=lambda _workspace: _Lock(),
            runtime_record_store_factory=lambda _workspace: _Records(),  # type: ignore[arg-type]

            open_browser=lambda _url: None,
            wait_for_health=lambda _url, _timeout: None,
            server_runner=_ServerRunner(),  # type: ignore[arg-type]
            static_dir=static_dir,
            process_id=lambda: 1234,
        ),
    )

    assert result == 1
