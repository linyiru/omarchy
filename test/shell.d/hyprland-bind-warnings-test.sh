#!/bin/bash

source "$(dirname "${BASH_SOURCE[0]}")/base-test.sh"

require_command lua

tmpdir=$(mktemp -d) && [[ -n $tmpdir && -d $tmpdir ]] ||
  fail "the test gets a temporary directory to load the Lua config in"
trap 'rm -rf "$tmpdir"' EXIT

declaration() {
  cat >"$tmpdir/bind.lua" <<LUA
hl = {
  dsp = { exec_cmd = function(command) return command end },
  bind = function(keys, dispatcher, opts)
    print("dispatcher: " .. tostring(dispatcher))
  end,
  unbind = function() end,
}

dofile("$ROOT/default/hypr/helpers.lua")

$1
LUA
}

# What a declaration writes on stderr, which is where a warning has to land.
warnings() {
  declaration "$1"
  lua "$tmpdir/bind.lua" 2>&1 >/dev/null
}

# What it writes on stdout, which belongs to the keybindings menu.
printed() {
  declaration "$1"
  lua "$tmpdir/bind.lua" 2>/dev/null
}

reported=$(warnings 'o.bind("SUPER + K", "Calendar", "true", { locked = true }, { id = "calendar" })')
grep -qF 'SUPER + K' <<<"$reported" ||
  fail "a bind passing a fifth argument names itself in the warning" "$reported"
grep -qF 'passes 5' <<<"$reported" ||
  fail "a bind passing a fifth argument is reported" "$reported"
pass "a bind passing a fifth argument is reported"

reported=$(warnings 'o.bind("SUPER + K", "Calendar", "true", { id = "calendar" })')
[[ -z $reported ]] ||
  fail "a bind passing four arguments is left alone" "$reported"
pass "a bind passing four arguments is left alone"

# The menu loads the config under a stub and reads records off stdout, so a
# warning written there would arrive as a row rather than as a warning.
rendered=$(printed 'o.bind("SUPER + K", "Calendar", "true", { locked = true }, { id = "calendar" })')
grep -qx 'dispatcher: true' <<<"$rendered" ||
  fail "a bind that warns still dispatches what it declared" "$rendered"
! grep -qF 'passes 5' <<<"$rendered" ||
  fail "a warning stays off the stream the keybindings menu parses" "$rendered"
pass "a warning stays off the stream the keybindings menu parses"

reported=$(warnings 'o.rebind("SUPER + K", "Calendar", "true", { locked = true }, { id = "calendar" })')
grep -qF 'SUPER + K' <<<"$reported" ||
  fail "a rebind passing a fifth argument is reported against its own keys" "$reported"
pass "a rebind passing a fifth argument is reported against its own keys"

# Every wrapper that forwards to o.bind has to forward the extras with it, or it
# becomes the one place a fifth argument still disappears without a word.
reported=$(warnings 'o.bind_toggle("SUPER + CTRL + N", "Toggle nightlight", "nightlight", { locked = true }, { id = "nightlight" })')
grep -qF 'SUPER + CTRL + N' <<<"$reported" ||
  fail "a toggle bind passing a fifth argument is reported against its own keys" "$reported"
pass "a toggle bind passing a fifth argument is reported against its own keys"

# A warning nobody ever sees is the only acceptable outcome on a stock machine,
# so load every binding file Omarchy ships. Read the stub out of the menu rather
# than keeping a second copy of it: it is the one place the whole config loads.
sed -n "/^    lua <<'LUA'\$/,/^LUA\$/p" "$ROOT/bin/omarchy-menu-keybindings" |
  sed '1d;$d' >"$tmpdir/scan.lua"
[[ -s $tmpdir/scan.lua ]] ||
  fail "the menu's Lua bind scan can be read out of the script"

home="$tmpdir/home"
mkdir -p "$home/.config/hypr"

cat >"$home/.config/hypr/hyprland.lua" <<LUA
dofile("$ROOT/default/hypr/bootstrap.lua")
require("default.hypr.helpers")
require("default.hypr.bindings.media")
require("default.hypr.bindings.clipboard")
require("default.hypr.bindings.tiling")
require("default.hypr.bindings.utilities")
require("default.hypr.bindings.voxtype")
require("default.hypr.bindings.applications")
LUA

scan() {
  env -i PATH="$PATH" HOME="$home" OMARCHY_PATH="$ROOT" lua "$tmpdir/scan.lua"
}

scanned=$(scan 2>/dev/null)
reported=$(scan 2>&1 >/dev/null)

# The scan loads the config through pcall, so a module that threw would leave
# stderr empty and pass the assertion below for the wrong reason. Count the
# records first: every binding file has to have run for the silence to mean
# anything.
(( $(grep -c . <<<"$scanned") > 150 )) ||
  fail "every binding file Omarchy ships loads under the scan" "$scanned"
[[ -z $reported ]] ||
  fail "the bindings Omarchy ships warn about nothing" "$reported"
pass "the bindings Omarchy ships warn about nothing"
