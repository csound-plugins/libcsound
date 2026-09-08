#!/usr/bin/env python3
"""CI test: importing libcsound on a mac without csound auto-installs it.

This script must be run on a machine with NO csound installed. Importing
libcsound is then expected to trigger the automatic macOS installer (which
needs an interactive terminal, so run it under ``script`` in CI).

After the import succeeds it creates a Csound instance and renders a short
offline render to ``out.wav`` to make sure the freshly installed library and
its opcodes actually work.
"""
import ctypes
import ctypes.util
import os
import shutil
import sys
import wave

OUTFILE = "out.wav"


def check_no_csound() -> None:
    problems = []
    if os.path.exists("/Applications/Csound"):
        problems.append("/Applications/Csound already exists")
    if shutil.which("csound"):
        problems.append(f"csound binary already on the PATH: {shutil.which('csound')}")
    if ctypes.util.find_library("CsoundLib64"):
        problems.append(f"CsoundLib64 is already findable: {ctypes.util.find_library('CsoundLib64')}")
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
    print(f"  opcode dir:     {libcsound.opcodeDir}")

    # Sanity checks that the auto-installer really ran and left a working install
    if not os.path.exists("/Applications/Csound/csound"):
        print("FAILED: /Applications/Csound/csound was not created by the installer",
              file=sys.stderr)
        sys.exit(2)
    if not os.environ.get("LIBCSOUNDPATH"):
        print("FAILED: LIBCSOUNDPATH was not set by the installer", file=sys.stderr)
        sys.exit(2)

    libcsound.csoundInitialize(signalHandler=False)
    cs = libcsound.Csound()
    ret = cs.setOption(f"-o{OUTFILE}")
    if ret != 0:
        print(f"FAILED: setOption returned {ret}", file=sys.stderr)
        sys.exit(2)

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
        pass

    if not os.path.exists(OUTFILE):
        print(f"FAILED: no output file {OUTFILE} was written", file=sys.stderr)
        sys.exit(2)
    with wave.open(OUTFILE, "rb") as wf:
        nframes = wf.getnframes()
        print(f"Rendered {OUTFILE}: channels={wf.getnchannels()} "
              f"samplerate={wf.getframerate()} frames={nframes}")
    if nframes == 0:
        print(f"FAILED: {OUTFILE} is empty", file=sys.stderr)
        sys.exit(2)
    print("OK")


if __name__ == "__main__":
    main()
