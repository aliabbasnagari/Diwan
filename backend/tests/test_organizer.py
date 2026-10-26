from app.library import lyrics, organizer


def test_sanitize_strips_invalid_chars():
    assert organizer.sanitize('My: Song/Name?') == "My SongName"


def test_sanitize_empty_uses_fallback():
    assert organizer.sanitize("   ", "Unknown") == "Unknown"


def test_folder_artist_prefers_albumartist():
    tags = {"albumartist": "Various Artists", "artist": "Solo"}
    assert organizer.folder_artist(tags) == "Various Artists"


def test_folder_artist_falls_back_to_artist():
    tags = {"albumartist": "", "artist": "Solo"}
    assert organizer.folder_artist(tags) == "Solo"


def test_folder_artist_falls_back_to_unknown():
    assert organizer.folder_artist({}) == "Unknown Artist"


def test_build_library_path_dedupes_collisions(tmp_path):
    p1 = organizer.build_library_path(tmp_path, "Artist", "Album", "Title", None, ".mp3")
    p1.write_bytes(b"x")

    p2 = organizer.build_library_path(tmp_path, "Artist", "Album", "Title", None, ".mp3")

    assert p1 != p2
    assert p2.name == "Title (2).mp3"


def test_reorganize_track_moves_and_renames(tmp_path):
    old_path = tmp_path / "Old Artist" / "Old Album" / "Old Title.mp3"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"audio-bytes")

    new_path = organizer.reorganize_track(
        old_path, tmp_path, artist="New Artist", album="New Album", title="New Title", track_number="3"
    )

    assert new_path == tmp_path / "New Artist" / "New Album" / "03 - New Title.mp3"
    assert new_path.read_bytes() == b"audio-bytes"
    assert not old_path.exists()
    assert not (tmp_path / "Old Artist").exists()  # emptied-out folders cleaned up


def test_reorganize_track_is_noop_if_already_correct(tmp_path):
    path = tmp_path / "Artist" / "Album" / "Title.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")

    result = organizer.reorganize_track(path, tmp_path, artist="Artist", album="Album", title="Title")

    assert result == path
    assert path.exists()


def test_reorganize_track_moves_companion_lyrics(tmp_path):
    old_path = tmp_path / "Artist" / "Album" / "Title.mp3"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(b"audio")
    lyrics.write_lyrics(old_path, "la la la")

    new_path = organizer.reorganize_track(
        old_path, tmp_path, artist="New Artist", album="New Album", title="Title"
    )

    assert lyrics.read_lyrics(new_path) == "la la la\n"
    assert not lyrics.lrc_path(old_path).exists()
