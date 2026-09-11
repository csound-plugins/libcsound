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
        HOME = Path.home()
        for path in [HOME/".local/csound/libcsound64.so"]:
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


_DEFAULT_WINDOWS_PATHS: tuple[str, ...] = (r"C:\Program Files\csound",
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
    out = _findLibWindows(libname, possible_paths)
    if isinstance(out, str):
        return None, ''
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
        OSError: if given an explicit path via ``LIBCSOUNDPATH`` but that
            failed to load
        ImportError: if no csound was found and install=False or
            ``LIBCSOUND_INSTALL=0``

    Environment variables:
        ``LIBCSOUNDPATH``: if set, the absolute path to the csound shared
            library to load. When set, no other search is performed. If not
            set, the library is searched in the system path (via
            ``ctypes.util.find_library``, the RPATH/RUNPATH of the ``csound``
            executable and standard installation locations).
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
            raise OSError(f"Could not resolve LIBCSOUNDPATH '{libcsoundPathEnv}': {e}") from e

        if not os.path.isfile(libcsoundPath):
            raise OSError(f"The env variable LIBCSOUNDPATH '{libcsoundPathEnv}' does not point to an existing file")

        try:
            _libcsound = ct.CDLL(libcsoundPath)
            _libcsoundpath = libcsoundPath
            return _libcsound, _libcsoundpath
        except OSError as e:
            raise OSError(f"Could not init libcsound from LIBCSOUNDPATH "
                          f"'{libcsoundPathEnv}' (resolved to '{libcsoundPath}')") from e

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
        if sys.platform == 'linux':
            _install_csound_linux()
            return csoundDLL(install=False)
        elif sys.platform == 'darwin':
            _install_csound_macos()
            return csoundDLL(install=False)

    if sys.platform in ('linux', 'darwin'):
        raise ImportError("libcsound not found. It can be installed via:\n"
                          "    curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash\n"
                          f"Search report:\n{report_text}")
    elif sys.platform.startswith('win'):
        raise ImportError("Csound library not found. "
                          "Make sure that csound is installed and the directory containing "
                          f"csound64.dll is in the path. PATH='{os.environ.get('PATH')}'\n"
                          "csound can be installed from https://github.com/csound/csound/releases\n"
                          f"Search report:\n{report_text}")
    else:
        raise ImportError(f"Did not find csound library in {sys.platform}")


def _hexdigest(path: str) -> str:
    hashsum = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hashsum.update(chunk)
    return hashsum.hexdigest()


def _download(url: str, target: str, verbose=False) -> None:
    import urllib.request
    import urllib.error
    import http.client
    import shutil
    if verbose:
        print("Downloading URL:", url, "to", target)
    else:
        logger.info("Downloading URL: %s to %s...", url, os.path.basename(target))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "libcsound"})
        with urllib.request.urlopen(req, timeout=120) as resp, \
                open(target, "wb") as out:
            shutil.copyfileobj(resp, out)
    except (OSError, http.client.HTTPException, ValueError) as e:
        # OSError covers urllib.error.URLError/HTTPError, socket and file errors;
        # HTTPException covers BadStatusLine/IncompleteRead; ValueError covers
        # malformed/unknown URLs.
        raise RuntimeError(f"Failed to download {target} from {url}\n{e}") from e


def _install_csound_linux() -> None:
    """Install the latest csound 7 portable release for linux.

    This mirrors the bootstrapping process of the one-line installer at
    https://csound-plugins.github.io/getcsound.sh

    It downloads the release asset ``csound7-linux-<arch>.zip`` from the
    ``csound-plugins/csound-plugins`` GitHub repository, verifies the
    SHA-256 checksum, extracts it and runs the
    bundled ``install.sh``. When running inside a tty the installer is run
    interactively; otherwise it is run with ``--user -y`` so that csound is
    installed to ``~/.local/csound``

    After a successful installation, the environment variables ``LIBCSOUNDPATH``
    and ``OPCODE7DIR64`` are set to point to the installed library and plugin
    directory, so that the current process can find csound immediately without
    the need to open a new terminal.

    Raises:
        RuntimeError: if the download or the checksum verification failed, if the
            bundled ``install.sh`` could not be found or failed, or if no csound
            installation could be located after running the installer.
    """
    import platform
    import stat
    import subprocess
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
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            raise RuntimeError(
                f"The downloaded archive '{asset}' is not a valid zip file: {e}"
            ) from e

        # Locate the bundled installer
        for root, _dirs, files in os.walk(extract_dir):
            if "install.sh" in files:
                installer = os.path.join(root, "install.sh")
                break
        else:
            raise RuntimeError(f"install.sh was not found inside {asset}")

        os.chmod(installer, os.stat(installer).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # Run the bundled installer
        if sys.stdin is not None and not sys.stdin.closed and sys.stdin.isatty():
            # running inside a terminal: run interactively
            logger.info("Running bundled installer: %s", installer)
            result = subprocess.run([installer])
        else:
            # no terminal: install for the current user, answering yes to all
            # questions so that the installer does not block on any prompt
            logger.info("Running bundled installer: %s --user -y", installer)
            result = subprocess.run([installer, "--user", "-y"])

        if result.returncode != 0:
            raise RuntimeError(f"The bundled installer exited with status {result.returncode}")

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
    installed with the system ``installer`` under sudo, so an interactive
    terminal session is required.

    This runs the bundled copy of the one-line installer used at
    https://csound-plugins.github.io/getcsound.sh, which resolves the latest
    successful workflow run, downloads its ``csound-7.*-macos*`` artifact
    through the anonymous nightly.link mirror and installs the extracted .pkg.

    After a successful installation the environment variables ``LIBCSOUNDPATH``
    and ``OPCODE7DIR64`` are set to point to the installed library and plugin
    directory, so that the current process can find csound immediately without
    the need to open a new terminal.

    Raises:
        RuntimeError: if the bundled installer could not be found or failed, or
            if no csound installation could be located after running it.
    """
    import importlib.resources
    import subprocess

    installer = importlib.resources.files(__package__).joinpath("data", "getcsound.sh")
    if not installer.is_file():
        raise RuntimeError(f"The bundled installer was not found: {installer}")

    # as_file() yields a real filesystem path, extracting to a temporary file
    # first when the package is loaded from an archive (e.g. a zip).
    with importlib.resources.as_file(installer) as script:
        logger.info("Running bundled installer: %s", script)
        result = subprocess.run(["bash", str(script)])
    if result.returncode != 0:
        raise RuntimeError(
            f"The bundled installer exited with status {result.returncode}\n"
            "The csound macOS .pkg is installed with sudo and needs an interactive "
            "terminal session.\n"
            "Alternatively, csound can be installed manually:\n"
            "    curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash"
        )

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