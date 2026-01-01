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


def csoundDLL() -> tuple[ct.CDLL, str]:
    global _libcsound
    global _libcsoundpath

    if _libcsound is not None:
        return _libcsound, _libcsoundpath

    if BUILDING_DOCS:
        raise RuntimeError("Cannot access the dll while building docs")

    if sys.platform == 'linux':
        try:
            dll = ct.CDLL("libcsound64.so")
            _libcsound = dll
            _libcsoundpath = "libcsound64.so"
            return dll, "libcsound64.so"
        except OSError:
            libname = ctypes.util.find_library("csound64")
            if libname is None:
                raise ImportError("Did not find csound library in linux")
            return ct.CDLL(libname), libname
    libnames = csoundLibraryNames()
    for libname in libnames:
        path = ctypes.util.find_library(libname)
        if path:
            return ct.CDLL(path), path

    if sys.platform.startswith('win'):
        PATH = os.environ.get('PATH')
        raise ImportError(f"Csound library not found (searched for '{libnames}'. "
                          f"Make sure that csound is installed and the directory containing "
                          f"csound64.dll or csound.dll is in the path. PATH='{PATH}'")
    raise ImportError(f"Csound library not found (searched for '{libnames}') - Make sure that csound is installed")
