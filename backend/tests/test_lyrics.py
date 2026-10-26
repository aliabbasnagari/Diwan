from pathlib import Path

from app.library import lyrics


def test_lrc_path_swaps_extension():
    assert lyrics.lrc_path(Path("/lib/Artist/Album/01 - Title.mp3")) == Path(
        "/lib/Artist/Album/01 - Title.lrc"
    )


def test_read_lyrics_missing_returns_none(tmp_path):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake-audio")
    assert lyrics.read_lyrics(track) is None


def test_write_then_read_lyrics(tmp_path):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake-audio")

    lyrics.write_lyrics(track, "[00:01.00] Hello\n[00:02.00] World")

    assert lyrics.lrc_path(track).exists()
    assert lyrics.read_lyrics(track) == "[00:01.00] Hello\n[00:02.00] World\n"


def test_write_empty_text_clears_existing_lyrics(tmp_path):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake-audio")
    lyrics.write_lyrics(track, "some lyrics")
    assert lyrics.lrc_path(track).exists()

    lyrics.write_lyrics(track, "   ")

    assert not lyrics.lrc_path(track).exists()


def test_write_empty_text_is_noop_when_nothing_exists(tmp_path):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake-audio")
    lyrics.write_lyrics(track, "")
    assert not lyrics.lrc_path(track).exists()


def test_move_companion_moves_file_to_new_location(tmp_path):
    old_track = tmp_path / "old.mp3"
    old_track.write_bytes(b"fake-audio")
    lyrics.write_lyrics(old_track, "lyrics here")

    new_dir = tmp_path / "newdir"
    new_dir.mkdir()
    new_track = new_dir / "new.mp3"
    new_track.write_bytes(b"fake-audio")

    lyrics.move_companion(old_track, new_track)

    assert not lyrics.lrc_path(old_track).exists()
    assert lyrics.read_lyrics(new_track) == "lyrics here\n"


def test_move_companion_without_source_is_noop(tmp_path):
    old_track = tmp_path / "old.mp3"
    new_track = tmp_path / "new.mp3"

    lyrics.move_companion(old_track, new_track)  # should not raise

    assert not lyrics.lrc_path(new_track).exists()


def test_move_companion_same_path_is_noop(tmp_path):
    track = tmp_path / "song.mp3"
    track.write_bytes(b"fake-audio")
    lyrics.write_lyrics(track, "lyrics")

    lyrics.move_companion(track, track)

    assert lyrics.read_lyrics(track) == "lyrics\n"


def test_move_companion_overwrites_existing_destination(tmp_path):
    old_track = tmp_path / "old.mp3"
    old_track.write_bytes(b"fake-audio")
    lyrics.write_lyrics(old_track, "new lyrics")

    new_track = tmp_path / "new.mp3"
    new_track.write_bytes(b"fake-audio")
    lyrics.write_lyrics(new_track, "stale lyrics")

    lyrics.move_companion(old_track, new_track)

    assert lyrics.read_lyrics(new_track) == "new lyrics\n"
