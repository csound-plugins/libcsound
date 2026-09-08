#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: getcsound.sh [OPTIONS] [-- BUNDLED-INSTALLER-OPTIONS]

Options:
  --help       Show this help without downloading the installer.
  --help-all   Download the installer and show this help plus the bundled installer help.
  --verbose    Show the download URLs and other diagnostic information.

Arguments after -- are passed unchanged to the bundled installer. Use --help-all
to see the bundled installer's supported options and parameters. On macOS the
.pkg is installed directly by the system installer, which accepts no extra
arguments.
EOF
}

VERBOSE=0
SHOW_HELP=0
HELP_ALL=0
INSTALLER_ARGS=()
while (($#)); do
    case "$1" in
        --help)
            SHOW_HELP=1
            ;;
        --help-all)
            HELP_ALL=1
            ;;
        --verbose)
            VERBOSE=1
            ;;
        --)
            shift
            INSTALLER_ARGS+=("$@")
            break
            ;;
        *)
            INSTALLER_ARGS+=("$1")
            ;;
    esac
    shift
done

if ((SHOW_HELP)); then
    usage
    exit 0
fi

# ─── Helpers ──────────────────────────────────────────────────────
error() {
    printf 'Error: %s\n' "$*" >&2
}

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

# github_api_get URL OUTFILE
#
# GitHub's API rate-limits anonymous requests (shared runner IPs are often
# blocked with HTTP 403). When GH_TOKEN is set it is used to authenticate;
# otherwise the request stays anonymous.
github_api_get() {
    local url=$1 out=$2
    if [[ -n "${GH_TOKEN:-}" ]]; then
        curl -fsSL -H "Authorization: Bearer ${GH_TOKEN}" -o "$out" "$url"
    else
        curl -fsSL -o "$out" "$url"
    fi
}

# ═══════════════════════════════════════════════════════════════════
# Csound 7 Portable Linux - One-line installer
#
# SAFER USAGE (recommended):
#   curl -fsSL -o install-csound7-linux.sh \
#       https://csound-plugins.github.io/getcsound.sh
#   # Read the script, then run it:
#   bash ./install-csound7-linux.sh
#
# One-line usage (convenient, but inspects nothing before execution):
#   curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash
#
# This script downloads the release asset named in CSOUND7_ASSET
# (default: csound7-linux-full.zip), verifies its SHA-256 checksum,
# extracts it, and runs the bundled install.sh.
#
# Trust model:
#   - The release archive is downloaded over HTTPS from GitHub.
#   - A SHA-256 checksum file (${ASSET}.sha256) is downloaded from the
#     same release and verified before extraction.
#   - Checksums guard against corruption and trivial modification, but
#     they are hosted in the same place as the archive. For stronger
#     trust, sign the checksum file with GPG and verify it here.
# ═══════════════════════════════════════════════════════════════════
install_linux() {
    require_command curl
    require_command unzip
    require_command mktemp

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
    DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${TAG}/${ASSET}"
    CHECKSUM_URL="https://github.com/${REPO}/releases/download/${TAG}/${CHECKSUM_ASSET}"

    # ─── Prepare temporary directory ────────────────────────────────
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT

    ZIP_FILE="${TMP_DIR}/${ASSET}"
    EXTRACT_DIR="${TMP_DIR}/extracted"
    mkdir -p "$EXTRACT_DIR"

    # ─── Download ───────────────────────────────────────────────────
    echo "Downloading ${ASSET}..."
    echo "URL: ${DOWNLOAD_URL}"
    if ! curl -fsSL -o "$ZIP_FILE" "$DOWNLOAD_URL"; then
        error "Failed to download ${ASSET}"
        error "URL: ${DOWNLOAD_URL}"
        exit 1
    fi
    echo "Download complete: ${ZIP_FILE}"

    # ─── Verify checksum ────────────────────────────────────────────
    echo "Downloading checksum file: ${CHECKSUM_ASSET}..."
    verbose "Checksum URL: ${CHECKSUM_URL}"
    if curl -fsSL -o "${ZIP_FILE}.sha256" "$CHECKSUM_URL"; then
        echo "Verifying SHA-256 checksum..."
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
        echo "Checksum verified."
    else
        error "Failed to download checksum file: ${CHECKSUM_ASSET}"
        error "URL: ${CHECKSUM_URL}"
        error "Refusing to install an unverified archive."
        exit 1
    fi

    # ─── Extract ────────────────────────────────────────────────────
    echo "Extracting ${ASSET}..."
    if ! unzip -q "$ZIP_FILE" -d "$EXTRACT_DIR"; then
        error "Failed to extract ${ASSET}"
        exit 1
    fi

    # ─── Locate bundled installer ───────────────────────────────────
    INSTALLER=""
    while IFS= read -r -d '' candidate; do
        INSTALLER="$candidate"
        break
    done < <(find "$EXTRACT_DIR" -name install.sh -type f -print0)

    if [[ -z "$INSTALLER" ]]; then
        error "install.sh was not found inside ${ASSET}"
        exit 1
    fi

    chmod +x "$INSTALLER"

    if ((HELP_ALL)); then
        usage
        printf '\nBundled installer help:\n'
        "$INSTALLER" --help
        exit 0
    fi

    # ─── Run installer ──────────────────────────────────────────────
    echo "Running bundled installer: ${INSTALLER}"
    if [[ -t 0 ]]; then
        # stdin is a terminal: run normally
        "$INSTALLER" "${INSTALLER_ARGS[@]}"
    else
        # Executed via curl | bash: give the interactive installer a TTY
        # so its prompts (read/sudo) work correctly.
        if [[ -e /dev/tty ]]; then
            "$INSTALLER" "${INSTALLER_ARGS[@]}" < /dev/tty
        else
            error "No terminal available (/dev/tty)."
            error "This installer is interactive; please run it from a terminal."
            exit 1
        fi
    fi
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
# fetched through the nightly.link mirror. Because installation runs under
# sudo, this path requires an interactive terminal session.
#
# Trust model:
#   - The artifact is downloaded over HTTPS and installed unmodified.
#   - There is no published checksum for workflow artifacts, so integrity
#     cannot be verified independently. The mirror (nightly.link) serves the
#     artifact bytes as produced by the workflow run.
# ═══════════════════════════════════════════════════════════════════
install_macos() {
    if ((HELP_ALL)); then
        usage
        printf '\nThe macOS package is installed directly by the system installer;\n'
        printf 'there is no bundled installer whose help could be shown.\n'
        exit 0
    fi

    require_command curl
    require_command mktemp

    # The install step runs under sudo, so an interactive terminal is required
    # to let sudo prompt for credentials. Refuse to run otherwise.
    if [[ ! -t 0 ]] && ! (exec 3<>/dev/tty) 2>/dev/null; then
        error "The macOS installer needs sudo and must be run from a terminal."
        error "Please run it from an interactive Terminal session."
        exit 1
    fi

    if ((${#INSTALLER_ARGS[@]})); then
        printf 'Warning: arguments after -- (%s) are ignored on macOS.\n' "${INSTALLER_ARGS[*]}" >&2
    fi

    REPO="${CSOUND7_REPO:-csound/csound}"
    WORKFLOW="${CSOUND7_WORKFLOW:-csound_builds.yml}"
    BRANCH="${CSOUND7_MACOS_BRANCH:-develop}"
    ARTIFACT_GLOB="${CSOUND7_MACOS_ASSET:-csound-7.*-macos*}"

    # Use a token for the GitHub API queries when one is available in the
    # environment (e.g. GITHUB_TOKEN on CI); anonymous otherwise.
    GH_TOKEN="${CSOUND7_GH_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"

    # ─── Prepare temporary directory ────────────────────────────────
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT

    # ─── Resolve the latest successful workflow run ─────────────────
    RUN_ID="${CSOUND7_MACOS_RUN_ID:-}"
    if [[ -z "$RUN_ID" ]]; then
        echo "Looking for the latest successful ${WORKFLOW} run on branch '${BRANCH}' of ${REPO}..."
        RUNS_URL="https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?branch=${BRANCH}&event=push&per_page=30"
        verbose "Runs URL: ${RUNS_URL}"
        if ! github_api_get "$RUNS_URL" "$TMP_DIR/runs.json"; then
            error "Failed to query workflow runs."
            error "URL: ${RUNS_URL}"
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
    echo "Using workflow run: ${RUN_ID}"

    # ─── Resolve the matching artifact ──────────────────────────────
    ARTIFACT_NAME="${CSOUND7_MACOS_ARTIFACT:-}"
    if [[ -z "$ARTIFACT_NAME" ]]; then
        ARTIFACTS_URL="https://api.github.com/repos/${REPO}/actions/runs/${RUN_ID}/artifacts?per_page=100"
        verbose "Artifacts URL: ${ARTIFACTS_URL}"
        if ! github_api_get "$ARTIFACTS_URL" "$TMP_DIR/artifacts.json"; then
            error "Failed to list the artifacts of run ${RUN_ID}."
            error "URL: ${ARTIFACTS_URL}"
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
    echo "Using artifact: ${ARTIFACT_NAME}"

    # ─── Download via nightly.link ──────────────────────────────────
    ZIP_FILE="${TMP_DIR}/macos.zip"
    DOWNLOAD_URL="https://nightly.link/${REPO}/actions/runs/${RUN_ID}/${ARTIFACT_NAME}.zip"
    verbose "Download URL: ${DOWNLOAD_URL}"
    echo "Downloading ${ARTIFACT_NAME}..."
    if ! curl -fsSL -o "$ZIP_FILE" "$DOWNLOAD_URL"; then
        error "Failed to download ${ARTIFACT_NAME}"
        error "URL: ${DOWNLOAD_URL}"
        exit 1
    fi
    echo "Download complete: ${ZIP_FILE}"

    # ─── Extract ────────────────────────────────────────────────────
    EXTRACT_DIR="${TMP_DIR}/extracted"
    mkdir -p "$EXTRACT_DIR"
    echo "Extracting ${ARTIFACT_NAME}..."
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

    echo "Package: $(basename "$PKG")"

    # ─── Install ────────────────────────────────────────────────────
    echo "Installing Csound with the system installer (sudo may prompt for your password)..."
    sudo /usr/sbin/installer -pkg "$PKG" -target /
    echo "Csound installed successfully."
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
