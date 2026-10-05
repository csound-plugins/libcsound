#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════
# Csound 7 installer
#
# On Linux this script downloads the portable Csound 7 release from
# csound-plugins/csound-plugins, verifies its SHA-256 checksum, extracts it
# and installs it directly (system-wide or user-local). The portable
# installer logic is integrated here; the archive's install.sh is not run.
#
# On macOS it downloads the official .pkg built by the csound_builds workflow
# of csound/csound (branch develop) and installs it with the system installer.
# ═══════════════════════════════════════════════════════════════════

# ─── Output helpers ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { [ "$QUIET" = true ] || printf "${BLUE}ℹ %s${NC}\n" "$*"; }
ok()      { [ "$QUIET" = true ] || printf "${GREEN}✔ %s${NC}\n" "$*"; }
warn()    { printf "${YELLOW}⚠ %s${NC}\n" "$*"; }
error()   { printf "${RED}✖ %s${NC}\n" "$*" >&2; }
header()  { [ "$QUIET" = true ] || printf "${CYAN}%s${NC}\n" "$*"; }
result()  { printf "${GREEN}✔ %s${NC}\n" "$*"; }

debug() {
    if ((VERBOSE)); then
        printf '[debug] %s\n' "$*"
    fi
}

# ─── Command-line options ──────────────────────────────────────────
VERBOSE=0
SHOW_HELP=0
USE_RELEASE=0

INSTALL_MODE_ARG=""
AUTO_YES=false
QUIET=false
RISSET=""    # "" = ask interactively / install non-interactively, "no" = skip
USER_CSOUND_PATH="$HOME/.local/csound"
USER_PLUGINS_DIR="$HOME/.local/lib/csound/7.0/plugins64"

usage() {
    cat <<'EOF'
Usage: getcsound.sh [OPTIONS]

Options:
  --help       Show this help without downloading anything.
  --release    Install the installer published with the latest GitHub release
               instead of the latest successful csound_builds workflow run
               (macOS; Linux always installs from a release).
  --verbose    Show download URLs, debug information, and checksums (Linux).
  --no-risset  Do not install risset and do not ask about it
  -y           Non-interactive: do not prompt; install csound (defaults to a
               system installation) and risset. Pass --no-risset to skip risset.
  --quiet      Only output essential information (warnings, errors, and a
               final completion message)

Linux installation options (ignored on other platforms):
  --user       Install for the current user only (~/.local)
  --system     Install system-wide (/usr/local, requires sudo)
EOF
}

while (($#)); do
    case "$1" in
        --help)
            SHOW_HELP=1
            ;;
        --release)
            USE_RELEASE=1
            ;;
        --verbose)
            VERBOSE=1
            ;;
        --user)
            INSTALL_MODE_ARG="user"
            ;;
        --system)
            INSTALL_MODE_ARG="system"
            ;;
        --no-risset)
            RISSET="no"
            ;;
        -y)
            AUTO_YES=true
            ;;
        --quiet)
            QUIET=true
            ;;
        --)
            shift
            continue
            ;;
        *)
            error "Unknown option: $1"
            usage >&2
            exit 1
            ;;
    esac
    shift
done

if ((SHOW_HELP)); then
    usage
    exit 0
fi

# --verbose takes precedence if both --quiet and --verbose are given
if ((VERBOSE)); then
    QUIET=false
fi

# ─── Bootstrap helpers ─────────────────────────────────────────────
verbose() {
    if ((VERBOSE)); then
        printf '%s\n' "$*"
    fi
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        error "'$1' is required but not installed."
        error "Please install it and try again."
        exit 1
    fi
}

# api_error_hint
#
# Explain a failed GitHub API query. Anonymous requests from shared runner IPs
# are commonly rejected with HTTP 403 because the rate limit was exceeded.
api_error_hint() {
    error "This usually means the GitHub API rate limit was exceeded."
    error "Set CSOUND7_GH_TOKEN, GH_TOKEN or GITHUB_TOKEN to authenticate,"
    error "or install the GitHub CLI and run 'gh auth login'."
}

# resolve_github_token
#
# Return a GitHub token to authenticate API requests. The token is taken from
# the environment (CSOUND7_GH_TOKEN, GH_TOKEN or GITHUB_TOKEN). As a fallback,
# when none of those is set and the GitHub CLI is available, `gh auth token` is
# used. Prints an empty string when no token can be found.
resolve_github_token() {
    local token="${CSOUND7_GH_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"
    if [[ -z "$token" ]] && command -v gh >/dev/null 2>&1; then
        token=$(gh auth token 2>/dev/null || true)
    fi
    printf '%s' "$token"
}

# github_api_get URL OUTFILE
#
# GitHub's API rate-limits anonymous requests (shared runner IPs are often
# blocked with HTTP 403). When GH_TOKEN is set it is used to authenticate;
# otherwise the request stays anonymous. If an authenticated request fails
# (e.g. an expired token) the request is retried anonymously.
github_api_get() {
    local url=$1 out=$2
    if [[ -n "${GH_TOKEN:-}" ]]; then
        if curl -fsSL -H "Authorization: Bearer ${GH_TOKEN}" -o "$out" "$url"; then
            return 0
        fi
        verbose "Request with token failed; retrying anonymously..."
    fi
    curl -fsSL -o "$out" "$url"
}

# download_file URL OUTFILE
#
# Download a large archive, showing a progress bar when stderr is a
# terminal and staying silent otherwise (so CI logs stay clean).
# Transient failures (dropped connections, brief nightly.link throttling) are
# retried a few times with a linearly increasing delay.
# Note: curl's -s (silent) suppresses --progress-bar, so the two
# must not be combined.
download_file() {
    local url=$1 out=$2
    local attempt delay
    for ((attempt = 1; attempt <= 3; attempt++)); do
        if [[ -t 2 ]]; then
            if curl -fL --progress-bar -o "$out" "$url"; then
                return 0
            fi
        else
            if curl -fsSL -o "$out" "$url"; then
                return 0
            fi
        fi
        if ((attempt >= 3)); then
            return 1
        fi
        delay=$((attempt * 2))
        verbose "Download failed (attempt ${attempt}/3); retrying in ${delay}s..."
        sleep "$delay"
    done
}

# ─── Portable installer helpers ────────────────────────────────────
ask_yes_no() {
    local prompt="$1" response
    if [ "$AUTO_YES" = true ]; then
        return 0
    fi
    while true; do
        read -rp "$prompt [y/N]: " response
        case "$response" in
            [Yy]* ) return 0 ;;
            [Nn]* | "" ) return 1 ;;
            * ) echo "Please answer yes or no." ;;
        esac
    done
}

ask_choice() {
    local prompt="$1"
    local response
    while true; do
        read -rp "$prompt [(u)ser / (s)ystem]: " response
        case "$response" in
            [Uu]* | user | USER ) echo "user"; return ;;
            [Ss]* | system | SYSTEM ) echo "system"; return ;;
            * ) echo "Please enter 'user' (or 'u') / 'system' (or 's')." ;;
        esac
    done
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ─── risset installation ───────────────────────────────────────────
install_risset() {
    # risset is a python package, installed via uv
    if ! command_exists uv; then
        info "uv is not installed, installing it first..."
        if ! command_exists curl; then
            error "curl is required to install uv but is not installed."
            error "Please install curl, or install uv manually: https://docs.astral.sh/uv/"
            return 1
        fi
        curl -LsSf https://astral.sh/uv/install.sh | sh
        # Make uv available in this session (the installer puts it in ~/.local/bin)
        export PATH="$HOME/.local/bin:$PATH"
        if ! command_exists uv; then
            error "uv installation failed."
            return 1
        fi
        ok "uv installed: $(uv --version)"
    fi
    info "Installing risset..."
    uv tool install risset
    ok "risset installed. Run 'risset --help' to get started."
    info "To uninstall risset later: uv tool uninstall risset"
}

# maybe_install_risset
#
# Offer to install risset unless it is already available, unless --no-risset was
# given, or unless the user declines the interactive prompt. In non-interactive
# mode (with -y, or when no terminal is attached) risset is installed without
# asking. Shared by the Linux and macOS install paths.
maybe_install_risset() {
    [ "$QUIET" = true ] || echo ""
    if command_exists risset; then
        info "risset is already available at $(command -v risset); skipping installation."
    elif [ "$RISSET" = "no" ]; then
        debug "Skipping risset installation (--no-risset)."
    elif [ "$AUTO_YES" = true ] || [ ! -t 0 ]; then
        install_risset || warn "risset installation failed. You can retry later with: uv tool install risset"
    elif ask_yes_no "Install risset (csound package manager)?"; then
        install_risset || warn "risset installation failed. You can retry later with: uv tool install risset"
    fi
}

# ─── Detect shell ──────────────────────────────────────────────────
detect_shell() {
    if [ -n "${SHELL:-}" ]; then
        basename "$SHELL"
    else
        echo "bash"
    fi
}

detect_shell_rc() {
    local shell_name="$1"
    case "$shell_name" in
        bash)
            if [ -f "$HOME/.bashrc" ]; then echo "$HOME/.bashrc"
            elif [ -f "$HOME/.bash_profile" ]; then echo "$HOME/.bash_profile"
            else echo "$HOME/.bashrc"; fi
            ;;
        zsh)
            echo "$HOME/.zshrc"
            ;;
        fish)
            echo "$HOME/.config/fish/config.fish"
            ;;
        *)
            if [ -f "$HOME/.bashrc" ]; then echo "$HOME/.bashrc"
            elif [ -f "$HOME/.zshrc" ]; then echo "$HOME/.zshrc"
            else echo "$HOME/.bashrc"; fi
            ;;
    esac
}

# ─── Shell-specific config generators ──────────────────────────────
path_config_for_shell() {
    local dir="$1" shell_name="$2"
    case "$shell_name" in
        fish)
            # If we don't use --global then the change remains across sessions
            # making it rather difficult to remove (it needs to be removed from fish_variables)
            echo "fish_add_path --global $dir"
            ;;
        *)
            echo "export PATH=\"$dir:\$PATH\""
            ;;
    esac
}

# Remove existing PATH entries for our directory from shell config
remove_path_from_config() {
    local rc_file="$1" dir="$2" shell_name="$3"
    if [ ! -f "$rc_file" ]; then return; fi
    case "$shell_name" in
        fish)
            sed -i.bak "/fish_add_path.*$(echo "$dir" | sed 's/[\/&]/\\&/g')/d" "$rc_file" && rm -f "$rc_file.bak"
            ;;
        *)
            sed -i.bak "/$(echo "$dir" | sed 's/[\/&]/\\&/g')/d" "$rc_file" && rm -f "$rc_file.bak"
            ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════
# Portable Linux installation
#
# SOURCE_DIR must contain csound, libcsound64.so.7.0 and plugins/
# (as extracted from the portable release archive).
# ═══════════════════════════════════════════════════════════════════
run_portable_installer() {
    local source_dir="$1"

    CSOUND_BIN="$source_dir/csound"
    LIB_NAME="libcsound64.so.7.0"
    LIB_FILE="$source_dir/$LIB_NAME"
    SOURCE_PLUGINS_DIR="$source_dir/plugins"

    if [ ! -f "$CSOUND_BIN" ]; then
        error "csound executable not found in $source_dir"
        exit 1
    fi

    if [ ! -f "$LIB_FILE" ]; then
        error "$LIB_NAME not found in $source_dir"
        exit 1
    fi

    debug "Source directory: $source_dir"

    if [ -n "$INSTALL_MODE_ARG" ]; then
        INSTALL_MODE="$INSTALL_MODE_ARG"
    fi

    # ─── Choose installation mode ─────────────────────────────────
    header ""
    header "═══════════════════════════════════════════════════════"
    header "  Csound 7 Portable Installer"
    header "═══════════════════════════════════════════════════════"
    if [ "$QUIET" = false ]; then
        echo ""
        echo "  Install for:"
        echo "    (u)ser   - Current user only (~/.local)"
        echo "    (s)ystem - All users (/usr/local, requires sudo)"
        echo ""
    fi

    if [ -z "${INSTALL_MODE:-}" ] && [ "$AUTO_YES" = true ]; then
        INSTALL_MODE="system"
    elif [ -z "${INSTALL_MODE:-}" ]; then
        INSTALL_MODE=$(ask_choice "Installation mode")
    fi

    # ─── Check for an existing Csound installation ────────────────
    if command_exists csound; then
        EXISTING_CSOUND=$(command -v csound)
        USER_CSOUND="$USER_CSOUND_PATH/csound"

        warn "csound is already available at $EXISTING_CSOUND"

        if [ "$INSTALL_MODE" = "user" ] && [ "$EXISTING_CSOUND" = "$USER_CSOUND" ]; then
            info "The existing csound is the user-local installation target."
        elif ! ask_yes_no "A new installation might conflict with the existing csound. Proceed?"; then
            info "Installation cancelled."
            exit 0
        fi
    fi

    # ─── System-wide installation ─────────────────────────────────
    if [ "$INSTALL_MODE" = "system" ]; then

        header ""
        header "System-wide installation selected"
        header ""

        PREFIX="/usr/local"
        BIN_DIR="$PREFIX/bin"
        LIB_DIR="$PREFIX/lib"
        PLUGIN_DIR="$PREFIX/lib/csound/plugins64-7.0"
        INSTALLED_LOCATION="$PREFIX"

        # Check for sudo
        if [ "$EUID" -ne 0 ]; then
            if command_exists sudo; then
                SUDO=(sudo)
            else
                error "System installation requires root privileges. Please run as root or install sudo."
                exit 1
            fi
        else
            SUDO=()
        fi

        # Check for conflicts
        CONFLICT=false
        if [ -f "$BIN_DIR/csound" ]; then
            warn "csound already exists at $BIN_DIR/csound"
            CONFLICT=true
        fi
        if [ -f "$LIB_DIR/$LIB_NAME" ]; then
            warn "$LIB_NAME already exists at $LIB_DIR/$LIB_NAME"
            CONFLICT=true
        fi
        if [ -d "$PLUGIN_DIR" ] && [ -n "$(ls -A "$PLUGIN_DIR" 2>/dev/null)" ]; then
            warn "Plugin directory already exists and is not empty: $PLUGIN_DIR"
            CONFLICT=true
        fi

        if [ "$CONFLICT" = true ]; then
            if ! ask_yes_no "One or more target files/directories already exist. Overwrite?"; then
                info "Installation cancelled."
                exit 0
            fi
        fi

        # Check for patchelf
        if ! command_exists patchelf; then
            error "patchelf is required for system installation but not installed."
            error "Please install it (e.g., sudo apt install patchelf)"
            exit 1
        fi

        # Create a temp copy to patch. It lives inside TMP_DIR so the existing
        # cleanup trap removes it together with the extracted archive.
        PATCH_DIR="${TMP_DIR}/patch"
        mkdir -p "$PATCH_DIR"

        info "Patching rpath for system layout..."
        cp "$CSOUND_BIN" "$PATCH_DIR/csound"
        # Change rpath from $ORIGIN to $ORIGIN/../lib (bin is sibling to lib)
        # shellcheck disable=SC2016
        patchelf --set-rpath '$ORIGIN/../lib' "$PATCH_DIR/csound"
        ok "rpath patched: \$ORIGIN/../lib"

        # Install
        info "Installing to $PREFIX..."

        "${SUDO[@]}" mkdir -p "$BIN_DIR"
        "${SUDO[@]}" mkdir -p "$LIB_DIR"
        "${SUDO[@]}" mkdir -p "$PLUGIN_DIR"

        "${SUDO[@]}" cp "$PATCH_DIR/csound" "$BIN_DIR/csound"
        "${SUDO[@]}" chmod +x "$BIN_DIR/csound"

        "${SUDO[@]}" cp "$LIB_FILE" "$LIB_DIR/$LIB_NAME"
        "${SUDO[@]}" ln -sf "$LIB_DIR/$LIB_NAME" "$LIB_DIR/libcsound64.so"

        if [ -d "$SOURCE_PLUGINS_DIR" ]; then
            "${SUDO[@]}" cp -a "$SOURCE_PLUGINS_DIR/." "$PLUGIN_DIR/"
        fi

        # Update ldconfig
        info "Updating library cache..."
        "${SUDO[@]}" ldconfig

        ok "System-wide installation complete!"
        if [ "$QUIET" = false ]; then
            echo ""
            echo "  csound          → $BIN_DIR/csound"
            echo "  libcsound64.so  → $LIB_DIR/libcsound64.so"
            echo "  plugins         → $PLUGIN_DIR"
            echo ""
            echo "  To uninstall, run:"
            echo "    sudo rm -f $BIN_DIR/csound"
            echo "    sudo rm -f $LIB_DIR/$LIB_NAME $LIB_DIR/libcsound64.so"
            echo "    sudo rm -rf $PLUGIN_DIR"
            echo "    sudo ldconfig"
        fi

    # ─── User-local installation ──────────────────────────────────
    else

        header ""
        header "User-local installation selected"
        header ""

        INSTALL_DIR="$USER_CSOUND_PATH"
        PLUGIN_DIR="$USER_PLUGINS_DIR"
        INSTALLED_LOCATION="$INSTALL_DIR"

        # Check for conflicts
        CONFLICT=false
        if [ -d "$INSTALL_DIR" ]; then
            warn "Directory already exists: $INSTALL_DIR"
            CONFLICT=true
        fi
        if [ -d "$PLUGIN_DIR" ]; then
            warn "Directory already exists: $PLUGIN_DIR"
            CONFLICT=true
        fi

        if [ "$CONFLICT" = true ]; then
            if ! ask_yes_no "One or more target directories already exist. Overwrite?"; then
                info "Installation cancelled."
                exit 0
            fi
        fi

        # Install
        info "Installing to $INSTALL_DIR..."

        rm -rf "$INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"

        cp "$CSOUND_BIN" "$INSTALL_DIR/csound"
        chmod +x "$INSTALL_DIR/csound"

        cp "$LIB_FILE" "$INSTALL_DIR/$LIB_NAME"
        ln -sf "$INSTALL_DIR/$LIB_NAME" "$INSTALL_DIR/libcsound64.so"

        rm -rf "$PLUGIN_DIR"
        mkdir -p "$PLUGIN_DIR"

        if [ -d "$SOURCE_PLUGINS_DIR" ]; then
            cp -a "$SOURCE_PLUGINS_DIR/." "$PLUGIN_DIR/"
        fi

        ok "Files installed."

        # Update PATH in shell config
        SHELL_NAME=$(detect_shell)
        SHELL_RC=$(detect_shell_rc "$SHELL_NAME")

        info "Detected shell: $SHELL_NAME"
        info "Shell config: $SHELL_RC"

        # Ensure fish config directory exists
        if [ "$SHELL_NAME" = "fish" ]; then
            mkdir -p "$(dirname "$SHELL_RC")"
        fi

        PATH_LINE=$(path_config_for_shell "$INSTALL_DIR" "$SHELL_NAME")

        # Remove old entries first to avoid duplicates
        remove_path_from_config "$SHELL_RC" "$INSTALL_DIR" "$SHELL_NAME"

        {
            echo ""
            echo "# Added by Csound 7 installer"
            echo "$PATH_LINE"
        } >> "$SHELL_RC"

        ok "PATH updated in $SHELL_RC"

        # Summary
        if [ "$QUIET" = false ]; then
            echo ""
            echo "═══════════════════════════════════════════════════════"
            echo "  User-local installation complete!"
            echo "═══════════════════════════════════════════════════════"
            echo ""
            echo "  csound          → $INSTALL_DIR/csound"
            echo "  libcsound64.so  → $INSTALL_DIR/libcsound64.so"
            echo "  plugins         → $PLUGIN_DIR"
            echo ""
            echo "  Shell config:    $SHELL_RC"
            echo ""
            echo "  To use Csound immediately, open a new terminal session or run:"
            echo "    source $SHELL_RC"
            echo ""
            echo "═══════════════════════════════════════════════════════"
            echo ""
            echo "  To uninstall, run:"
            echo "    rm -rf $INSTALL_DIR"
            echo "    rm -rf $PLUGIN_DIR"
            echo "  And remove the '# Added by Csound 7 installer' block from $SHELL_RC"
        fi

    fi

    # ─── Optional: install risset ─────────────────────────────────
    maybe_install_risset

    # ─── Final status ─────────────────────────────────────────────
    if [ "$QUIET" = true ]; then
        result "Csound 7 installed to $INSTALLED_LOCATION"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Csound 7 Portable Linux - One-line installer
#
# SAFER USAGE (recommended):
#   curl -fsSL -o install-csound7-linux.sh \
#       https://csound-plugins.github.io/getcsound.sh
#   # Read the script, then run it:
#   bash ./getcsound.sh
#
# One-line usage (convenient, but inspects nothing before execution):
#   curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash

install_linux() {
    require_command curl
    require_command unzip
    require_command mktemp

    if ((USE_RELEASE)); then
        printf 'Note: --release has no effect on Linux; the portable release is always used.\n' >&2
    fi

    # sha256sum is preferred; macOS's shasum is not used here because Linux is required,
    # but keep a fallback so the script is portable in case that restriction changes.
    if command -v sha256sum >/dev/null 2>&1; then
        SHA256_CMD="sha256sum"
    elif command -v shasum >/dev/null 2>&1; then
        SHA256_CMD="shasum -a 256"
    else
        error "A SHA-256 checksum tool is required (sha256sum or shasum)."
        exit 1
    fi

    # Detect the CPU architecture.
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64|amd64)
            ARCH_SUFFIX="x86_64"
            ;;
        aarch64|arm64)
            ARCH_SUFFIX="aarch64"
            ;;
        *)
            echo "Unsupported architecture: $ARCH. Supported architectures: x86_64, aarch64."
            exit 1
            ;;
    esac

    REPO="${CSOUND7_REPO:-csound-plugins/csound-plugins}"
    TAG="${CSOUND7_TAG:-latest}"
    ASSET="${CSOUND7_ASSET:-csound7-linux-${ARCH_SUFFIX}.zip}"
    CHECKSUM_ASSET="${ASSET}.sha256"
    if [ "$TAG" = "latest" ]; then
    	DOWNLOAD_URL="https://github.com/${REPO}/releases/latest/download/${ASSET}"
        CHECKSUM_URL="https://github.com/${REPO}/releases/latest/download/${CHECKSUM_ASSET}"
    else
	    DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${TAG}/${ASSET}"
	    CHECKSUM_URL="https://github.com/${REPO}/releases/download/${TAG}/${CHECKSUM_ASSET}"
	fi

    # ─── Prepare temporary directory ────────────────────────────────
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT

    ZIP_FILE="${TMP_DIR}/${ASSET}"
    EXTRACT_DIR="${TMP_DIR}/extracted"
    mkdir -p "$EXTRACT_DIR"

    # ─── Download ───────────────────────────────────────────────────
    echo "Downloading ${DOWNLOAD_URL}"
    if ! download_file "$DOWNLOAD_URL" "$ZIP_FILE"; then
        error "Failed to download ${ASSET}"
        error "URL: ${DOWNLOAD_URL}"
        exit 1
    fi
    ok "Download complete: ${ZIP_FILE}"

    # ─── Verify checksum ────────────────────────────────────────────
    echo "Downloading checksum file: ${CHECKSUM_URL}"
    if curl -fsSL -o "${ZIP_FILE}.sha256" "$CHECKSUM_URL"; then
        info "Verifying SHA-256 checksum..."
        EXPECTED_HASH=$(awk 'NR==1 {print $1}' "${ZIP_FILE}.sha256")
        ACTUAL_HASH=$($SHA256_CMD "$ZIP_FILE" | awk '{print $1}')
        verbose "Expected SHA-256: ${EXPECTED_HASH:-<missing>}"
        verbose "Actual SHA-256:   ${ACTUAL_HASH:-<missing>}"
        if [[ -z "$EXPECTED_HASH" ]] || [[ "$EXPECTED_HASH" != "$ACTUAL_HASH" ]]; then
            error "SHA-256 checksum verification failed for ${ASSET}"
            error "Expected: ${EXPECTED_HASH:-<missing>}"
            error "Actual:   ${ACTUAL_HASH:-<missing>}"
            error "The downloaded file may be corrupted or have been modified."
            error "Checksum URL: ${CHECKSUM_URL}"
            exit 1
        fi
        ok "Checksum verified."
    else
        error "Failed to download checksum file: ${CHECKSUM_ASSET}"
        error "URL: ${CHECKSUM_URL}"
        error "Refusing to install an unverified archive."
        exit 1
    fi

    # ─── Extract ────────────────────────────────────────────────────
    info "Extracting ${ASSET}..."
    if ! unzip -q "$ZIP_FILE" -d "$EXTRACT_DIR"; then
        error "Failed to extract ${ASSET}"
        exit 1
    fi

    # ─── Give the interactive installer a TTY when needed ───────────
    # With -y no prompts are shown, so a terminal is not required (this keeps
    # non-interactive CI usage working). Otherwise reconnect stdin to the
    # terminal, e.g. when executed via curl | bash.
    if [[ ! -t 0 ]] && [ "$AUTO_YES" != true ]; then
        if (exec 3<>/dev/tty) 2>/dev/null; then
            exec < /dev/tty
        else
            error "No terminal available (/dev/tty)."
            error "This installer is interactive; please run it from a terminal, or pass -y."
            exit 1
        fi
    fi

    # ─── Install ────────────────────────────────────────────────────
    run_portable_installer "$EXTRACT_DIR"
}

# ═══════════════════════════════════════════════════════════════════
# Csound 7 macOS - .pkg installer
#
# The official Csound 7 macOS installer is produced by the "csound_builds"
# workflow of the csound/csound repository on the "develop" branch (Csound 7).
# It is uploaded as a workflow artifact named csound-7.*-macos* containing a
# universal .pkg, which we install with macOS's "installer" command.
#
# GitHub Actions artifacts cannot be downloaded anonymously, so the archive is
# fetched through the nightly.link mirror. Installation runs under sudo: an
# interactive terminal is used when available so that sudo can prompt for the
# password, otherwise the install proceeds if sudo is passwordless.
#
# Trust model:
#   - The artifact is downloaded over HTTPS and installed unmodified.
#   - There is no published checksum for workflow artifacts, so integrity
#     cannot be verified independently. The mirror (nightly.link) serves the
#     artifact bytes as produced by the workflow run.
# ═══════════════════════════════════════════════════════════════════
install_macos() {
    require_command curl
    require_command mktemp

    # The install step runs under sudo. When a terminal is available, sudo can
    # prompt for a password as usual. Without a terminal (e.g. on CI) the
    # install can still proceed when sudo runs without a password (passwordless
    # sudo, as on GitHub-hosted runners); otherwise refuse to run.
    SUDO=(sudo)
    SUDO_NONINTERACTIVE=0
    if [[ ! -t 0 ]] && ! (exec 3<>/dev/tty) 2>/dev/null; then
        if sudo -n true 2>/dev/null; then
            SUDO=(sudo -n)
            SUDO_NONINTERACTIVE=1
        else
            error "The macOS installer needs sudo and must be run from a terminal."
            error "Please run it from an interactive Terminal session."
            exit 1
        fi
    fi

    # With -y no prompts are shown, so a terminal is not required. Otherwise
    # reconnect stdin to the terminal (e.g. when executed via curl | bash) so
    # that the risset prompt can read from it.
    if [[ ! -t 0 ]] && [ "$AUTO_YES" != true ] && [ "$RISSET" != "no" ]; then
        if (exec 3<>/dev/tty) 2>/dev/null; then
            exec < /dev/tty
        fi
    fi

    if [[ -n "$INSTALL_MODE_ARG" ]]; then
        printf 'Warning: --user/--system are ignored on macOS.\n' >&2
    fi

    REPO="${CSOUND7_REPO:-csound/csound}"
    WORKFLOW="${CSOUND7_WORKFLOW:-csound_builds.yml}"
    BRANCH="${CSOUND7_MACOS_BRANCH:-develop}"
    ARTIFACT_GLOB="${CSOUND7_MACOS_ASSET:-csound-7.*-macos*}"

    # Use a token for the GitHub API queries when one is available (from the
    # environment, e.g. GITHUB_TOKEN on CI, or as a fallback from `gh auth
    # token`); anonymous otherwise.
    GH_TOKEN=$(resolve_github_token)

    # ─── Prepare temporary directory ────────────────────────────────
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT

    ZIP_FILE="${TMP_DIR}/macos.zip"

    if ((USE_RELEASE)); then
        # ─── Resolve the latest release ─────────────────────────────
        RELEASE_TAG="${CSOUND7_RELEASE_TAG:-latest}"
        if [[ "$RELEASE_TAG" == "latest" ]]; then
            RELEASE_URL="https://api.github.com/repos/${REPO}/releases/latest"
            info "Looking for the latest release of ${REPO}..."
        else
            RELEASE_URL="https://api.github.com/repos/${REPO}/releases/tags/${RELEASE_TAG}"
            info "Looking for release ${RELEASE_TAG} of ${REPO}..."
        fi
        verbose "Release URL: ${RELEASE_URL}"
        if ! github_api_get "$RELEASE_URL" "$TMP_DIR/release.json"; then
            error "Failed to query the release."
            error "URL: ${RELEASE_URL}"
            api_error_hint
            exit 1
        fi
        RELEASE_TAG=$(awk -F'"' '/"tag_name":/ { print $4; exit }' "$TMP_DIR/release.json")
        if [[ -z "$RELEASE_TAG" ]]; then
            error "Could not determine the release tag."
            error "URL: ${RELEASE_URL}"
            exit 1
        fi
        info "Using release: ${RELEASE_TAG}"
        ARTIFACT_NAME="csound-macos-${RELEASE_TAG}.zip"
        DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${ARTIFACT_NAME}"
    else
        # ─── Resolve the latest successful workflow run ─────────────
        RUN_ID="${CSOUND7_MACOS_RUN_ID:-}"
        if [[ -z "$RUN_ID" ]]; then
            info "Looking for the latest successful ${WORKFLOW} run on branch '${BRANCH}' of ${REPO}..."
            RUNS_URL="https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?branch=${BRANCH}&event=push&per_page=30"
            verbose "Runs URL: ${RUNS_URL}"
            if ! github_api_get "$RUNS_URL" "$TMP_DIR/runs.json"; then
                error "Failed to query workflow runs."
                error "URL: ${RUNS_URL}"
                api_error_hint
                exit 1
            fi
            RUN_ID=$(awk '
                /^      "id":/          { id = $2; gsub(/[",]/, "", id) }
                /^      "conclusion":/  { c = $2; gsub(/[",]/, "", c)
                                          if (c == "success" && id != "") { print id; exit } }
            ' "$TMP_DIR/runs.json")
            if [[ -z "$RUN_ID" ]]; then
                error "No successful ${WORKFLOW} run found on branch '${BRANCH}' of ${REPO}."
                error "Runs URL: ${RUNS_URL}"
                exit 1
            fi
        fi
        info "Using workflow run: ${RUN_ID}"

        # ─── Resolve the matching artifact ──────────────────────────
        ARTIFACT_NAME="${CSOUND7_MACOS_ARTIFACT:-}"
        if [[ -z "$ARTIFACT_NAME" ]]; then
            ARTIFACTS_URL="https://api.github.com/repos/${REPO}/actions/runs/${RUN_ID}/artifacts?per_page=100"
            verbose "Artifacts URL: ${ARTIFACTS_URL}"
            if ! github_api_get "$ARTIFACTS_URL" "$TMP_DIR/artifacts.json"; then
                error "Failed to list the artifacts of run ${RUN_ID}."
                error "URL: ${ARTIFACTS_URL}"
                api_error_hint
                exit 1
            fi
            while IFS= read -r name; do
                # intentional glob match against the artifact name
                # shellcheck disable=SC2254
                case "$name" in
                    $ARTIFACT_GLOB)
                        ARTIFACT_NAME="$name"
                        break
                        ;;
                esac
            done < <(awk '
                /^      "name":/ { n = $0; sub(/^[^"]*"name": "/, "", n); sub(/",?$/, "", n) }
                /^      "expired":/ { e = $0; sub(/^[^"]*"expired": /, "", e); sub(/,?$/, "", e)
                                      if (e == "false") print n }
            ' "$TMP_DIR/artifacts.json")
            if [[ -z "$ARTIFACT_NAME" ]]; then
                error "No artifact matching '${ARTIFACT_GLOB}' was found in run ${RUN_ID}."
                exit 1
            fi
        fi
        info "Using artifact: ${ARTIFACT_NAME}"

        # ─── Download via nightly.link ──────────────────────────────
        # GitHub Actions artifacts cannot be downloaded anonymously, so the
        # archive is fetched through the nightly.link mirror.
        DOWNLOAD_URL="https://nightly.link/${REPO}/actions/runs/${RUN_ID}/${ARTIFACT_NAME}.zip"
    fi

    verbose "Download URL: ${DOWNLOAD_URL}"
    info "Downloading ${ARTIFACT_NAME}..."
    if ! download_file "$DOWNLOAD_URL" "$ZIP_FILE"; then
        error "Failed to download ${ARTIFACT_NAME}"
        error "URL: ${DOWNLOAD_URL}"
        exit 1
    fi
    ok "Download complete: ${ZIP_FILE}"

    # ─── Extract ────────────────────────────────────────────────────
    EXTRACT_DIR="${TMP_DIR}/extracted"
    mkdir -p "$EXTRACT_DIR"
    info "Extracting ${ARTIFACT_NAME}..."
    if ! ditto -x -k "$ZIP_FILE" "$EXTRACT_DIR"; then
        error "Failed to extract ${ARTIFACT_NAME}"
        exit 1
    fi

    # ─── Locate the .pkg ────────────────────────────────────────────
    PKG=""
    while IFS= read -r -d '' candidate; do
        PKG="$candidate"
        break
    done < <(find "$EXTRACT_DIR" -name '*.pkg' -type f -print0)

    if [[ -z "$PKG" ]]; then
        error "No .pkg was found inside ${ARTIFACT_NAME}"
        exit 1
    fi

    info "Package: $(basename "$PKG")"

    # ─── Install ────────────────────────────────────────────────────
    if ((SUDO_NONINTERACTIVE)); then
        info "Installing Csound with the system installer (passwordless sudo)..."
    else
        info "Installing Csound with the system installer (sudo may prompt for your password)..."
    fi
    "${SUDO[@]}" /usr/sbin/installer -pkg "$PKG" -target /
    ok "Csound installed successfully."

    # ─── Optional: install risset ─────────────────────────────────
    maybe_install_risset

    if [ "$QUIET" = true ]; then
        result "Csound 7 installed successfully."
    fi
}

# ─── Dispatch by operating system ──────────────────────────────────
OS=$(uname -s)
case "$OS" in
    Linux)
        install_linux
        ;;
    Darwin)
        install_macos
        ;;
    *)
        echo "Unsupported operating system: $OS. Only Linux and macOS are supported."
        exit 1
        ;;
esac
