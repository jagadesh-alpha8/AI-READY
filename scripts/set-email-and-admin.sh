#!/usr/bin/env bash
# Set the production email account (forgot password + error alerts) and the admin login.
#
# Run from WSL (it uses the "AIOS" ssh host):
#   bash "/mnt/d/AI READY/scripts/set-email-and-admin.sh"
#
# It asks for the values with hidden typing and sends them to the server over
# ssh stdin -- never on a command line, never into git. Safe to re-run, e.g.
# to rotate the Gmail app password or reset the admin password.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${AIOS_HOST:-AIOS}"

read -rp  'Gmail address that sends the emails [myingage@gmail.com]: ' GMAIL
GMAIL="${GMAIL:-myingage@gmail.com}"
read -rsp 'Gmail app password (16 letters, spaces are fine): ' APP_PW; echo
read -rp  'Admin email [jagadesh.v@myingage.com]: ' ADMIN
ADMIN="${ADMIN:-jagadesh.v@myingage.com}"
read -rsp 'Admin password: ' ADMIN_PW; echo
[ -n "$APP_PW" ] && [ -n "$ADMIN_PW" ] || { echo 'Both passwords are needed.'; exit 1; }

ssh -o BatchMode=yes "$HOST" 'sudo tee /usr/local/sbin/ai-ready-set-email.py >/dev/null && sudo chmod 700 /usr/local/sbin/ai-ready-set-email.py' \
  < "$HERE/server/set_email_and_admin.py"
printf '%s\n%s\n%s\n%s\n' "$GMAIL" "$APP_PW" "$ADMIN" "$ADMIN_PW" \
  | ssh -o BatchMode=yes "$HOST" 'sudo python3 /usr/local/sbin/ai-ready-set-email.py'
unset APP_PW ADMIN_PW
echo "Done. Check $ADMIN for the test email, then try 'Forgot password?' on https://ai.ingageedutech.com/login"
