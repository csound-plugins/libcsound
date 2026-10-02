from __future__ import annotations
import ctypes as ct
import hashlib
from pathlib import Path
from typing import Sequence

from .common import logger
from ._terminal import *


def print_download_info(url: str, target: str) -> None:
    """Print a compact, colored summary of an imminent download."""
    stream = sys.stdout
    asset = os.path.basename(target)
    target_dir = os.path.dirname(target) or "."

    title = paint(f"Downloading {asset}", "bold", "cyan", stream=stream)
    rule_char = "─" if supports_color(stream) and supports_unicode(stream) else "-"
    try:
        width = os.get_terminal_size().columns
    except Exception:
        width = 80
    rule = rule_char * max(0, width - 4)

    print()
    print(f"  {title}")
    print(f"  {rule}")
    for label, value, color in (
        ("source:", url, "blue"),
        ("target:", target_dir, "blue"),
    ):
        label_text = paint(f"{label:<8}", "bold", stream=stream)
        value_text = paint(value, color, stream=stream)
        print(f"  {label_text} {value_text}")
    print()


def hexdigest(path: str) -> str:
    hashsum = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hashsum.update(chunk)
    return hashsum.hexdigest()


def content_length(resp: Any) -> int | None:
    try:
        value = resp.headers.get("Content-Length")
        if value is not None:
            return int(value)
    except (KeyError, TypeError, ValueError):
        pass
    return None


def copy_with_progress(resp: Any, out: Any, asset: str) -> None:
    """Copy ``resp`` to ``out``, rendering a progress bar on stderr."""
    import time

    stream = sys.stderr
    tty = stream_is_tty(stream)
    total = content_length(resp)
    start = time.monotonic()
    done = 0
    last_render = 0.0
    last_render_done = -1
    interval = 0.1 if tty else 0.5
    while True:
        chunk = resp.read(65536)
        if not chunk:
            break
        out.write(chunk)
        done += len(chunk)
        now = time.monotonic()
        if now - last_render >= interval:
            render_progress_line(stream, asset, done, total, now - start, tty)
            last_render = now
            last_render_done = done
    if tty:
        clear_progress_line(stream)
        print_progress_done(stream, asset, done)
    elif done != last_render_done:
        render_progress_line(stream, asset, done, total,
                             time.monotonic() - start, tty)


def download(url: str, target: str, verbose: bool = False, retries: int = 3,
             progress: bool = False) -> None:
    """Download ``url`` and store it as ``target``.

    Args:
        url: Source URL.
        target: Destination file path.
        verbose: Print a human-readable summary of the download.
        retries: Number of attempts before giving up.
        progress: Show a progress bar while downloading (tty only).
    """
    import time
    import urllib.request
    import http.client
    import shutil
    asset = os.path.basename(target)
    if verbose:
        print_download_info(url, target)
    else:
        logger.info("Downloading URL: %s to %s...", url, asset)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "libcsound"})
            with urllib.request.urlopen(req, timeout=120) as resp, \
                    open(target, "wb") as out:
                if progress:
                    copy_with_progress(resp, out, asset)
                else:
                    shutil.copyfileobj(resp, out)
            return
        except (OSError, http.client.HTTPException, ValueError) as e:
            # OSError covers urllib.error.URLError/HTTPError, socket and file errors;
            # HTTPException covers BadStatusLine/IncompleteRead; ValueError covers
            # malformed/unknown URLs.
            last_error = e
            if progress and stream_is_tty(sys.stderr):
                try:
                    clear_progress_line(sys.stderr)
                except Exception:
                    pass
            if attempt < retries:
                wait = 2 * attempt
                logger.warning("Download of '%s' failed (attempt %d/%d): %s. "
                               "Retrying in %ds...",
                               asset, attempt, retries, e, wait)
                time.sleep(wait)
    raise RuntimeError(f"Failed to download '{asset}' from {url} "
                       f"(temporary file: {target}) after {retries} attempts\n"
                       f"{last_error}") from last_error


def run_installer(cmd: Sequence[str], failure_hint: str = "") -> None:
    """Run an installer command, streaming its output live while capturing it.

    When stdin is a terminal (interactive use) the child inherits stdio
    directly so prompts are visible. Capturing via a pipe would hide
    prompts printed without a trailing newline (e.g. ``read -p "…: "``,
    as used by the Linux bundled ``install.sh``, or ``sudo``'s password
    prompt): line-wise iteration only forwards complete lines, so the
    question would never be shown while the installer blocks waiting
    for the answer. Piping also makes the child's stdout fully buffered
    instead of line-buffered, delaying progress output.

    In non-interactive mode (no tty) stdout and stderr are merged,
    printed as they arrive and retained for diagnostics.

    Raises:
        RuntimeError: if the command exits with a non-zero status. The error
            includes the exit status, the full command, the tail of the
            captured output (non-interactive mode only) and ``failure_hint``.
    """
    import subprocess
    logger.info("Running bundled installer: %s", " ".join(str(c) for c in cmd))
    if stdin_is_tty():
        # Interactive: inherit stdio so `read -p`/sudo prompts are visible.
        returncode = subprocess.run(list(cmd)).returncode
        if returncode != 0:
            message = (f"Installer exited with status {returncode}\n"
                       f"Command: {' '.join(str(c) for c in cmd)}")
            if failure_hint:
                message += f"\n{failure_hint}"
            raise RuntimeError(message)
        return
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


def install_csound_linux() -> None:
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
        download(f"{base_url}/{asset}", zip_path, verbose=True,
                 progress=stdin_is_tty())
        download(checksum_url, checksum_path)

        # Verify SHA256 checksum before extracting
        try:
            with open(checksum_path, encoding="utf-8") as f:
                tokens = f.readline().split()
        except (OSError, UnicodeDecodeError) as e:
            raise RuntimeError(
                f"Could not read the checksum file downloaded from {checksum_url}: {e}"
            ) from e
        expected = tokens[0] if tokens else ""
        actual = hexdigest(zip_path)
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
            run_installer([installer])
        else:
            # no terminal: install for the current user, answering yes to all
            # questions so that the installer does not block on any prompt
            run_installer([installer, "--user", "-y"])

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


def install_csound_macos() -> None:
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
        run_installer(["bash", str(script)], failure_hint=macos_hint)

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


def install_csound_windows() -> None:
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
        if stdin_is_tty():
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
        run_installer(
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
