#!/usr/bin/env python3
"""CI test: importing libcsound on Windows without csound auto-installs it.

This script must be run on a machine with NO csound installed. Importing
libcsound is then expected to trigger the automatic Windows installer, which
runs the bundled getcsound.ps1. The Inno Setup package installs machine-wide
to %ProgramFiles%\\Csound7 and needs Administrator rights; GitHub-hosted
Windows runners are already elevated, so no UAC prompt appears.

After the import succeeds it creates a Csound instance and renders a short
offline render to ``out.wav`` to make sure the freshly installed library and
its opcodes actually work.
"""
import ctypes.util
import os
import shutil
import sys
import wave
from pathlib import Path

OUTFILE = "out.wav"


def program_files() -> Path:
    return Path(os.environ.get("ProgramW6432")
                or os.environ.get("ProgramFiles")
                or r"C:\Program Files")


def check_no_csound() -> None:
    problems = []
    csound_dir = program_files() / "Csound7"
    if csound_dir.exists():
        problems.append(f"{csound_dir} already exists")
    if shutil.which("csound"):
        problems.append(f"csound binary already on the PATH: {shutil.which('csound')}")
    if ctypes.util.find_library("csound64"):
        problems.append(f"csound64 is already findable: {ctypes.util.find_library('csound64')}")
    if problems:
        print("Test premise broken: csound seems to already be installed:\n  "
              + "\n  ".join(problems), file=sys.stderr)
        sys.exit(3)


def main() -> None:
    check_no_csound()

    # This import is expected to install csound automatically
    print("Importing libcsound (this should auto-install csound 7)...", flush=True)
    try:
        import libcsound
    except Exception as e:
        print(f"FAILED: importing libcsound raised: {e!r}", file=sys.stderr)
        raise

    print("libcsound imported OK", flush=True)
    print(f"  csound version: {libcsound.VERSION}")
    print(f"  libcsound path: {libcsound.libcsoundPath}")

    # Sanity checks that the auto-installer really ran and left a working install
    csoundbin = program_files() / "Csound7" / "bin" / "csound.exe"
    if not csoundbin.exists():
        print(f"FAILED: {csoundbin} was not created by the installer", file=sys.stderr)
        sys.exit(2)
    if not os.environ.get("LIBCSOUNDPATH"):
        print("FAILED: LIBCSOUNDPATH was not set by the installer", file=sys.stderr)
        sys.exit(2)

    libcsound.csoundInitialize(signalHandler=False)
    cs = libcsound.Csound()
    cs.setOption(f"-o{OUTFILE}")
    cs.setOption("--wave")

    ret = cs.compileOrc(r"""
sr = 44100
ksmps = 64
nchnls = 1
0dbfs = 1
instr 1
    a1 oscili 0.5, 440
    out a1
endin
""")
    if ret != 0:
        print(f"FAILED: compileOrc returned {ret}", file=sys.stderr)
        sys.exit(2)

    cs.start()
    cs.scoreEvent('i', [1, 0, 1])
    cs.scoreEvent('e', [0, 1.1])

    while cs.performKsmps() == libcsound.CSOUND_SUCCESS:
        print(".", end="", flush=True)

    # Finalize the output file: the WAV header is only written and the file
    # closed when the csound instance is destroyed.
    cs.destroy()

    if not os.path.exists(OUTFILE):
        print(f"\nFAILED: no output file {OUTFILE} was written", file=sys.stderr)
        sys.exit(2)
    with wave.open(OUTFILE, "rb") as wf:
        nframes = wf.getnframes()
        print(f"\nRendered {OUTFILE}: channels={wf.getnchannels()} "
              f"samplerate={wf.getframerate()} frames={nframes}")
    if nframes == 0:
        print(f"FAILED: {OUTFILE} is empty", file=sys.stderr)
        sys.exit(2)
    print("OK")


if __name__ == "__main__":
    main()
