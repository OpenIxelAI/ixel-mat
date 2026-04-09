#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${IXEL_REPO_URL:-https://github.com/OpenIxelAI/ixel-mat.git}"
BRANCH="${IXEL_BRANCH:-main}"
INSTALL_ROOT="${IXEL_INSTALL_ROOT:-$HOME/.local/share/ixel-mat}"
BIN_DIR="${IXEL_BIN_DIR:-$HOME/.local/bin}"
REPO_DIR="$INSTALL_ROOT/repo"
VENV_DIR="$INSTALL_ROOT/.venv"
WRAPPER_PATH="$BIN_DIR/ixel"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing required command: $1" >&2
    exit 1
  }
}

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    echo python
    return
  fi
  echo "error: python3 or python is required" >&2
  exit 1
}

append_path_hint() {
  if [[ "${IXEL_SKIP_PATH_UPDATE:-0}" == "1" ]]; then
    return
  fi
  case ":$PATH:" in
    *":$BIN_DIR:"*) return ;;
  esac

  local shell_name profile_line target_file=""
  shell_name="$(basename "${SHELL:-}")"
  profile_line="export PATH=\"$BIN_DIR:\$PATH\""

  case "$shell_name" in
    zsh) target_file="$HOME/.zshrc" ;;
    bash) target_file="$HOME/.bashrc" ;;
  esac

  if [[ -n "$target_file" ]]; then
    mkdir -p "$(dirname "$target_file")"
    touch "$target_file"
    if ! grep -Fq "$profile_line" "$target_file"; then
      printf '\n# Added by Ixel MAT installer\n%s\n' "$profile_line" >> "$target_file"
      echo "Added $BIN_DIR to PATH in $target_file"
    fi
  fi
}

need_cmd git
PYTHON_BIN="$(pick_python)"

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" fetch origin
  git -C "$REPO_DIR" checkout "$BRANCH"
  git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
else
  rm -rf "$REPO_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"

cat > "$WRAPPER_PATH" <<EOF
#!/usr/bin/env bash
set -euo pipefail
INSTALL_ROOT="${INSTALL_ROOT}"
REPO_DIR="\$INSTALL_ROOT/repo"
VENV_DIR="\$INSTALL_ROOT/.venv"
if [[ \$# -eq 0 ]]; then
  exec "\$VENV_DIR/bin/python" "\$REPO_DIR/mat.py"
else
  exec "\$VENV_DIR/bin/python" "\$REPO_DIR/cli.py" "\$@"
fi
EOF
chmod +x "$WRAPPER_PATH"

append_path_hint

echo
echo "Ixel MAT installed."
echo "Binary: $WRAPPER_PATH"
echo "Run: ixel"
echo "If your shell cannot find 'ixel' yet, restart the shell or run:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
