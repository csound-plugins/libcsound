from __future__ import annotations
import ctypes as ct
import ctypes.util
import sys
import hashlib
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
        try:
            if sys.platform == 'linux':
                _install_csound_linux()
            elif sys.platform == 'darwin':
                _install_csound_macos()
            elif sys.platform.startswith('win'):
                _install_csound_windows()
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


def _hexdigest(path: str) -> str:
    hashsum = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hashsum.update(chunk)
    return hashsum.hexdigest()


def _download(url: str, target: str, verbose=False, retries: int = 3) -> None:
    import time
    import urllib.request
    import urllib.error
    import http.client
    import shutil
    asset = os.path.basename(target)
    if verbose:
        print("Downloading URL:", url, "to", target)
    else:
        logger.info("Downloading URL: %s to %s...", url, asset)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "libcsound"})
            with urllib.request.urlopen(req, timeout=120) as resp, \
                    open(target, "wb") as out:
                shutil.copyfileobj(resp, out)
            return
        except (OSError, http.client.HTTPException, ValueError) as e:
            # OSError covers urllib.error.URLError/HTTPError, socket and file errors;
            # HTTPException covers BadStatusLine/IncompleteRead; ValueError covers
            # malformed/unknown URLs.
            last_error = e
            if attempt < retries:
                wait = 2 * attempt
                logger.warning("Download of '%s' failed (attempt %d/%d): %s. "
                               "Retrying in %ds...",
                               asset, attempt, retries, e, wait)
                time.sleep(wait)
    raise RuntimeError(f"Failed to download '{asset}' from {url} "
                       f"(temporary file: {target}) after {retries} attempts\n"
                       f"{last_error}") from last_error


def _run_installer(cmd: Sequence[str], failure_hint: str = "") -> None:
    """Run an installer command, streaming its output live while capturing it.

    The child inherits stdin so interactive prompts keep working; stdout and
    stderr are merged, printed as they arrive (so progress stays visible) and
    retained for diagnostics.

    Raises:
        RuntimeError: if the command exits with a non-zero status. The error
            includes the exit status, the full command, the tail of the
            captured output and ``failure_hint``.
    """
    import subprocess
    logger.info("Running bundled installer: %s", " ".join(str(c) for c in cmd))
    proc = subprocess.Popen(list(cmd),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        print(line, end="")
    returncode = proc.wait()
    if returncode != 0:
        tail = "".join(lines[-50:]).rstrip() or "<no output captured>"
        message = (f"Installer exited with status {returncode}\n"
                   f"Command: {' '.join(str(c) for c in cmd)}\n"
                   f"--- installer output (last {min(len(lines), 50)} lines) ---\n"
                   f"{tail}")
        if failure_hint:
            message += f"\n{failure_hint}"
        raise RuntimeError(message)


def _install_csound_linux() -> None:
    """Install the latest csound 7 portable release for linux.

    This mirrors the process of the one-line installer at
    https://csound-plugins.github.io/getcsound.sh

    It downloads the release asset ``csound7-linux-<arch>.zip`` from the
    ``csound-plugins/csound-plugins`` GitHub repository, verifies the
    SHA-256 checksum, extracts it and runs the
    bundled ``install.sh``. When running inside a tty the installer is run
    interactively; otherwise it is run with ``--user -y`` so that csound is
    installed to ``~/.local/csound``

    After a successful installation, the environment variables ``LIBCSOUNDPATH``
    and ``OPCODE7DIR64`` point to the installed library and plugin
    directory, so that the current process can find csound without
    the need to open a new terminal.

    Raises:
        RuntimeError: if the download or the checksum verification failed, if the
            bundled ``install.sh`` could not be found or failed, or if csound
            could not be located post installation.
    """
    import platform
    import stat
    import tempfile
    import zipfile

    repo = "csound-plugins/csound-plugins"
    tag = os.getenv("CSOUND7_TAG", "latest")

    # Detect the CPU architecture
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        raise RuntimeError(f"Unsupported architecture: {machine}. "
                           "Supported architectures: x86_64, aarch64.")

    asset = os.getenv("CSOUND7_ASSET", f"csound7-linux-{arch}.zip")
    checksum_asset = f"{asset}.sha256"
    if tag == 'latest':
        # Notice how github changes the format to address the latest release
        base_url = f"https://github.com/{repo}/releases/latest/download"
    else:
        # Here this is a real tag, it must exist
        base_url = f"https://github.com/{repo}/releases/download/{tag}"
    
    checksum_url = f"{base_url}/{checksum_asset}"

    with tempfile.TemporaryDirectory(prefix="libcsound-install-") as tmpdir:
        zip_path = os.path.join(tmpdir, asset)
        checksum_path = f"{zip_path}.sha256"
        _download(f"{base_url}/{asset}", zip_path, verbose=True)
        _download(checksum_url, checksum_path)

        # Verify SHA256 checksum before extracting
        try:
            with open(checksum_path, encoding="utf-8") as f:
                tokens = f.readline().split()
        except (OSError, UnicodeDecodeError) as e:
            raise RuntimeError(
                f"Could not read the checksum file downloaded from {checksum_url}: {e}"
            ) from e
        expected = tokens[0] if tokens else ""
        actual = _hexdigest(zip_path)
        if not expected or expected != actual:
            raise RuntimeError(
                f"SHA-256 checksum verification failed for {asset}\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}\n"
                f"The downloaded file may be corrupted or have been modified.\n"
                f"Checksum URL: {checksum_url}")
        logger.info("Checksum verified.")

        extract_dir = os.path.join(tmpdir, "extracted")
        try:
            zip_size = os.path.getsize(zip_path)
        except OSError:
            zip_size = -1
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            raise RuntimeError(
                f"The downloaded archive '{asset}' is not a valid zip file "
                f"(size: {zip_size} bytes, temporary file: {zip_path}): {e}"
            ) from e
        except zipfile.LargeZipFile as e:
            raise RuntimeError(
                f"The downloaded archive '{asset}' requires 64-bit zip support "
                f"(size: {zip_size} bytes, temporary file: {zip_path}): {e}"
            ) from e
        except NotImplementedError as e:
            # Unsupported compression method.
            raise RuntimeError(
                f"The downloaded archive '{asset}' uses an unsupported "
                f"compression method (temporary file: {zip_path}): {e}"
            ) from e
        except OSError as e:
            raise RuntimeError(
                f"Could not extract the downloaded archive '{asset}' "
                f"(temporary file: {zip_path}, extract dir: {extract_dir}): {e}"
            ) from e

        # Locate the bundled installer
        for root, _dirs, files in os.walk(extract_dir):
            if "install.sh" in files:
                installer = os.path.join(root, "install.sh")
                break
        else:
            raise RuntimeError(f"install.sh was not found inside {asset}")

        try:
            os.chmod(installer, os.stat(installer).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError as e:
            raise RuntimeError(
                f"Could not make the bundled installer executable: '{installer}' "
                f"(from archive '{asset}'): {e}"
            ) from e

        # Run the bundled installer (output streams live and is captured, so a
        # failure carries the installer log; see _run_installer)
        if sys.stdin is not None and not sys.stdin.closed and sys.stdin.isatty():
            # running inside a terminal: run interactively
            _run_installer([installer])
        else:
            # no terminal: install for the current user, answering yes to all
            # questions so that the installer does not block on any prompt
            _run_installer([installer, "--user", "-y"])

    # Make the freshly installed csound available to the current process
    home = Path.home()
    userpath = home/".local/csound/libcsound64.so"
    systempath = Path("/usr/local/lib/libcsound64.so")
    if userpath.exists():
        pluginspath = home/".local/lib/csound/7.0/plugins64"
        if not pluginspath.is_dir():
            raise RuntimeError(f"csound 7 installation failed: plugin directory "
                               f"'{pluginspath}' was not found")
        os.environ["LIBCSOUNDPATH"] = str(userpath.resolve())
        os.environ['OPCODE7DIR64'] = str(pluginspath.resolve())
    elif systempath.exists():
        pluginspath = Path("/usr/local/lib/csound/plugins64-7.0")
        if not pluginspath.is_dir():
            raise RuntimeError(f"csound 7 installation failed: plugin directory "
                               f"'{pluginspath}' was not found")
        os.environ["LIBCSOUNDPATH"] = str(systempath.resolve())
        os.environ['OPCODE7DIR64'] = str(pluginspath.resolve())
    else:
        raise RuntimeError("csound 7 installation failed: "
                           "libcsound64.so was not found in any of the standard locations")


def _install_csound_macos() -> None:
    """Install the latest csound 7 .pkg for macOS by running the bundled installer.

    The official Csound 7 macOS package is produced by the "csound_builds"
    workflow of the csound/csound repository on the "develop" branch and is
    installed with the system ``installer`` under sudo. An interactive terminal
    session is used when available (so sudo can prompt for the password). 
    When there is no terminal (e.g. on CI) the install still succeeds if sudo is
    configured to run password-less.

    This runs the bundled copy of the one-line installer used at
    https://csound-plugins.github.io/getcsound.sh, which resolves the latest
    successful workflow run, downloads its ``csound-7.*-macos*`` artifact
    through the anonymous nightly.link mirror and installs the extracted .pkg.

    After installation the environment variables ``LIBCSOUNDPATH``
    and ``OPCODE7DIR64`` point to the installed library and plugin
    directory, so that the current process can find csound immediately without
    the need to open a new session.

    Raises:
        RuntimeError: if the bundled installer could not be found or failed, or
            if no csound installation could be located after running it.
    """
    import importlib.resources

    installer = importlib.resources.files(__package__).joinpath("data", "getcsound.sh")
    if not installer.is_file():
        raise RuntimeError(f"The bundled installer was not found: {installer}")

    # as_file() yields a real filesystem path, extracting to a temporary file
    # first when the package is loaded from an archive (e.g. a zip).
    macos_hint = ("The csound macOS .pkg is installed with sudo and needs an interactive "
                  "terminal (or passwordless sudo).\n"
                  "Alternatively, csound can be installed manually:\n"
                  "    curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash")
    with importlib.resources.as_file(installer) as script:
        _run_installer(["bash", str(script)], failure_hint=macos_hint)

    # Make the freshly installed csound available to the current process
    csound_dir = Path("/Applications/Csound")
    libpath = csound_dir / "CsoundLib64.framework" / "CsoundLib64"
    pluginspath = csound_dir / "CsoundLib64.framework" / "Resources" / "Opcodes64"
    if libpath.exists():
        os.environ["LIBCSOUNDPATH"] = str(libpath.resolve())
        if pluginspath.exists() and pluginspath.is_dir():
            os.environ['OPCODE7DIR64'] = str(pluginspath.resolve())
        logger.info("Csound installed successfully to %s", csound_dir)
        return

    raise RuntimeError("csound 7 installation failed: "
                       "CsoundLib64 was not found in /Applications/Csound")


def _windows_is_admin() -> bool:
    """Return True if the current Windows session is elevated.

    Returns False when the check cannot confirm elevation (including when the
    check itself is unavailable), so callers fail with a helpful message
    rather than assuming admin rights.
    """
    try:
        return bool(ct.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug("Could not determine Windows elevation status: %s", e)
        return False


def _stdin_is_tty() -> bool:
    """Return True if stdin is an interactive terminal."""
    try:
        return bool(sys.stdin is not None and not sys.stdin.closed and sys.stdin.isatty())
    except Exception:
        return False


def _install_csound_windows() -> None:
    """Install the latest csound 7 for Windows by running the bundled installer.

    This runs the bundled copy of the official installer at
    https://csound-plugins.github.io/getcsound.ps1 with Windows PowerShell. The
    installer resolves the latest successful ``csound_builds`` workflow run of
    the ``csound/csound`` repository on the ``develop`` branch, downloads the
    Windows x86_64 Inno Setup package and installs it silently to
    ``%ProgramFiles%\\Csound7``. Windows on ARM64 is not supported yet.

    The package is installed machine-wide and needs admin rights: when the current 
    session is not elevated the installer triggers a UAC prompt, so an interactive 
    (or pre-elevated) session is required. On CI runners the session is usually 
    already elevated.

    After a successful installation the env vars ``LIBCSOUNDPATH``
    and ``OPCODE7DIR64`` are set to point to the installed library and plugin
    folder, so that the current process can find csound immediately without
    the need to open a new terminal.

    Raises:
        RuntimeError: if PowerShell or the bundled installer could not be found,
            if the installer failed, or if no csound installation could be
            located after running it.
    """
    import importlib.resources
    import platform
    import shutil

    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        raise RuntimeError(
            f"Windows on ARM64 (detected: '{platform.machine()}') is not supported "
            "by the automatic csound installer, which provides an x86_64 package only.\n"
            "Install csound manually (e.g. from https://github.com/csound/csound/releases) "
            "and point LIBCSOUNDPATH at the installed csound64.dll."
        )

    if not _windows_is_admin():
        if _stdin_is_tty():
            logger.warning("The Csound Windows installer installs machine-wide and needs "
                           "admin rights; the installer will request elevation (UAC prompt).")
        else:
            raise RuntimeError(
                "The Csound Windows installer installs machine-wide and needs admin "
                "rights, but the current session is not elevated and there is no "
                "interactive terminal to show the UAC prompt.\n"
                "Run from an interactive (or already elevated) PowerShell session, or "
                "install csound manually:\n"
                "    irm https://csound-plugins.github.io/getcsound.ps1 | iex"
            )

    installer = importlib.resources.files(__package__).joinpath("data", "getcsound.ps1")
    if not installer.is_file():
        raise RuntimeError(f"The bundled installer was not found: {installer}")

    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise RuntimeError(
            "PowerShell was not found. It is needed to install csound on Windows.\n"
            "Alternatively, csound can be installed manually:\n"
            "    irm https://csound-plugins.github.io/getcsound.ps1 | iex"
        )

    # as_file() yields a real filesystem path, extracting to a temporary file
    # first when the package is loaded from an archive (e.g. a zip).
    windows_hint = ("The Csound Windows installer installs machine-wide and needs "
                    "admin rights: run it from an interactive (or elevated) "
                    "PowerShell session.\n"
                    "Alternatively, csound can be installed manually:\n"
                    "    irm https://csound-plugins.github.io/getcsound.ps1 | iex")
    with importlib.resources.as_file(installer) as script:
        _run_installer(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            failure_hint=windows_hint
        )

    # Make the freshly installed csound available to the current process
    programfiles = (os.environ.get("ProgramW6432")
                    or os.environ.get("ProgramFiles")
                    or r"C:\Program Files")
    csound_dir = Path(programfiles) / "Csound7"
    bindir = csound_dir / "bin"
    libpath = bindir / "csound64.dll"
    pluginspath = csound_dir / "plugins64"
    if libpath.is_file():
        os.environ["LIBCSOUNDPATH"] = str(libpath.resolve())
        # The machine-wide PATH set by the installer is not visible to this
        # process yet, so add the bin directory here to let csound's dependent
        # DLLs (e.g. libsndfile) be resolved when the library is loaded.
        os.environ["PATH"] = str(bindir.resolve()) + os.pathsep + os.environ.get("PATH", "")
        if pluginspath.is_dir():
            os.environ['OPCODE7DIR64'] = str(pluginspath.resolve())
        logger.info("Csound installed successfully to %s", csound_dir)
        return

    raise RuntimeError("csound 7 installation failed: csound64.dll was not found in "
                       f"'{bindir}'")
