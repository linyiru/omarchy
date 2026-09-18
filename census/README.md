# i18n census

Counts the user-facing English strings in the Omarchy tree, stratified by what it would cost to mark each kind. Written to support the argument in [omacom/omarchy#12345](https://github.com/omacom/omarchy/issues/12345), which committed to publishing it with each stratum's predicate before the figures are asked to carry a decision.

**This is not proposed for merge.** There is no pull request and there will not be one. It lives on a branch so that its lines can be cited and so that anyone can run it, not because it belongs in the product tree.

## Run it

```
git clone --branch i18n-census-audit https://github.com/linyiru/omarchy.git /tmp/census-audit
git clone https://github.com/omacom/omarchy.git /tmp/omarchy
git -C /tmp/omarchy archive 9c5482c5 | tar -x -C /tmp/pinned
python3 /tmp/census-audit/census/omarchy-i18n-census.py /tmp/pinned
```

Stdlib Python 3 only. Verified on 3.14.7.

Use `git archive` rather than a checkout: a census run against a dirty working tree is not a census of any revision.

```
--predicates   print what each stratum counts, and nothing else
--samples      show three example strings per stratum
--no-pin       run against a revision other than the pinned one
```

Exit status is 0 on success, 2 if the prose test fails one of its pinned cases, and 3 if any stratum count differs from the pinned figures. A non-zero 3 means either the tree is not `9c5482c5` or a predicate changed; the output says which figures moved.

## What is pinned

`PINNED_SHA` is `9c5482c58dbe4974de337450754885083c91eada` (omacom/omarchy, branch `quattro`, committed 2026-09-16). Two things are pinned against it:

- `SELFTEST`, 17 cases pinning `is_prose()` in both directions. These cover the prose heuristic and nothing else.
- `PINNED`, `PINNED_EXCLUDED`, `PINNED_QML_GRID` and `PINNED_KEYBIND_SOLO`, 19 `(sites, unique, files)` triples covering every figure the script prints.

Pinning the counts is what makes the predicates falsifiable. Editing a predicate without editing its pinned triple makes the script fail rather than quietly publish a different number under the same stratum name.

## Sift strata and schema strata

The distinction that organises the whole script, and the source of four of the five errors corrected since the first version:

A **sift** stratum is a pile of arbitrary string literals in code, only some of which reach a human, so the census has to guess which. `is_prose()` is that guess.

A **schema** stratum is a named field that is human-facing by construction: a menu label, a keybinding description, a `# omarchy:summary=` value. Every value counts. Applying a prose heuristic there does not add caution, it invents false negatives. `is_prose("Custom")` is a judgement call, but a menu label reading `Custom` is a catalog entry whatever the heuristic thinks of it.

## Known limits

- `sites` counts edits a marking sweep must make; `unique` counts entries a catalog would hold. They are different questions and the gap between them is the point of reporting both.
- `unique` totals are unions, not sums. 15 strings are both a menu label and a keybinding description, so summing the two strata double counts them.
- The qml stratum has no single defensible predicate, so all nine cells of a 3x3 grid are reported (property set x prose strictness) and the shipped cell is marked. The spread is 41 to 84 sites.
- Two populations are counted but held out of the totals, named in `EXCLUDED_NOTES` with the reason: the menu's `"title"` values, which are user-facing and which the label-only predicate omits, and `# omarchy:args=` values, which are usage syntax rather than sentences.
- The bash file set is `bin/`, `install/` and `migrations/`, excluding `test/` and `shell/plugins/dev-gallery/`. A different file set is a different number under the same name, so it is part of the predicate.
