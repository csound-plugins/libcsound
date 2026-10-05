from __future__ import annotations
import ctypes as ct
from pathlib import Path
import sys
import os
from .common import logger
from typing import Sequence


def stdin_is_tty() -> bool:
    """Return True if stdin is an interactive terminal."""
    try:
        return bool(sys.stdin is not None and not sys.stdin.closed and sys.stdin.isatty())
    except Exception:
        return False


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


def install_csound_linux(quiet=True) -> None:
    """Install csound 7 on linux by running the bundled installer.

    This runs the bundled copy of the official installer at
    https://csound-plugins.github.io/getcsound.sh with bash. The installer
    downloads the portable csound 7 release from the
    ``csound-plugins/csound-plugins`` GitHub repository, verifies its SHA-256
    checksum and installs it. ``--no-risset`` is always passed so that risset is
    never installed.

    When running inside a terminal the installer is run interactively;
    otherwise it is run with ``--user -y`` so that csound is installed to
    ``~/.local/csound`` without prompting.

    After a successful installation, the environment variables ``LIBCSOUNDPATH``
    and ``OPCODE7DIR64`` point to the installed library and plugin
    directory, so that the current process can find csound without
    the need to open a new terminal.

    Raises:
        RuntimeError: if the bundled installer could not be found or failed, or
            if csound could not be located post installation.
    """
    import importlib.resources

    installer = importlib.resources.files(__package__).joinpath("data", "getcsound.sh")
    if not installer.is_file():
        raise RuntimeError(f"The bundled installer was not found: {installer}")

    # as_file() yields a real filesystem path, extracting to a temporary file
    # first when the package is loaded from an archive (e.g. a zip).
    linux_hint = ("csound can also be installed manually:\n"
                  "    curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash")
    with importlib.resources.as_file(installer) as script:
        options = ["bash", str(script), "--no-risset"]
        if not stdin_is_tty():
            # No terminal (e.g. on CI): install for the current user and answer
            # yes to any prompt, so that no password is needed and the installer
            # does not block waiting for input.
            options.extend(["--user", "-y"])
        if quiet:
            options.append("--quiet")
        run_installer(options, failure_hint=linux_hint)

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


def install_csound_macos(quiet=True) -> None:
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
    args = ["bash", str(installer)]
    if quiet:
        args.append("--quiet")
    with importlib.resources.as_file(installer) as script:
        run_installer(args, failure_hint=macos_hint)

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
