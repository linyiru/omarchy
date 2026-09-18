#!/usr/bin/env python3
"""Stratified census of user-facing English strings in the Omarchy tree.

One number cannot describe this population: the strata below need different
mechanisms and differ in cost by an order of magnitude. Reporting a single
"unmarked strings" total is what made two earlier surveys of this tree disagree
by 2.6x.

Every figure printed here is a (predicate, tree) pair, and both halves are
stated. The predicate for each stratum is in PREDICATES and printed with the
table; the tree is pinned by PINNED_SHA and the counts it produced are in
PINNED, so a predicate that drifts fails loudly instead of quietly publishing a
different number under the same name.

    python3 omarchy-i18n-census.py <repo-root>     # census, verified against PINNED
    python3 omarchy-i18n-census.py <root> --no-pin # a tree other than PINNED_SHA
    python3 omarchy-i18n-census.py --predicates    # just the predicates

Exit status: 0 ok, 2 the prose test failed a pinned case, 3 a stratum count
drifted from PINNED (either the tree moved or a predicate changed).
"""
import os
import re
import sys
from collections import defaultdict

# omacom/omarchy, branch quattro, committed 2026-09-16. Every count in PINNED
# below was produced against `git archive 9c5482c5`, not against a working tree.
PINNED_SHA = "9c5482c58dbe4974de337450754885083c91eada"

# Surfaces that are not user-facing and must never enter a catalog.
EXCLUDE_PATHS = (
    "shell/plugins/dev-gallery/",   # developer reference, shown only via a dev flag
    "test/",                        # fixtures and expectations
)

# The bash tree the census reads. Stated because it is part of the predicate:
# a different file set is a different number under the same stratum name.
BASH_ROOTS = ("bin", "install", "migrations")

# ---------------------------------------------------------------------------
# The one distinction that organises everything below.
#
# A *sift* stratum is a pile of arbitrary string literals in code, only some of
# which reach a human, so the census has to guess: is_prose() is the guess and
# it is pinned by SELFTEST. A *schema* stratum is a named field that is
# human-facing by construction -- a menu label, a keybinding description, a
# command summary -- so every value counts and applying a prose heuristic there
# only invents false negatives. Four of the five figures corrected after this
# census first published were the same mistake: is_prose() gating a schema
# stratum.
# ---------------------------------------------------------------------------
SIFT_STRATA = ("bash-plain", "bash-interpolating", "bash-heredoc-block", "qml")
SCHEMA_STRATA = ("bash-metadata", "menu-data", "keybind-data")

# Commands whose quoted arguments reach a human.
OUT_CMD = r"(?:echo|printf|omarchy-notification-send|gum\s+(?:confirm|input|choose|spin|style|format|table))"
OUT_FLAG = r"--(?:header|prompt|placeholder|title|affirmative|negative)"
STR = r'"((?:[^"\\]|\\.)*)"'

# Two stages on purpose: one regex finds the window a command's arguments live
# in, a second pulls every literal out of it. A single combined pattern stops at
# the first literal per line, which silently drops the second argument of
# `omarchy-notification-send "Headline" "Body"`.
# The window must be able to cross a `|`, `;` or `&` that sits *inside* a quoted
# literal -- `echo "Usage: … <raise|lower>"` is one argument, not two commands --
# so it alternates bare characters with whole literals and stops at the first
# unquoted separator.
RE_OUT_WINDOW = re.compile(OUT_CMD + r'(?:[^\n;|&"]|' + STR + r")*")
RE_FLAG_WINDOW = re.compile(OUT_FLAG + r"=?\s*(?:\S+\s+)?" + STR)
RE_LITERAL = re.compile(STR)
RE_MARKED = re.compile(r'\$"((?:[^"\\]|\\.)*)"')
RE_HEREDOC = re.compile(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s*$")

# Schema fields. `summary` only: it is the one-line description the `omarchy`
# router prints, exactly one per file and prose by construction. `args` is
# counted separately under EXCLUDED because it is usage syntax, not sentences.
RE_META_SUMMARY = re.compile(r"^#\s*omarchy:summary=(.+)$")
RE_META_ARGS = re.compile(r"^#\s*omarchy:args=(.+)$")

# `o.bind` and `o.bind_toggle` are the whole family present in the tree at
# PINNED_SHA; `o.rebind` was in an earlier version of this predicate and matches
# nothing. The description must be a plain double-quoted literal: a Lua
# expression or concatenation in that slot is not a catalog entry.
RE_KEYBIND_FAMILY = re.compile(r'\bo\.(?:bind|bind_toggle)\(\s*"[^"]*"\s*,\s*' + STR)
RE_KEYBIND_SOLO = re.compile(r'\bo\.bind\(\s*"[^"]*"\s*,\s*' + STR)

RE_MENU_LABEL = re.compile(r'"label"\s*:\s*' + STR)
RE_MENU_TITLE = re.compile(r'"title"\s*:\s*' + STR)

RE_INTERP = re.compile(r"[$`]")
RE_LETTERS = re.compile(r"[A-Za-z]{2,}")

RE_EXPANSION = re.compile(r"\$\{[^}]*\}|\$\([^)]*\)|`[^`]*`|\$[A-Za-z_][A-Za-z0-9_]*")
RE_USAGE = re.compile(r"--?[A-Za-z][\w-]*|\[[^\]]*\]|<[^>]*>")
# Terminal control strings. An OSC sequence is payload all the way to its
# terminator, so it goes entirely; a CSI sequence wraps prose, so only the
# sequence goes and the words between two of them survive.
RE_ESCAPE = re.compile(
    r"\\+(?:e|0?33|x1[bB])\][^\\]*"
    r"|\\+(?:e|0?33|x1[bB])\[[0-9;]*[A-Za-z]"
    r"|\\+[ntre0]")


def is_prose(s):
    """A literal a translator could work on, as opposed to an id, path or flag.

    The residue after removing shell expansions and usage syntax is what a
    translator would actually see, so the test runs on that, not on the raw
    literal: "${COMMAND_ROUTE[$key]}" and "[--inline] [--pick]" leave nothing.

    Used only on SIFT_STRATA. Applying it to a schema field is a bug, not a
    conservatism: `is_prose("Custom")` is a judgement call, but a menu label
    reading "Custom" is a catalog entry whatever the heuristic thinks.
    """
    s = s.strip()
    if not s or s.startswith(("http", "/", "~", "#", "-", ".", "%")):
        return False
    if s.endswith((".qml", ".js", ".sh", ".json", ".svg", ".png", ".conf", ".toml")):
        return False
    residue = RE_USAGE.sub(" ", RE_ESCAPE.sub(" ", RE_EXPANSION.sub(" ", s))).strip()
    words = RE_LETTERS.findall(residue)
    if not words:
        return False
    if len(words) >= 2:
        return True
    word = words[0]
    if len(word) < 3:
        return False
    # A lone word is a UI label when it is capitalised or an all-caps section
    # heading and carries no identifier punctuation; "Close", "Apps" and
    # "BRIGHTNESS" are copy, "keyboard-us" and a Nerd Font glyph are not.
    if not re.search(r"[_\-.\d/]", residue) and (
            re.fullmatch(r"[A-Z][a-z]+", word) or re.fullmatch(r"[A-Z]{3,}", word)):
        return True
    return residue.rstrip().endswith((".", "!", "?", ":")) and len(word) >= 4


# ---------------------------------------------------------------------------
# qml: the honest stratum. The count depends on two independent choices, so the
# census reports the whole 3x3 grid rather than one number. The shipped figure
# is MID x prose, marked in the grid; every other cell is reachable by a
# defensible reading of "a display property bound to a bare literal".
# ---------------------------------------------------------------------------
QML_PROPS = {
    "core": ["text", "title", "label", "placeholderText"],
    "mid": ["text", "title", "label", "placeholderText", "description", "tooltip",
            "subtext", "message", "toggleHint", "headerText"],
    "wide": ["text", "title", "label", "placeholderText", "description", "tooltip",
             "subtext", "message", "toggleHint", "headerText", "name", "header",
             "caption", "hint", "summary", "subtitle", "buttonText", "actionText",
             "errorText", "statusText", "heading", "detail"],
}
QML_SHIPPED = ("mid", "prose")

QML_GATES = {
    # strictest: prose and at least two words, so a one-word label drops out
    "multiword": lambda s: is_prose(s) and len(RE_LETTERS.findall(s)) >= 2,
    "prose": is_prose,
    # loosest: anything containing a word, so identifiers and glyph names enter
    "letters": lambda s: bool(RE_LETTERS.search(s)),
}


PREDICATES = {
    "bash-plain": (
        'a double-quoted literal in an argument window of ' + OUT_CMD.replace("(?:", "(") +
        ' or after ' + OUT_FLAG.replace("(?:", "(") + ', in ' + "/ ".join(BASH_ROOTS) +
        '/, passing is_prose(), not already $"…"-marked, and containing no $ or backtick'),
    "bash-interpolating": (
        "the same window and gate as bash-plain, but the literal does contain a $ or "
        'backtick, so $"…" cannot hold it and it needs a printf rewrite first'),
    "bash-heredoc-block": (
        "one entry per heredoc body containing at least one is_prose() line, counted "
        "as a block because the body cannot be marked literal-by-literal"),
    "bash-metadata": (
        "every `# omarchy:summary=` value in " + "/ ".join(BASH_ROOTS) + "/, ungated: "
        "the router prints it, there is exactly one per file, and it is prose by schema"),
    "qml": (
        "a display property from QML_PROPS bound to a bare double-quoted literal under "
        "shell/, gated by QML_GATES; reported as a 3x3 grid, shipped figure is "
        + " x ".join(QML_SHIPPED)),
    "menu-data": (
        'every `"label"` value in default/omarchy/omarchy-menu.jsonc, ungated. Counts '
        "product and app names deliberately left in English, so read it as an upper "
        "bound on the work rather than a translation target"),
    "keybind-data": (
        "the second argument of o.bind / o.bind_toggle in default/hypr/bindings/*.lua "
        "when it is a plain double-quoted literal, ungated"),
}

# Counted and named rather than silently dropped. A census that hides its
# exclusions is a census whose total cannot be argued with.
EXCLUDED_NOTES = {
    "menu-title": (
        'the `"title"` values in omarchy-menu.jsonc, which the label-only menu-data '
        "predicate omits. They are user-facing (\"Default Browser\", \"Remove\", "
        '"Reset to default"), so menu-data understates by this much'),
    "bash-metadata-args": (
        "`# omarchy:args=` values. Usage syntax rather than sentences -- <app-name>, "
        "[application-args...], <chrome|brave|edge> -- so 3 of them pass is_prose(). "
        "The metavariable names are English, so a maximal localization would touch them"),
}


def walk(root, subdirs, suffixes=None):
    for sub in subdirs:
        base = os.path.join(root, sub)
        for dirpath, _, names in os.walk(base):
            for n in sorted(names):
                p = os.path.join(dirpath, n)
                rel = os.path.relpath(p, root)
                if rel.startswith(EXCLUDE_PATHS):
                    continue
                if suffixes and not n.endswith(suffixes):
                    continue
                yield rel, p


def heredoc_blocks(lines):
    """Return (opener_line_index, prose_line_count) for every heredoc body."""
    out, i, n = [], 0, len(lines)
    while i < n:
        m = RE_HEREDOC.search(lines[i])
        if m:
            term, start, j = m.group(1), i, i + 1
            prose = 0
            while j < n and lines[j].strip() != term:
                if is_prose(lines[j]):
                    prose += 1
                j += 1
            if prose:
                out.append((start, prose))
            i = j + 1
        else:
            i += 1
    return out


# Cases that pin the prose test in both directions. A census whose predicate
# drifts is worse than no census: two earlier surveys of this tree disagreed by
# 2.6x because neither pinned it. These 17 cases pin is_prose() and nothing
# else -- the stratum counts are pinned separately in PINNED.
SELFTEST = [
    (True, "Close"),
    (True, "BRIGHTNESS"),
    (True, "DHCP"),
    (True, "Public key> "),
    (True, "Route collision: $collision"),
    (True, r"\e[32m\nUpdate Arch signing keys\e[0m"),
    (True, r"\nPreinstalls are still marked as removed."),
    (False, ""),
    (False, "keyboard-us"),
    (False, "100%"),
    (False, "W"),
    (False, "${COMMAND_ROUTE[$key]}"),
    (False, "[--inline] [--pick]"),
    (False, r"\e]PBe0af68"),
    (False, "\U000f0140"),
    (False, "/usr/share/omarchy"),
    (False, "Panel.qml"),
]

# (sites, unique, files) at PINNED_SHA. Pinning the counts is what makes the
# predicates falsifiable: change one and this table says so.
PINNED = {
    "bash-plain": (1204, 1085, 395),
    "bash-interpolating": (395, 360, 155),
    "bash-heredoc-block": (96, 89, 75),
    "bash-metadata": (458, 458, 458),
    "qml": (75, 73, 21),
    "menu-data": (340, 230, 1),
    "keybind-data": (186, 173, 6),
}
PINNED_EXCLUDED = {
    "menu-title": (16, 7, 1),
    "bash-metadata-args": (184, 163, 184),
}
# Every cell of the qml grid, so the range in the row above is inspectable.
PINNED_QML_GRID = {
    ("core", "multiword"): (41, 40, 15),
    ("core", "prose"): (73, 71, 19),
    ("core", "letters"): (79, 76, 21),
    ("mid", "multiword"): (43, 42, 17),
    ("mid", "prose"): (75, 73, 21),
    ("mid", "letters"): (81, 78, 23),
    ("wide", "multiword"): (44, 43, 18),
    ("wide", "prose"): (78, 75, 24),
    ("wide", "letters"): (84, 80, 26),
}
# Variant counted alongside keybind-data so the choice of family is visible.
PINNED_KEYBIND_SOLO = (180, 167, 6)


def selftest():
    bad = [(want, s) for want, s in SELFTEST if is_prose(s) is not want]
    for want, s in bad:
        print(f"  FAIL expected {'prose' if want else 'not prose'}: {s!r}")
    print(f"is_prose selftest: {len(SELFTEST) - len(bad)}/{len(SELFTEST)} passed")
    return not bad


class Tally:
    def __init__(self):
        self.sites = defaultdict(int)
        self.uniq = defaultdict(set)
        self.files = defaultdict(set)
        self.samples = defaultdict(list)

    def add(self, stratum, rel, text):
        self.sites[stratum] += 1
        self.uniq[stratum].add(text)
        self.files[stratum].add(rel)
        if len(self.samples[stratum]) < 3:
            self.samples[stratum].append(f"{rel}: {text[:72]}")

    def triple(self, stratum):
        return (self.sites[stratum], len(self.uniq[stratum]), len(self.files[stratum]))


def collect_bash(root, t):
    for rel, path in walk(root, BASH_ROOTS):
        try:
            src = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if "\0" in src[:1024]:
            continue
        lines = src.splitlines()
        marked = set(RE_MARKED.findall(src))

        for start, prose in heredoc_blocks(lines):
            t.add("bash-heredoc-block", rel, f"{prose} prose lines at :{start + 1}")

        for line in lines:
            stripped = line.strip()
            m = RE_META_SUMMARY.match(stripped)
            if m:
                t.add("bash-metadata", rel, m.group(1))
                continue
            m = RE_META_ARGS.match(stripped)
            if m:
                t.add("bash-metadata-args", rel, m.group(1))
                continue
            if stripped.startswith("#"):
                continue
            lits = []
            # finditer, not findall: the window pattern carries a capture group, and
            # findall would hand back that group instead of the whole window.
            for m in RE_OUT_WINDOW.finditer(line):
                lits += RE_LITERAL.findall(m.group(0))
            lits += RE_FLAG_WINDOW.findall(line)
            for lit in lits:
                if not is_prose(lit) or lit in marked:
                    continue
                if RE_INTERP.search(lit):
                    t.add("bash-interpolating", rel, lit)
                else:
                    t.add("bash-plain", rel, lit)


def collect_qml(root):
    """Return the whole grid plus the shipped cell's hits.

    grid is {(propset, gate): (sites, unique, files)}; shipped is the list of
    (relpath, literal) for QML_SHIPPED, so the caller can fold the real strings
    into the tally and the cross-stratum unique union stays honest.
    """
    files = list(walk(root, ("shell",), (".qml",)))
    srcs = [(rel, open(p, encoding="utf-8", errors="replace").read()) for rel, p in files]
    grid, shipped = {}, []
    for pname, props in QML_PROPS.items():
        rx = re.compile(r"\b(" + "|".join(props) + r")\s*:\s*" + STR)
        hits = [(rel, lit) for rel, src in srcs for _prop, lit in rx.findall(src)]
        for gname, gate in QML_GATES.items():
            keep = [(rel, lit) for rel, lit in hits if gate(lit)]
            grid[(pname, gname)] = (len(keep), len({l for _r, l in keep}),
                                    len({r for r, _l in keep}))
            if (pname, gname) == QML_SHIPPED:
                shipped = keep
    return grid, shipped


def collect_schema(root, t):
    menu = os.path.join(root, "default/omarchy/omarchy-menu.jsonc")
    if os.path.exists(menu):
        rel = "default/omarchy/omarchy-menu.jsonc"
        text = open(menu, encoding="utf-8").read()
        for lit in RE_MENU_LABEL.findall(text):
            t.add("menu-data", rel, lit)
        for lit in RE_MENU_TITLE.findall(text):
            t.add("menu-title", rel, lit)

    solo_sites, solo_uniq, solo_files = 0, set(), set()
    for rel, path in walk(root, ("default/hypr/bindings",), (".lua",)):
        src = open(path, encoding="utf-8", errors="replace").read()
        for lit in RE_KEYBIND_FAMILY.findall(src):
            t.add("keybind-data", rel, lit)
        solo = RE_KEYBIND_SOLO.findall(src)
        if solo:
            solo_sites += len(solo)
            solo_uniq |= set(solo)
            solo_files.add(rel)
    return (solo_sites, len(solo_uniq), len(solo_files))


def fmt(triple):
    s, u, f = triple
    return f"{s:6d}  {u:6d}  {f:5d}"


def drift(label, got, want):
    if got == want:
        return None
    return f"  DRIFT {label}: got {got}, pinned {want}"


def print_predicates():
    print("PREDICATES -- what each stratum counts, and therefore what its number means")
    print()
    for k in list(SIFT_STRATA) + list(SCHEMA_STRATA):
        kind = "sift  " if k in SIFT_STRATA else "schema"
        print(f"{k}  [{kind}]")
        for line in wrap(PREDICATES[k], 74):
            print(f"    {line}")
        print()
    print("EXCLUDED -- counted and named, not dropped")
    print()
    for k, note in EXCLUDED_NOTES.items():
        print(f"{k}")
        for line in wrap(note, 74):
            print(f"    {line}")
        print()


def wrap(text, width):
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def main():
    argv = sys.argv[1:]
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]

    if "--predicates" in flags:
        print_predicates()
        return

    if not selftest():
        sys.exit(2)

    root = args[0] if args else "."
    t = Tally()
    collect_bash(root, t)
    keybind_solo = collect_schema(root, t)
    qml_grid, qml_shipped = collect_qml(root)
    for rel, lit in qml_shipped:
        t.add("qml", rel, lit)

    order = list(SIFT_STRATA[:3]) + ["bash-metadata", "qml", "menu-data", "keybind-data"]
    note = {
        "bash-plain": 'markable with $"…" as-is',
        "bash-interpolating": 'needs printf rewrite first (no $var inside $"…")',
        "bash-heredoc-block": 'unreachable by $"…" -- rewrite or externalise',
        "bash-metadata": "data read from disk, needs its own mechanism",
        "qml": f"display property bound to a bare literal ({' x '.join(QML_SHIPPED)})",
        "menu-data": "already localizable by construction",
        "keybind-data": "BLOCKED: description is also the join key (schema change)",
    }
    w = max(len(k) for k in order)

    print(f"tree: {root}")
    print(f"pinned to omacom/omarchy {PINNED_SHA[:8]}"
          + ("  [--no-pin: counts not verified]" if "--no-pin" in flags else ""))
    print()
    print(f"{'stratum'.ljust(w)}   sites  unique  files  kind    mechanism")
    print("-" * (w + 76))
    for k in order:
        kind = "sift" if k in SIFT_STRATA else "schema"
        print(f"{k.ljust(w)}  {fmt(t.triple(k))}  {kind:6s}  {note[k]}")
    print("-" * (w + 76))

    work = [k for k in order if not k.endswith("-data")]
    data = [k for k in order if k.endswith("-data")]
    # union, not sum: a string appearing in two strata is one catalog entry.
    print(f"{'BACKLOG (needs marking)'.ljust(w)}  {sum(t.sites[k] for k in work):6d}  "
          f"{len(set().union(*(t.uniq[k] for k in work))):6d}")
    print(f"{'ALREADY DATA'.ljust(w)}  {sum(t.sites[k] for k in data):6d}  "
          f"{len(set().union(*(t.uniq[k] for k in data))):6d}")
    print()

    print("qml sensitivity grid -- the row above is one cell of this")
    print(f"  {'propset x gate':22s}  sites  unique  files")
    for pname in QML_PROPS:
        for gname in QML_GATES:
            cell = qml_grid[(pname, gname)]
            mark = "  <== shipped" if (pname, gname) == QML_SHIPPED else ""
            print(f"  {pname + ' x ' + gname:22s} {fmt(cell)}{mark}")
    print()

    print("counted separately, not dropped")
    for k in EXCLUDED_NOTES:
        print(f"  {k.ljust(w)}  {fmt(t.triple(k))}")
    print(f"  {'keybind o.bind alone'.ljust(w)}  {fmt(keybind_solo)}"
          "   (vs the bind+bind_toggle family above)")
    print()

    problems = []
    for k in order:
        problems.append(drift(k, t.triple(k), PINNED[k]))
    for k, want in PINNED_EXCLUDED.items():
        problems.append(drift(k, t.triple(k), want))
    for key, want in PINNED_QML_GRID.items():
        problems.append(drift("qml " + " x ".join(key), qml_grid[key], want))
    problems.append(drift("keybind o.bind alone", keybind_solo, PINNED_KEYBIND_SOLO))
    problems = [p for p in problems if p]

    if "--no-pin" in flags:
        print(f"pin check skipped; {len(problems)} figure(s) differ from {PINNED_SHA[:8]}")
    elif problems:
        print(f"PIN CHECK FAILED -- {len(problems)} figure(s) drifted:")
        for p in problems:
            print(p)
        print("  Either the tree is not " + PINNED_SHA[:8]
              + " (use --no-pin) or a predicate changed.")
    else:
        print(f"pin check: all {len(PINNED) + len(PINNED_EXCLUDED) + len(PINNED_QML_GRID) + 1}"
              f" figures match {PINNED_SHA[:8]}")

    if "--samples" in flags:
        print()
        for k in order:
            for s in t.samples[k]:
                print(f"  [{k}] {s}")

    if problems and "--no-pin" not in flags:
        sys.exit(3)


main()
