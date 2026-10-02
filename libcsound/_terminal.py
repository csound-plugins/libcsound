from __future__ import annotations
import os
import sys
from typing import Any, TextIO


_ANSI_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ASCII_SPINNER = "|/-\\"


def stream_is_tty(stream: Any) -> bool:
    try:
        return bool(stream is not None and not stream.closed and stream.isatty())
    except Exception:
        return False


def supports_color(stream: Any) -> bool:
    if not stream_is_tty(stream):
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    return os.environ.get("TERM") != "dumb"


def supports_unicode(stream: Any) -> bool:
    encoding = str(getattr(stream, "encoding", "") or "").lower()
    return "utf" in encoding


def paint(text: str, *colors: str, stream: Any = sys.stdout) -> str:
    if not supports_color(stream):
        return text
    codes = "".join(_ANSI_COLORS[c] for c in colors)
    return f"{codes}{text}{_ANSI_COLORS['reset']}"


def format_bytes(num: int | float) -> str:
    num = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if num < 1024.0 or unit == "PiB":
            if unit == "B":
                return f"{int(num)} B"
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PiB"


def stdin_is_tty() -> bool:
    """Return True if stdin is an interactive terminal."""
    try:
        return bool(sys.stdin is not None and not sys.stdin.closed and sys.stdin.isatty())
    except Exception:
        return False


def render_progress_line(stream: TextIO, asset: str, done: int,
                         total: int | None, elapsed: float, tty: bool) -> None:
    use_unicode = supports_unicode(stream)
    if total:
        frac = min(1.0, done / total)
        pct = f"{frac * 100:3.0f}%"
        bar_width = 20
        filled = int(bar_width * frac)
        if supports_color(stream):
            fill_char = "█" if use_unicode else "#"
            empty_char = "░" if use_unicode else "-"
            bar = f"{_ANSI_COLORS['green']}{fill_char * filled}{_ANSI_COLORS['reset']}{empty_char * (bar_width - filled)}"
        else:
            bar = f"{'#' * filled}{'-' * (bar_width - filled)}"
        speed = done / elapsed if elapsed > 0 else 0.0
        line = (f"  {asset}  {pct} [{bar}]  "
                f"{format_bytes(done)}/{format_bytes(total)}  "
                f"{format_bytes(speed)}/s")
    else:
        spinner_frames = _SPINNER if use_unicode else _ASCII_SPINNER
        spinner = spinner_frames[int(elapsed * 10) % len(spinner_frames)]
        line = f"  {asset}  {spinner}  {format_bytes(done)}"
    if tty:
        try:
            width = os.get_terminal_size().columns
            line = ("\r" + line).ljust(width)
        except Exception:
            line = "\r" + line
        end = ""
    else:
        end = "\n"
    print(line, end=end, file=stream, flush=True)


def clear_progress_line(stream: TextIO) -> None:
    try:
        width = os.get_terminal_size().columns
    except Exception:
        width = 80
    print("\r" + " " * width + "\r", end="", file=stream, flush=True)


def print_progress_done(stream: TextIO, asset: str, done: int) -> None:
    """Print the final summary line after a successful download."""
    print(f"  {asset}  {format_bytes(done)}", file=stream)
