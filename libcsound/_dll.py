from __future__ import annotations
import ctypes as ct
import ctypes.util
import sys
import os
from .common import BUILDING_DOCS, logger
from typing import Sequence
from pathlib import Path

_libcsound = None
_libcsoundpath = ''
_opcodeDir = ''


def _expand_rpath_entry(entry: str, origin: str) -> list[str]:
    """
    Expand the dynamic-linker tokens in one RPATH/RUNPATH entry.

    ``$ORIGIN``/``${ORIGIN}`` -> the directory of the binary.
    ``$PLATFORM``/``${PLATFORM}`` -> ``platform.machine()``.
    ``$LIB``/``${LIB}`` -> loader/distro specific, so both ``lib`` and
    ``lib64`` are returned. Remaining ``$VAR`` tokens are expanded from the
    environment; entries with an unresolved token are dropped (returned list
    is empty) rather than resolved against the CWD.
    """
    import platform

    machine = platform.machine()
    entry = (entry.replace("${ORIGIN}", origin)
                  .replace("$ORIGIN", origin)
                  .replace("${PLATFORM}", machine)
                  .replace("$PLATFORM", machine))

    variants = [entry]
    if "$LIB" in entry or "${LIB}" in entry:
        variants = [entry.replace("${LIB}", d).replace("$LIB", d)
                    for d in ("lib", "lib64")]

    expanded = []
    for variant in variants:
        variant = os.path.expandvars(variant)
        if "$" not in variant:
            expanded.append(variant)
    return expanded


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

    try:
        result = subprocess.run(["readelf", "-d", bin], check=True, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise RuntimeError(f"Could not run 'readelf' to inspect {bin}: {e}") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"'readelf -d {bin}' failed with status {e.returncode}\n"
            f"stderr: {e.stderr.strip()}"
        ) from e

    rpaths: list[str] = []
    for line in result.stdout.splitlines():
        m = re.search(r"\((?:RPATH|RUNPATH)\).*Library (?:rpath|runpath): \[(.*)\]", line)
        if m:
            rpaths.extend(m.group(1).split(":"))

    if not rpaths:
        raise RuntimeError(f"{bin} has no RPATH/RUNPATH")

    origin = str(Path(bin).resolve().parent)

    for entry in rpaths:
        if not entry:
            continue
        for expanded in _expand_rpath_entry(entry, origin):
            candidate = os.path.join(os.path.abspath(expanded), libname)
            if os.path.isfile(candidate):
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

    try:
        result = subprocess.run(["otool", "-l", bin], check=True, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise RuntimeError(f"Could not run 'otool' to inspect {bin}: {e}") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"'otool -l {bin}' failed with status {e.returncode}\n"
            f"stderr: {e.stderr.strip()}"
        ) from e

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
        if not entry:
            continue
        entry = entry.replace("@executable_path", origin)
        entry = entry.replace("@loader_path", origin)
        entry = os.path.expandvars(entry)
        entry = os.path.abspath(entry)

        candidate = os.path.join(entry, libname)
        if os.path.isfile(candidate):
            return os.path.realpath(candidate)

    raise FileNotFoundError(f"{libname} not found in the RPATH of {bin}")


def _tryCDLL(libpath: str, errormsg: str = '',
             winmode: int | None = None) -> tuple[ct.CDLL | None, str]:
    """Try to load `libpath`, returning ``(cdll, '')`` on success or ``(None, message)``."""
    try:
        return ct.CDLL(libpath, winmode=winmode), ''
    except OSError as e:
        if not errormsg:
            errormsg = f"Could not initialize library {libpath}"
        message = f"{errormsg} (exception: {e})"
        logger.debug(message)
        return None, message


def _format_report(report: Sequence[str]) -> str:
    return "\n".join(f"  - {line}" for line in report)


def _findLibcsoundMacos() -> tuple[ct.CDLL, str] | str:
    report: list[str] = []

    def step1():
        report.append("Trying to load 'CsoundLib64' by name")
        dll, err = _tryCDLL("CsoundLib64")
        if dll is None:
            report.append(err)
            return None
        return dll, "CsoundLib64"

    def step2():
        libname = ctypes.util.find_library("CsoundLib64")
        if not libname:
            report.append("ctypes.util.find_library('CsoundLib64') returned None")
            return None
        report.append(f"find_library('CsoundLib64') returned '{libname}'")
        dll, err = _tryCDLL(libname, f"find_library returned '{libname}', "
                                     f"but the library could not be initialized")
        if dll is None:
            report.append(err)
            return None
        return dll, libname

    def step3():
        import shutil
        csoundbin = shutil.which("csound")
        if not csoundbin:
            report.append("'csound' executable not found in PATH")
            return None
        report.append(f"Found csound executable at '{csoundbin}'")
        try:
            libcsound_rpath = read_rpath_macos(csoundbin, "CsoundLib64")
        except (OSError, RuntimeError) as e:
            logger.debug("error while checking the rpath of csound (%s), error: %s", csoundbin, e)
            report.append(f"Could not resolve CsoundLib64 from the rpath of "
                          f"'{csoundbin}': {e}")
            return None
        report.append(f"Resolved CsoundLib64 to '{libcsound_rpath}' from the rpath of "
                      f"'{csoundbin}'")
        dll, err = _tryCDLL(libcsound_rpath, f"Found library at {libcsound_rpath}, "
                                             f"but failed to load")
        if dll is None:
            report.append(err)
            return None
        return dll, libcsound_rpath

    for func in [step1, step2, step3]:
        out = func()
        if out is not None:
            return out

    return _format_report(report)


def _findLibcsoundLinux() -> tuple[ct.CDLL, str] | str:
    """
    Returns a tuple (cdll, librarypath) or an error message
    """
    report: list[str] = []

    def step1():
        report.append("Trying to load 'libcsound64.so' by name")
        dll, err = _tryCDLL("libcsound64.so")
        if dll is None:
            report.append(err)
            return None
        return dll, "libcsound64.so"

    def step2():
        libname = ctypes.util.find_library("csound64")
        if not libname:
            report.append("ctypes.util.find_library('csound64') returned None")
            return None
        report.append(f"find_library('csound64') returned '{libname}'")
        # find_library does not always return an absolute path
        # so the only check is to just try to initialize the dll
        dll, err = _tryCDLL(libname, f"find_library returned '{libname}', "
                                     f"but the library could not be initialized")
        if dll is None:
            report.append(err)
            return None
        return dll, libname

    def step3():
        import shutil
        csoundbin = shutil.which("csound")
        if not csoundbin:
            report.append("'csound' executable not found in PATH")
            return None
        report.append(f"Found csound executable at '{csoundbin}'")
        try:
            libcsound_rpath = read_rpath(csoundbin, "libcsound64.so")
        except (OSError, RuntimeError) as e:
            logger.debug("error while checking the rpath of csound (%s), error: %s", csoundbin, e)
            report.append(f"Could not resolve libcsound64.so from the rpath of "
                          f"'{csoundbin}': {e}")
            return None
        report.append(f"Resolved libcsound64.so to '{libcsound_rpath}' from the rpath of "
                      f"'{csoundbin}'")

        dll, err = _tryCDLL(libcsound_rpath, f"Found library at {libcsound_rpath}, "
                                             f"but failed to load")
        if dll is None:
            report.append(err)
            return None
        return dll, libcsound_rpath

    def step4():
        # Explicit probe of well-known locations. This does not rely on the
        # loader cache (ldconfig), the csound binary being on PATH (step3) or
        # any env var, so it also finds a system-wide install whose ld cache
        # is stale (e.g. portable install to /usr/local without ldconfig
        # having been re-run) instead of triggering a needless reinstall.
        HOME = Path.home()
        for path in [HOME/".local/csound/libcsound64.so",
                     Path("/usr/local/lib/libcsound64.so"),
                     Path("/usr/lib/libcsound64.so")]:
            if not path.exists():
                report.append(f"'{path}' does not exist")
                continue
            pathstr = str(path.resolve())
            report.append(f"Found library at '{pathstr}'")
            dll, err = _tryCDLL(pathstr, f"Found library at {pathstr}, but failed to load")
            if dll is None:
                report.append(err)
                return None
            return dll, pathstr

    for func in [step1, step2, step3, step4]:
        out = func()
        if out is not None:
            return out

    return _format_report(report)


_DEFAULT_WINDOWS_PATHS: tuple[str, ...] = (r"C:\Program Files\Csound7\bin",
                                           r"C:\Program Files\Csound7",
                                           r"C:\Program Files\csound",
                                           r"C:\Program Files\csound\bin")


def _findLibWindows(libname: str,
                    possible_paths: Sequence[str] = _DEFAULT_WINDOWS_PATHS
                    ) -> tuple[ct.CDLL, str] | str:
    report: list[str] = []

    # first search the PATH
    dll, err = _tryCDLL(libname, winmode=0)
    if dll is not None:
        return dll, libname
    report.append(err)

    for path in possible_paths:
        dllabspath = os.path.join(path, libname)
        dll, err = _tryCDLL(dllabspath)
        if dll is not None:
            return dll, dllabspath
        report.append(err)

    return _format_report(report)


def findLibWindows(libname: str,
                    possible_paths: Sequence[str] = _DEFAULT_WINDOWS_PATHS
                    ) -> tuple[ct.CDLL | None, str]:
    """Locate a Windows DLL by name and in ``possible_paths``.

    Returns:
        a tuple (cdll, report), where cdll is the loaded library or None if
        it was not found, and report is the path used on success or the
        diagnostic search report on failure.
    """
    out = _findLibWindows(libname, possible_paths)
    if isinstance(out, str):
        return None, out
    return out


def _findLibcsoundWindows() -> tuple[ct.CDLL, str] | str:
    return _findLibWindows('csound64.dll')


def csoundDLL(install=True) -> tuple[ct.CDLL, str]:
    """
    Find and initialize the csound shared library.

    This function is called internally when ``libcsound`` is imported, in order
    to determine where to load libcsound from.

    Args:
        install: if True and csound is not found, it is installed. Set the env
            var ``LIBCSOUND_INSTALL`` to ``0`` or ``false`` to disable this
            behaviour.

    Returns:
        a tuple (cdll: ctypes.CDLL, path: str), where cdll is the actual
        CDLL object and path is the path used to load it

    Raises:
        ImportError: if csound cannot be made available. This covers a
            ``LIBCSOUNDPATH`` that does not resolve or fails to load, a failed
            automatic installation, and the case where no csound was found
            with installation disabled (``install=False`` or
            ``LIBCSOUND_INSTALL=0``). The original error is always chained
            (``__cause__``) and its detail is included in the message.

    Environment variables:
        ``LIBCSOUNDPATH``: if set, the absolute path to the csound shared
            library to load (no other search is performed). Otherwise,
            the library is searched in the system path (via
            ``ctypes.util.find_library``, the RPATH/RUNPATH of the ``csound``
            executable and standard locations).
        ``LIBCSOUND_INSTALL``: if set to ``0`` or ``false``, automatic
            installation of csound is disabled.
    """
    global _libcsound
    global _libcsoundpath

    if _libcsound is not None:
        return _libcsound, _libcsoundpath

    if BUILDING_DOCS:
        raise RuntimeError("Cannot access the dll while building docs")

    if install:
        LIBCSOUND_INSTALL = os.getenv('LIBCSOUND_INSTALL')
        if LIBCSOUND_INSTALL is not None and LIBCSOUND_INSTALL.lower() in ('0', 'false'):
            logger.debug("Installation disabled via LIBCSOUND_INSTALL")
            install = False

    if (libcsoundPathEnv := os.getenv("LIBCSOUNDPATH")):
        try:
            libcsoundPath = str(Path(libcsoundPathEnv).resolve())
        except (OSError, RuntimeError) as e:
            raise ImportError(f"Could not resolve LIBCSOUNDPATH '{libcsoundPathEnv}': {e}") from e

        if not os.path.isfile(libcsoundPath):
            raise ImportError(f"The env variable LIBCSOUNDPATH '{libcsoundPathEnv}' does not point to an existing file")

        try:
            _libcsound = ct.CDLL(libcsoundPath)
            _libcsoundpath = libcsoundPath
            return _libcsound, _libcsoundpath
        except OSError as e:
            raise ImportError(f"Could not init libcsound from LIBCSOUNDPATH "
                              f"'{libcsoundPathEnv}' (resolved to '{libcsoundPath}'): {e}") from e

    if sys.platform == 'linux':
        out = _findLibcsoundLinux()
    elif sys.platform == 'darwin':
        out = _findLibcsoundMacos()
    elif sys.platform.startswith('win'):
        out = _findLibcsoundWindows()
    else:
        raise ImportError(f"Unsupported platform: {sys.platform}")

    if isinstance(out, str):
        report_text = out
    else:
        _libcsound, _libcsoundpath = out
        _opcodeDir = ''
        return _libcsound, _libcsoundpath

    if install:
        from . import _install
        try:
            if sys.platform == 'linux':
                _install.install_csound_linux()
            elif sys.platform == 'darwin':
                _install.install_csound_macos()
            elif sys.platform.startswith('win'):
                _install.install_csound_windows()
        except ImportError:
            raise
        except (RuntimeError, OSError) as e:
            raise ImportError(f"Automatic csound installation failed: {e}") from e
        return csoundDLL(install=False)

    if sys.platform in ('linux', 'darwin'):
        raise ImportError("libcsound not found. It can be installed via:\n"
                          "    curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash\n"
                          f"Search report:\n{report_text}")
    elif sys.platform.startswith('win'):
        raise ImportError("Csound library not found. "
                          "Make sure that csound is installed and the directory containing "
                          f"csound64.dll is in the path. PATH='{os.environ.get('PATH')}'\n"
                          "Csound 7 can be installed automatically, but the installer needs "
                          "admin rights and an interactive (or elevated) session; "
                          "install it manually from a powershell console via:\n"
                          "    irm https://csound-plugins.github.io/getcsound.ps1 | iex\n"
                          f"Search report:\n{report_text}")
    else:
        raise ImportError(f"Did not find csound library in {sys.platform}")


def _default_user_plugins_dir(version: int | None = None) -> Path:
    """Return csound's default user plugin directory for this platform.

    This mirrors the ``CS_DEFAULT_USER_PLUGINDIR`` value that csound would
    normally compile in. The official macOS installer builds csound with
    ``CS_OPCODE_DIR`` set, which currently makes csound skip this default, so
    ``CS_USER_PLUGINDIR`` must be set explicitly for user plugins to be found
    (upstream fix pending).

    Args:
        version: the csound version as returned by ``csoundGetVersion()``
            (e.g. ``7000`` for csound 7.0). If not given, the version of the
            loaded csound library is queried.

    Returns:
        the default user plugin directory. It does not need to exist.
    """
    if version is None:
        if _libcsound is None:
            raise RuntimeError("libcsound is not loaded, cannot determine the csound version")
        version = int(_libcsound.csoundGetVersion())
    apiversion = f"{version // 1000}.0"
    if sys.platform == 'darwin':
        return Path.home() / "Library" / "csound" / apiversion / "plugins64"
    elif sys.platform == 'linux':
        return Path.home() / ".local" / "lib" / "csound" / apiversion / "plugins64"
    elif sys.platform.startswith('win'):
        localappdata = os.environ.get("LOCALAPPDATA")
        base = Path(localappdata) if localappdata else Path.home() / "AppData" / "Local"
        return base / "csound" / apiversion / "plugins64"
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


def _ensure_user_plugins_dir(version: int | None = None) -> None:
    """Set ``CS_USER_PLUGINDIR`` to csound's default if it is not already set.

    This is only done on macOS, where the official csound build does not search
    the default user plugin directory (see ``_default_user_plugins_dir``). On
    other platforms csound already searches it, and setting the variable
    explicitly would only add a warning when the directory does not exist.
    Existing values are never overridden.

    Temporary workaround until the fix is merged upstream in csound.
    """
    if sys.platform != 'darwin':
        return
    if os.environ.get("CS_USER_PLUGINDIR") is not None:
        return
    pluginsdir = _default_user_plugins_dir(version)
    logger.debug("Setting CS_USER_PLUGINDIR to '%s'", pluginsdir)
    os.environ["CS_USER_PLUGINDIR"] = str(pluginsdir)


