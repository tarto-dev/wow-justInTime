# JustInTime — In-game smoke test procedure

After each meaningful Plan B change, verify in WoW.

## Setup

1. Symlink the addon into WoW:
   ```bash
   ln -s /home/tarto/projects/wowAddons/justInTime/addon/JustInTime ~/Games/wow/_retail_/Interface/AddOns/JustInTime
   ```
2. Launch WoW Retail (Midnight, Interface 120001).
3. At the character select / main screen, confirm JustInTime is enabled in `/AddOns`. The name should appear with the **flame gradient** (light orange → bright red across letters) and a **lightning bolt icon** to its left.

## Boot tests (no key required)

1. **Login boot**: log in. Expected: `[JIT] JustInTime chargé. /jit pour les options.` in chat — with "JustInTime" in flame colors.
2. **Schema validation**: if `Data.lua` is corrupt, expected: `[JIT] ⚠ Data.lua schéma invalide`. Otherwise nothing.
3. **Staleness**: if `Data.lua` is >14 days old, expected: `[JIT] ⚠ données vieilles de N jours`.
4. **Self-tests**: `/jit test` → expected: 5 PASS lines + summary `5/5 tests passent`.

## Settings panel

1. `/jit` → Settings panel opens. Title appears in flame gradient. AddOns list also shows "JustInTime" in flame.
2. Verify all sections present: **Référence** (4 radios + 1 checkbox), **Overlay graphique** (2 radios + 1 checkbox + 1 button), **Mode texte** (3 checkboxes), **Alerte critique** (3 checkboxes), **Données** (1 line + 1 button).
3. Toggle each checkbox/radio → `/reload` → verify state persists (SavedVariables OK).
4. `/jit show` → overlay appears (if in-key, or always-visible mode and key is active).
5. `/jit lock` then drag the overlay → it does not move. `/jit unlock` then drag → moves and persists.
6. Click "Réinitialiser la position" → overlay returns to TOPRIGHT default.

## In-key tests

1. Start a Mythic+ key (any of the 8 MN1 dungeons).
2. Verify overlay shows (in always mode) or appears at boss kill (in popup mode with fade-in).
3. Kill a boss → expected:
   - **Chat**: `[JIT] <BossName> tué — <delta> vs <ref>` (if `chat_boss_kill` enabled)
   - **Overlay** updates: delta numeric, bar color shifts toward green/violet/red, pip turns green.
4. Continue keying. If pace falls behind enough that ETA > timer:
   - **Chat**: `[JIT] ⚠ projection : déplate prévue à <ETA> (<over>)` (once)
   - **Overlay**: bar pulses red.
5. End the key (timed or depleted). Expected:
   - **Chat**: `[JIT] Run terminée <time> ✓ timée — <delta> vs <ref>` (or `Run dépletée`).
   - **Overlay** hides (always mode) or stays in popup state until next key.
6. Next key: reset behavior reproduces.

## /reload mid-key

1. Start a key, kill boss 1, kill boss 2.
2. `/reload` mid-run.
3. Expected: addon recovers active session; subsequent kills still append correctly to the same `JustInTimeDB.active_session.boss_kills`.

## Reset confirmation

1. `/jit reset` → confirmation popup with FR text "Effacer toutes tes runs perso ? (impossible à annuler)".
2. Click "Oui" → expected: `[JIT] Runs perso effacées (N entrées)`.
3. `/jit reset` again → "Non" → no change.

## Edge cases

- **Unknown dungeon** (Delve / non-keystone instance): no crash; ref resolves to nil; overlay shows elapsed but "réf indispo".
- **Key abandoned** (party leaves, leave instance): `CHALLENGE_MODE_RESET` → `active_session` cleared; overlay hides.
- **Deplete crossed mid-run**: overlay continues tracking; recap chat says "dépletée".
- **Mode switch during key**: `/jit mode fastest` → next overlay tick uses the new reference.

## Self-tests output (expected)

```
[JIT][debug] JustInTime self-tests
[JIT][debug] PASS: affix_combo_sort
[JIT][debug] PASS: pace_no_kills
[JIT][debug] PASS: pace_at_anchor
[JIT][debug] PASS: pace_drift_past_ref
[JIT][debug] PASS: sorted_ref_splits
[JIT][debug] 5/5 tests passent
```

## Done

If all sections pass with no errors in chat (other than the expected info/warning lines), Plan B is verified. Report any anomaly with the chat log + relevant `JustInTimeDB` snapshot.

## Branding checklist (visual)

- [ ] AddOns list: "JustInTime" name displays in flame gradient (orange → red across letters)
- [ ] AddOns list: yellow lightning bolt icon to the left of the addon name
- [ ] Chat at login: `[JIT] <flame-colored>JustInTime</flame> chargé. /jit pour les options.`
- [ ] Settings panel: title at top in flame gradient (huge font)
- [ ] Settings panel footer: "By Claralicious_" in bleu/blanc/rouge tricolor
- [ ] Overlay frame: small "JustInTime" title in flame gradient at top-left
- [ ] Chat tag: `[JIT]` with green brackets, J in red, IT in light violet
