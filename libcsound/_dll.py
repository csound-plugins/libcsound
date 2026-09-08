from __future__ import annotations
import ctypes as ct
import ctypes.util
import sys
import hashlib
import os
from .common import BUILDING_DOCS, logger
from typing import Sequence


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
        if (libname := ctypes.util.find_library("csound64")):
            if os.path.exists(libname):
                return ct.CDLL(libname), libname, ''
            else:
                logger.error(f"find_library returned '{libname}', but the file does not exist, "
                             f"probably ldconfig needs to be called to update the ")
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


def findLibWindows(libname: str,
                   possible_paths: Sequence[str] = (r"C:\Program Files\csound",
                                                    r"C:\Program Files\csound\bin")
                   ) -> tuple[ct.CDLL | None, str]:
    # first search the PATH
    try:
        dll = ct.CDLL(libname, winmode=0)   # <-- allow to search the path
        return dll, libname
    except OSError:
        pass

    if possible_paths:
        for path in possible_paths:
            if os.path.exists(path):
                dllabspath = os.path.join(path, libname)
                if os.path.exists(dllabspath):
                    try:
                        dll = ct.CDLL(dllabspath)
                        return dll, dllabspath
                    except OSError:
                        continue
    return None, ''


def _findLibcsoundWindows() -> tuple[ct.CDLL, str, str] | None:
    cdll, libpath = findLibWindows('csound64.dll')
    return (cdll, libpath, '') if cdll is not None else None


def csoundDLL(install=True) -> tuple[ct.CDLL, str, str]:
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
    else:
        raise ImportError(f"Unsupported platform: {sys.platform}")

    if out is not None:
        dll, dllpath, opcodepath = out
        _libcsound = dll
        _libcsoundpath = dllpath
        _opcodeDir = opcodepath
        return _libcsound, _libcsoundpath, _opcodeDir

    if install:
        if sys.platform == 'linux':
            _install_csound_linux()
            return csoundDLL(install=False)
        elif sys.platform == 'darwin':
            _install_csound_macos()
            return csoundDLL(install=False)

    if sys.platform in ('linux', 'darwin'):
        raise ImportError("libcsound not found. It can be installed via:\n"
                          "    curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash")
    elif sys.platform.startswith('win'):
        raise ImportError("Csound library not found. "
                          "Make sure that csound is installed and the directory containing "
                          f"csound64.dll is in the path. PATH='{os.environ.get('PATH')}'\n"
                          "csound can be installed from https://github.com/csound/csound/releases")
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
    except (urllib.error.URLError, OSError) as e:
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

    Returns:
        True if the installation was successful.

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
    from pathlib import Path

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
        with open(checksum_path) as f:
            tokens = f.readline().split()
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
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)

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
        os.environ["LIBCSOUNDPATH"] = str(userpath.resolve())
        pluginspath = home/".local/lib/csound/7.0/plugins64"
        assert pluginspath.exists() and pluginspath.is_dir()
        os.environ['OPCODE7DIR64'] = str(pluginspath.resolve())
    elif systempath.exists():
        pluginspath = Path("/usr/local/lib/csound/plugins64-7.0")
        assert pluginspath.exists() and pluginspath.is_dir()
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
    from pathlib import Path

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