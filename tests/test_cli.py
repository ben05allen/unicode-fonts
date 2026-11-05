"""Tests for the command line interface."""

from __future__ import annotations

import pytest

from unicode_fonts.cli import main


def test_stdin_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr("sys.stdin", _Stdin("**hi** there\n"))
    assert main([]) == 0
    assert capsys.readouterr().out == "𝗵𝗶 there\n"


def test_reads_a_file(tmp_path, capsys: pytest.CaptureFixture) -> None:
    path = tmp_path / "post.md"
    path.write_text("*hello*", encoding="utf-8")
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == "𝘩𝘦𝘭𝘭𝘰"


def test_writes_an_output_file(tmp_path, capsys: pytest.CaptureFixture) -> None:
    source = tmp_path / "post.md"
    source.write_text("**x**", encoding="utf-8")
    target = tmp_path / "out.txt"
    assert main([str(source), "-o", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == "𝘅"
    assert capsys.readouterr().out == ""


def test_family_flag(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", _Stdin("**x**"))
    assert main(["--family", "serif"]) == 0
    assert capsys.readouterr().out == "𝐱"


def test_font_flag(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", _Stdin("Hi"))
    assert main(["--font", "fullwidth"]) == 0
    assert capsys.readouterr().out == "Ｈｉ"


def test_warnings_go_to_stderr(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", _Stdin("**`x`**"))
    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == "𝚡"
    assert "warning:" in captured.err


def test_unknown_family_exits_two(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", _Stdin("x"))
    assert main(["--family", "comic"]) == 2
    assert "unknown family" in capsys.readouterr().err


def test_missing_file_exits_one(capsys: pytest.CaptureFixture) -> None:
    assert main(["/nonexistent/post.md"]) == 1
    assert "error" in capsys.readouterr().err


def test_list_fonts(capsys: pytest.CaptureFixture) -> None:
    assert main(["--list-fonts"]) == 0
    out = capsys.readouterr().out
    assert "sansBoldItalic" in out
    assert "lossless" in out
    assert "circled" in out


def test_family_and_font_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["--family", "serif", "--font", "sans"])


class _Stdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text
