import pytest

from app.library import scanner


def test_encode_decode_roundtrip():
    value = "Artist/Album/01 - Title.mp3"
    encoded = scanner.encode_id(value)
    assert scanner.decode_id(encoded) == value


def test_encode_id_is_url_safe():
    encoded = scanner.encode_id("Weird & Name (feat. X)/Album")
    assert "/" not in encoded
    assert "+" not in encoded


def test_resolve_track_path_within_library(tmp_path):
    lib = tmp_path / "library"
    (lib / "Artist" / "Album").mkdir(parents=True)

    track_id = scanner.encode_id("Artist/Album/Title.mp3")
    resolved = scanner.resolve_track_path(lib, track_id)

    assert resolved == (lib / "Artist" / "Album" / "Title.mp3").resolve()


def test_resolve_track_path_rejects_escape(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()

    escape_id = scanner.encode_id("../outside.mp3")
    with pytest.raises(ValueError):
        scanner.resolve_track_path(lib, escape_id)
