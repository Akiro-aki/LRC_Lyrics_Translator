"""Shared fixture builders: create small tagged audio files in tmp dirs."""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest
from mutagen.flac import FLAC
from mutagen.id3 import ID3, SYLT, TALB, TIT2, TPE1, USLT
from mutagen.mp3 import MP3


def _minimal_mp3_bytes() -> bytes:
    """A tiny but structurally valid MP3 (ID3 header + 5 valid MPEG frames).

    mutagen requires several consecutive valid frames to accept the stream,
    so the frame header is repeated at the correct frame stride.
    """
    id3 = b"ID3\x04\x00\x00" + bytes([0, 0, 0, 0]) + b"\x00" * 10
    frame_len = 144 * 128000 // 44100  # 128kbps Layer III @44100 -> 417 bytes
    frame = b"\xff\xfb\x90\x00" + b"\x00" * (frame_len - 4)
    return id3 + frame * 5


@pytest.fixture
def mp3_path(tmp_path: Path) -> Path:
    path = tmp_path / "track.mp3"
    path.write_bytes(_minimal_mp3_bytes())
    return path


def tag_mp3(path: Path, *, title="Song Title", artist="Artist Name", album="Some Album",
            synced_text: str | None = None, plain_text: str | None = None) -> None:
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    if title:
        audio.tags.add(TIT2(encoding=3, text=[title]))
    if artist:
        audio.tags.add(TPE1(encoding=3, text=[artist]))
    if album:
        audio.tags.add(TALB(encoding=3, text=[album]))
    if synced_text:
        from audio2lrc.lrc.parser import parse_lrc

        pairs = [
            (line.text, int(line.time * 1000) if line.time is not None else 0)
            for line in parse_lrc(synced_text)
        ]
        audio.tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, text=pairs))
    if plain_text:
        audio.tags.add(USLT(encoding=3, lang="eng", desc="", text=plain_text))
    audio.save()


def minimal_flac_bytes() -> bytes:
    """A minimal valid FLAC (STREAMINFO only; mutagen can rewrite its tags)."""
    info = (44100 << 44) | (1 << 41) | (15 << 36)
    block = struct.pack(">HH", 4096, 4096) + b"\x00\x00\x00" + b"\x00\x00\x00"
    streaminfo = block + info.to_bytes(8, "big") + b"\x00" * 16
    return b"fLaC" + b"\x80" + len(streaminfo).to_bytes(3, "big") + streaminfo


@pytest.fixture
def flac_path(tmp_path: Path) -> Path:
    path = tmp_path / "track.flac"
    path.write_bytes(minimal_flac_bytes())
    return path


def tag_flac(path: Path, *, title="Song Title", artist="Artist Name", album="Some Album",
             lyrics: str | None = None, duration: int | None = None) -> None:
    f = FLAC(path)
    if title:
        f["title"] = title
    if artist:
        f["artist"] = artist
    if album:
        f["album"] = album
    if lyrics:
        f["lyrics"] = lyrics
    f.save()


def minimal_m4a_bytes() -> bytes:
    """A tiny structurally valid M4A (ftyp + mvhd/udta moov + mdat)."""
    ilst = struct.pack(">I", 8) + b"ilst"
    hdlr = (
        struct.pack(">I", 32)
        + b"hdlr"
        + struct.pack(">I", 0)
        + struct.pack(">I", 0)
        + b"mdir"
        + b"\x00" * 12
    )
    meta = struct.pack(">I", 8 + 4 + len(hdlr) + len(ilst)) + b"meta" + struct.pack(">I", 0) + hdlr + ilst
    udta = struct.pack(">I", 8 + len(meta)) + b"udta" + meta
    mvhd = (
        struct.pack(">I", 28)
        + b"mvhd"
        + struct.pack(">I", 0)
        + struct.pack(">II", 0, 0)
        + struct.pack(">II", 44100, 1323000)
    )
    moov = struct.pack(">I", 8 + len(mvhd) + len(udta)) + b"moov" + mvhd + udta
    ftyp = struct.pack(">I", 24) + b"ftyp" + struct.pack(">I", 0) + b"M4A " + b"mp42isom"
    mdat = struct.pack(">I", 0x10) + b"mdat" + b"\x00" * 8
    return ftyp + moov + mdat


@pytest.fixture
def m4a_path(tmp_path: Path) -> Path:
    path = tmp_path / "track.m4a"
    path.write_bytes(minimal_m4a_bytes())
    return path


def tag_m4a(path: Path, *, title="Song Title", artist="Artist Name", album="Some Album",
            lyrics: str | None = None) -> None:
    from mutagen.mp4 import MP4

    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    if title:
        audio.tags["\xa9nam"] = title
    if artist:
        audio.tags["\xa9ART"] = artist
    if album:
        audio.tags["\xa9alb"] = album
    if lyrics:
        audio.tags["\xa9lyr"] = lyrics
    audio.save()


SYNCED_LRC = """[00:01.00]First line
[00:02.50]Second line
[00:03.25]Third line
"""