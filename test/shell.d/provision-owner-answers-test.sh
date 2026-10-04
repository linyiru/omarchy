#!/bin/bash

set -euo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/base-test.sh"

# First-boot setup with answers the platform staged before the boot, as a
# Raspberry Pi stages the settings Raspberry Pi Imager wrote: the form skips the
# fields they cover, checks each the way its prompt would, and asks for the
# rest. load_answers, keyboard_form, user_form and staged_username_valid run as
# omarchy-provision-owner defines them, with the prompts faked.

tmp=$(cd -- "$(mktemp -d)" && pwd -P)
trap 'rm -rf "$tmp"' EXIT

sed -n '/^load_answers() {/,/^}/p; /^keyboard_form() {/,/^}/p; /^user_form() {/,/^}/p; /^staged_username_valid() {/,/^}/p' \
  "$ROOT/bin/omarchy-provision-owner" >"$tmp/form-steps.sh"
for fn in load_answers keyboard_form user_form staged_username_valid; do
  grep -q "^$fn() {" "$tmp/form-steps.sh" || fail "omarchy-provision-owner defines $fn"
done

cat >"$tmp/form.sh" <<SH
set -euo pipefail
source "$ROOT/install/provisioning/setup-form.sh"
source "$tmp/form-steps.sh"
PROVISIONING_DIR=$tmp/provisioning
ANSWERS_FILE=$tmp/provisioning/answers
LOG_FILE=$tmp/log
declare -A answers=()
step() { :; }
say() { :; }
notice() { :; }
log_step() { echo "\$1" >>"\$LOG_FILE"; }
confirm_reboot() { exit 5; }
encrypted_install() { [[ -e $tmp/encrypted ]]; }
omarchy_username_taken() { [[ \$1 == "taken" ]]; }
apply_keyboard() { [[ \$1 != "broken" ]]; }
asked() { echo "\$1" >>"$tmp/asked"; }
omarchy_prompt_keyboard() { asked keyboard; keyboard=us keyboard_label="English (US)"; }
omarchy_prompt_username() { asked username; username=typed; }
omarchy_prompt_password() { asked password; password=typed-password; }
omarchy_prompt_identity() { asked identity; full_name="" email_address=""; }
omarchy_prompt_hostname() { asked hostname; hostname=omarchy; }
omarchy_prompt_timezone() { asked timezone; timezone=UTC; }
load_answers
keyboard_form
user_form
declare -p keyboard keyboard_label username password password_hash hostname timezone >"$tmp/result"
SH

run_form() {
  rm -rf "$tmp/provisioning" "$tmp/asked" "$tmp/result" "$tmp/log" "$tmp/encrypted"
  mkdir -p "$tmp/provisioning"
  : >"$tmp/asked"
  if (($#)); then
    printf '%s\n' "$@" >"$tmp/provisioning/answers"
  fi
  bash "$tmp/form.sh" || fail "the form finishes" "$(cat "$tmp/log" 2>/dev/null)"
}

asked_list() {
  paste -sd' ' "$tmp/asked"
}

value_of() {
  (source "$tmp/result" && printf '%s' "${!1}")
}

hash='$y$j9T$abcdefghijklmnop$0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef'

run_form
[[ $(asked_list) == "keyboard username password identity hostname timezone" ]] ||
  fail "with no answers every field is asked" "$(asked_list)"
pass "with no staged answers the form asks every field"

run_form "keymap=de" "username=alice" "password_hash=$hash" "hostname=pi-desk" "timezone=Europe/Berlin"
[[ $(asked_list) == "identity" ]] || fail "only what Imager has no field for is asked" "$(asked_list)"
[[ $(value_of keyboard) == "de" && $(value_of keyboard_label) == "German" ]] ||
  fail "the staged keymap is applied with the form's label" "$(cat "$tmp/result")"
[[ $(value_of username) == "alice" && $(value_of hostname) == "pi-desk" && $(value_of timezone) == "Europe/Berlin" ]] ||
  fail "the staged account, hostname and timezone are kept" "$(cat "$tmp/result")"
[[ $(value_of password_hash) == "$hash" && -z $(value_of password) ]] ||
  fail "the staged password stays a hash" "$(cat "$tmp/result")"
pass "a complete set of answers leaves only the name and email to ask"

run_form "keymap=broken" "username=taken" "password_hash=plaintext" "hostname=-bad-" "timezone=Not/AZone" "shell=/bin/zsh"
[[ $(asked_list) == "keyboard username password identity hostname timezone" ]] ||
  fail "answers the prompts would reject are asked again" "$(asked_list)"
grep -q "staged keymap broken did not take" "$tmp/log" || fail "a keymap that did not take is logged" "$(cat "$tmp/log")"
[[ -z $(value_of password_hash) && $(value_of password) == "typed-password" ]] ||
  fail "a password that is not a crypt hash is never stored" "$(cat "$tmp/result")"
pass "an answer the form would reject is asked for instead"

rm -f "$tmp/encrypted"
mkdir -p "$tmp/provisioning"
printf '%s\n' "username=alice" "password_hash=$hash" >"$tmp/provisioning/answers"
touch "$tmp/encrypted"
: >"$tmp/asked"
bash "$tmp/form.sh" || fail "the encrypted form finishes"
grep -qx password "$tmp/asked" || fail "an encrypted install asks for the password the disk takes" "$(asked_list)"
[[ -z $(value_of password_hash) ]] || fail "an encrypted install ignores the staged hash" "$(cat "$tmp/result")"
pass "an encrypted install asks for its password despite a staged hash"
