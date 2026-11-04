#!/usr/bin/env bash
# intervals-coach-agent installer for Linux with systemd.
#
#   sudo ./install.sh [--chat-id N] [--key FILE] [--instance DIR]
#
#   --chat-id N     your Telegram chat id (send /whoami to the bot to find it)
#   --key FILE      Google service-account JSON key, for the optional shared journal
#   --instance DIR  a directory with your own config.yaml, athlete/profile.md and env file
#                   (default: the generic templates in ./examples)
#
# Run it from a checkout of the repository. It is safe to re-run. It always rebuilds the
# package in /opt/coach-agent (source and Python environment), and it never overwrites the
# instance in /etc/coach-agent or the state in /var/lib/coach-agent: an existing file is kept,
# and the new template is written beside it as <file>.bundle.
#
# Supported package managers for the Python prerequisite: dnf/yum, apt, zypper, pacman.
# On anything else, install Python 3.11+ with the venv module yourself, then run this script.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPT=/opt/coach-agent
ETC=/etc/coach-agent
STATE=/var/lib/coach-agent
SERVICE_USER=coach
CHAT_ID=""
KEY=""
INSTANCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --chat-id)  CHAT_ID="$2"; shift 2 ;;
    --key)      KEY="$2"; shift 2 ;;
    --instance) INSTANCE="$2"; shift 2 ;;
    -h|--help)  sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32mok\033[0m  %s\n' "$*"; }
warn() { printf '    \033[33m!!\033[0m  %s\n' "$*"; WARNINGS+=("$*"); }
WARNINGS=()

[[ $EUID -eq 0 ]] || { echo "Run as root (for example: sudo ./install.sh)." >&2; exit 1; }
[[ "$(uname -s)" == "Linux" ]] || { echo "install.sh is for Linux. See docs/INSTALL.md for macOS and Windows." >&2; exit 1; }
[[ -d "$HERE/coach" && -f "$HERE/pyproject.toml" ]] || { echo "Run from the repository root." >&2; exit 1; }
if [[ -n "$CHAT_ID" && ! "$CHAT_ID" =~ ^-?[0-9]+$ ]]; then echo "--chat-id must be a number" >&2; exit 2; fi

# Instance templates: --instance DIR, else the generic examples shipped with the repo.
if [[ -n "$INSTANCE" ]]; then
  T_CONFIG="$INSTANCE/config.yaml"; T_PROFILE="$INSTANCE/athlete/profile.md"
  T_ENV="$INSTANCE/env.example"; [[ -f "$T_ENV" ]] || T_ENV="$HERE/examples/env.example"
else
  T_CONFIG="$HERE/examples/config.example.yaml"; T_PROFILE="$HERE/examples/athlete-profile.example.md"
  T_ENV="$HERE/examples/env.example"
fi
for f in "$T_CONFIG" "$T_PROFILE" "$T_ENV"; do [[ -f "$f" ]] || { echo "Missing template: $f" >&2; exit 1; }; done

# ------------------------------------------------------------------ 1. Python
say "1. Python 3.11+ with venv"
have_python() {  # prints the first interpreter that is 3.11+ and can create a venv
  local c
  for c in python3.13 python3.12 python3.11 python3; do
    command -v "$c" >/dev/null || continue
    "$c" -c 'import sys, ensurepip, venv; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null \
      && { echo "$c"; return 0; }
  done
  return 1
}
install_python() {
  if command -v dnf >/dev/null; then
    # RHEL/Rocky/Alma 9 ship 3.9 as python3; 3.12 is an AppStream package. Fedora/EL10 python3 is new enough.
    dnf -y install python3.12 python3.12-pip 2>/dev/null || dnf -y install python3 python3-pip
  elif command -v yum >/dev/null; then
    yum -y install python3.12 python3.12-pip || yum -y install python3 python3-pip
  elif command -v apt-get >/dev/null; then
    apt-get update -qq
    local v; v=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 python3-venv ${v:+python$v-venv}
  elif command -v zypper >/dev/null; then
    zypper --non-interactive install python312 || zypper --non-interactive install python3
  elif command -v pacman >/dev/null; then
    pacman -Sy --noconfirm --needed python
  else
    return 1
  fi
}
if ! PY=$(have_python); then
  install_python || { echo "No supported package manager. Install Python 3.11+ with venv, then re-run." >&2; exit 1; }
  PY=$(have_python) || { echo "Python 3.11+ with venv is still not available. Install it, then re-run." >&2; exit 1; }
fi
ok "$PY ($("$PY" --version 2>&1))"

# ------------------------------------------------------------------ 2. Account and directories
say "2. Service account and directories"
NOLOGIN=$(command -v nologin || echo /usr/sbin/nologin)
if id "$SERVICE_USER" >/dev/null 2>&1; then
  ok "User $SERVICE_USER exists"
else
  useradd --system --home-dir "$STATE" --create-home --shell "$NOLOGIN" "$SERVICE_USER"
  ok "Created system user $SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 750 "$STATE"
install -d -o root -g root -m 755 "$OPT"
install -d -o root -g "$SERVICE_USER" -m 750 "$ETC" "$ETC/athlete"
ok "$OPT  $ETC  $STATE"

# ------------------------------------------------------------------ 3. Package
say "3. Package (source and Python environment)"
if command -v systemctl >/dev/null && systemctl is-active --quiet coach-agent 2>/dev/null; then
  systemctl stop coach-agent; ok "Stopped the running service"
fi
rm -rf "$OPT/src" "$OPT/venv"
mkdir -p "$OPT/src"
# Copy the checkout without VCS metadata or local build artefacts.
tar -C "$HERE" --exclude=.git --exclude='*.egg-info' --exclude=__pycache__ --exclude=.pytest_cache \
    --exclude=./data --exclude=./venv --exclude=./.venv -cf - . | tar -C "$OPT/src" -xf -
chown -R root:root "$OPT/src"
"$PY" -m venv "$OPT/venv"
"$OPT/venv/bin/pip" install --quiet --upgrade pip
"$OPT/venv/bin/pip" install --quiet "$OPT/src"
VPY="$OPT/venv/bin/python"
SDK=$("$VPY" -c 'import claude_agent_sdk as s, os; print(os.path.dirname(s.__file__))')
ln -sf "$SDK/_bundled/claude" "$OPT/venv/bin/claude"
ok "Package $("$VPY" -c 'from importlib.metadata import version; print(version("intervals-coach-agent"))') installed"
ok "Claude CLI $("$OPT/venv/bin/claude" --version 2>/dev/null | head -1)"
install -m 755 "$OPT/src/deploy/coach-as" /usr/local/bin/coach-as
ok "/usr/local/bin/coach-as"

# ------------------------------------------------------------------ 4. Instance (never overwritten)
say "4. Instance configuration in $ETC"
place() {  # place <template> <target>
  if [[ -e "$2" ]]; then
    install -o root -g "$SERVICE_USER" -m 640 "$1" "$2.bundle"
    ok "Kept existing $(basename "$2") (template saved as $(basename "$2").bundle)"
  else
    install -o root -g "$SERVICE_USER" -m 640 "$1" "$2"
    ok "Installed $(basename "$2")"
  fi
}
place "$T_CONFIG" "$ETC/config.yaml"
place "$T_PROFILE" "$ETC/athlete/profile.md"
place "$T_ENV" "$ETC/.env"
if [[ -n "$KEY" ]]; then
  install -o root -g "$SERVICE_USER" -m 640 "$KEY" "$ETC/google-service-account.json"
  ok "Installed the Google service-account key"
fi
if [[ -n "$CHAT_ID" ]]; then
  sed -i -E "s/^(  allowed_chat_ids: )\[[0-9-]*\]/\1[$CHAT_ID]/; s/^(  default_chat_id: )[0-9-]+/\1$CHAT_ID/" "$ETC/config.yaml"
  ok "Chat id set to $CHAT_ID"
fi

# ------------------------------------------------------------------ 5. systemd and SELinux
say "5. systemd unit"
install -m 644 "$OPT/src/deploy/coach-agent.service" /etc/systemd/system/coach-agent.service
if command -v restorecon >/dev/null; then
  restorecon -R "$OPT" "$ETC" "$STATE" /usr/local/bin/coach-as /etc/systemd/system/coach-agent.service
  ok "SELinux labels restored"
fi
HAVE_SYSTEMD=0
if command -v systemctl >/dev/null && [[ -d /run/systemd/system ]]; then
  HAVE_SYSTEMD=1
  systemctl daemon-reload
  systemctl enable coach-agent >/dev/null 2>&1
  ok "Service installed and enabled"
else
  warn "systemd is not running here: start the agent with  coach-as coach-agent  (see docs/INSTALL.md)"
fi

# ------------------------------------------------------------------ 6. Checks
say "6. Checks"
if grep -qE '^ANTHROPIC_API_KEY=(sk-ant-\.\.\.)?$' "$ETC/.env"; then warn "Set ANTHROPIC_API_KEY in $ETC/.env"; else ok "Anthropic API key set"; fi
if grep -qE '^TELEGRAM_BOT_TOKEN=(123456:ABC\.\.\.)?$' "$ETC/.env"; then warn "Set TELEGRAM_BOT_TOKEN in $ETC/.env"; else ok "Telegram bot token set"; fi
if grep -qE '^  allowed_chat_ids: \[(0|123456789)\]' "$ETC/config.yaml"; then
  warn "Chat id not set: run  coach-as coach-agent , send /whoami to the bot, Ctrl-C, then re-run with --chat-id N"
else
  ok "Chat id set"
fi
if ! grep -q '^journal:' "$ETC/config.yaml"; then
  warn "Your config.yaml has no journal: block (optional); see config.yaml.bundle"
elif awk '/^journal:/{j=1;next} /^[^ #]/{j=0} j&&/^  enabled: *true/{f=1} END{exit !f}' "$ETC/config.yaml"; then
  if [[ -f "$ETC/google-service-account.json" ]]; then ok "Journal key present"
  else warn "Journal enabled but $ETC/google-service-account.json is missing: re-run with --key FILE, or set journal.enabled: false"; fi
fi
# The Intervals sign-in lives in $STATE, so it survives a package rebuild.
if ! timeout 60 coach-as claude mcp list 2>/dev/null | grep -q '^intervals:'; then
  coach-as claude mcp add --scope user --transport http intervals https://mcp.intervals.icu/mcp >/dev/null
  ok "Registered the Intervals.icu Connector"
fi
if timeout 60 coach-as claude mcp list 2>/dev/null | grep '^intervals:' | grep -q Connected; then
  ok "Intervals.icu Connector signed in"
else
  warn "Intervals.icu not signed in: run  coach-as claude mcp login --no-browser intervals"
fi

# ------------------------------------------------------------------ 7. Start
say "7. Result"
if [[ ${#WARNINGS[@]} -eq 0 && $HAVE_SYSTEMD -eq 1 ]]; then
  systemctl restart coach-agent
  sleep 3
  if systemctl is-active --quiet coach-agent; then ok "coach-agent is running. Send /jobs to your bot."
  else warn "The service did not start: journalctl -u coach-agent -n 50 --no-pager"; fi
else
  echo "    Still to do:"
  for w in "${WARNINGS[@]}"; do echo "      - $w"; done
  echo "    Then re-run ./install.sh (it starts the service when nothing is left), or: systemctl restart coach-agent"
fi
