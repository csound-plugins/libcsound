from __future__ import annotations
import ctypes as ct
import ctypes.util
import sys
import os
from .common import BUILDING_DOCS


def csoundLibraryNames() -> list[str]:
    platform = sys.platform
    if platform.startswith('linux'):
        return ['csound64']
    elif platform.startswith('win'):
        return ['csound64', 'csound']
    elif platform.startswith('darwin'):
        return ['CsoundLib64']
    else:
        raise RuntimeError(f"Platform '{platform}' not supported")


_libcsound = None
_libcsoundpath = ''
_opcodeDir = ''



def read_rpath(bin: str, libname: str) -> str:
    """
    Return the absolute path to `libname` by resolving the executable' RPATH/RUNPATH.

    Args:
        bin: Path to an ELF executable.
        libname: Library filename, e.g. "libfoo.so" or "libfoo.so.1".

    Returns:
        Absolute path to the library.

    Raises:
        FileNotFoundError: If the library cannot be found in the executable's RPATH/RUNPATH.
        RuntimeError: If the executable is not ELF or has no RPATH/RUNPATH.
    """
    import subprocess
    import re
    from pathlib import Path

    result = subprocess.run(["readelf", "-d", bin], check=True, capture_output=True, text=True)

    rpath = None
    for line in result.stdout.splitlines():
        m = re.search(r"\((?:RPATH|RUNPATH)\).*Library (?:rpath|runpath): \[(.*)\]", line)
        if m:
            rpath = m.group(1)
            break

    if rpath is None:
        raise RuntimeError(f"{bin} has no RPATH/RUNPATH")

    origin = str(Path(bin).resolve().parent)

    for entry in rpath.split(":"):
        entry = entry.replace("$ORIGIN", origin)
        entry = os.path.expandvars(entry)
        entry = os.path.abspath(entry)

        candidate = os.path.join(entry, libname)
        if os.path.exists(candidate):
            return os.path.realpath(candidate)

    raise FileNotFoundError(f"{libname} not found in RPATH/RUNPATH of {bin}")


def read_rpath_macos(bin: str, libname: str) -> str:
    """
    Return the absolute path to `libname` by resolving the executable's RPATH entries.

    Args:
        bin: Path to a Mach-O executable.
        libname: Library filename, e.g. "CsoundLib64".

    Returns:
        Absolute path to the library.

    Raises:
        FileNotFoundError: If the library cannot be found in the executable's RPATH.
        RuntimeError: If the executable has no RPATH entries.
    """
    import subprocess
    import re
    from pathlib import Path

    result = subprocess.run(["otool", "-l", bin], check=True, capture_output=True, text=True)

    rpaths = []
    lines = result.stdout.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"\bcmd LC_RPATH\b", line):
            # The path is in the "path <rpath> (offset N)" line following the cmd line
            for followup in lines[i + 1:]:
                m = re.search(r"^\s*path (.*?) \(offset \d+\)\s*$", followup)
                if m:
                    rpaths.append(m.group(1))
                    break
                if re.search(r"^\s*cmd ", followup):
                    break

    if not rpaths:
        raise RuntimeError(f"{bin} has no LC_RPATH entries")

    origin = str(Path(bin).resolve().parent)

    for entry in rpaths:
        entry = entry.replace("@executable_path", origin)
        entry = entry.replace("@loader_path", origin)
        entry = os.path.expandvars(entry)
        entry = os.path.abspath(entry)

        candidate = os.path.join(entry, libname)
        if os.path.exists(candidate):
            return os.path.realpath(candidate)

    raise FileNotFoundError(f"{libname} not found in the RPATH of {bin}")


def _findLibcsoundMacos() -> tuple[ct.CDLL, str, str] | None:
    def step1():
        try:
            dll = ct.CDLL("CsoundLib64")
            return dll, "CsoundLib64", ''
        except Exception:
            return None

    def step2():
        if libname := ctypes.util.find_library("CsoundLib64"):
            return ct.CDLL(libname), libname, ''
        return None

    def step3():
        import shutil
        csoundbin = shutil.which("csound")
        if not csoundbin:
            return None
        libcsound_rpath = read_rpath_macos(csoundbin, "CsoundLib64")
        dll = ct.CDLL(libcsound_rpath)
        return dll, libcsound_rpath, ''

    for func in [step1, step2, step3]:
        out = func()
        if out is not None:
            dll, dllpath, opcodepath = out
            return dll, dllpath, opcodepath

    return None


def _findLibcsoundLinux() -> tuple[ct.CDLL, str, str] | None:
    def step1():
        try:
            dll = ct.CDLL("libcsound64.so")
            return dll, "libcsound64.so", ''
        except Exception as e:
            return None

    def step2():
        if libname := ctypes.util.find_library("csound64"):
            return ct.CDLL(libname), libname, ''
        return None

    def step3():
        import shutil
        csoundbin = shutil.which("csound")
        if not csoundbin:
            return None
        libcsound_rpath = read_rpath(csoundbin, "libcsound64.so")
        dll = ct.CDLL(libcsound_rpath)
        return dll, libcsound_rpath, ''

    for func in [step1, step2, step3]:
        out = func()
        if out is not None:
            dll, dllpath, opcodepath = out
            return dll, dllpath, opcodepath

    return None


def _findLibcsoundWindows() -> tuple[ct.CDLL, str, str] | None:
    libnames = ['csound64', 'csound']
    for libname in libnames:
        try:
            dll = ct.CDLL(libname)
            return dll, libname, ''
        except OSError:
            continue
    return None


def csoundDLL() -> tuple[ct.CDLL, str, str]:
    """
    Finds and initialized libcsound

    Returns:
        a tuple (cdll: ctypes.CDLL, path: str, opcodeDir: str), where cdll is the actual
        CDLL object, path is the path used to load it and opcodeDir is the default
        folder to use when loading plugins (will be empty if found a system
        installed csound). At the moment this is only used if no csound installation
        is used and the distributed portable csound is used instead

    This function is called internally to determine where to load
    libcsound from. The only way to customize it is to set the environment
    variable LIBCSOUNDPATH to the path of the library. If not set, the library
    will be searched in the system path. If not found, an ImportError will be raised

    If not explicitely set via LIBCSOUNDPATH, ctypes.util.find_library is used.
    """
    global _libcsound
    global _libcsoundpath
    global _opcodeDir

    if _libcsound is not None:
        return _libcsound, _libcsoundpath, _opcodeDir

    if BUILDING_DOCS:
        raise RuntimeError("Cannot access the dll while building docs")

    if (libcsoundPathEnv := os.getenv("LIBCSOUNDPATH")):
        if not os.path.exists(libcsoundPathEnv):
            raise OSError(f"The env variable LIBCSOUNDPATH '{libcsoundPathEnv}' does not point to an existing file")

        try:
            _libcsound = ct.CDLL(libcsoundPathEnv)
            _libcsoundpath = libcsoundPathEnv
            return _libcsound, _libcsoundpath, ''
        except OSError as e:
            raise OSError(f"Could not init libcsound from the path given as env variable LIBCSOUNDPATH: '{libcsoundPathEnv}'") from e

    if sys.platform == 'linux':
        out = _findLibcsoundLinux()
    elif sys.platform == 'darwin':
        out = _findLibcsoundMacos()
    elif sys.platform.startswith('win'):
        out = _findLibcsoundWindows()
        if out is None:
            raise ImportError("Csound library not found. "
                              "Make sure that csound is installed and the directory containing "
                              f"csound64.dll or csound.dll is in the path. PATH='{os.environ.get('PATH')}'")

    else:
        raise ImportError(f"Unsupported platform: {sys.platform}")

    if out is None:
        raise ImportError(f"Did not find csound library in {sys.platform}")
    dll, dllpath, opcodepath = out
    _libcsound = dll
    _libcsoundpath = dllpath
    _opcodeDir = opcodepath
    return _libcsound, _libcsoundpath, _opcodeDir

