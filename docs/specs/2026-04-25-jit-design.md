# JustInTime — Design Spec

**Date** : 2026-04-25
**Auteur** : Claralicious_ + Claude
**Statut** : Spec validé, prêt pour writing-plans

---

## 1. Vue d'ensemble

JustInTime est un addon WoW Retail (Midnight, 12.0) qui aide à décider en cours de Mythic+ s'il vaut la peine de continuer ou s'il faut reset la clé. Il compare la run en cours à une **référence** (P10 des runs publiques timées au même donjon × niveau × affixes, ou tes runs perso) et affiche en continu un delta avance/retard.

Le système repose sur deux artefacts :
- un **fichier plat de référence** `Data.lua` généré périodiquement par un script Python à partir de l'API Raider.IO,
- un **SavedVariables** local `JustInTimeDB` qui stocke tes runs perso en live-record et tes préférences.

L'addon offre deux modes complémentaires : un **chat printer** texte (à chaque boss kill et fin de clé) et un **overlay graphique** (barre de progression colorée selon le delta).

---

## 2. Buts / non-buts

### Buts (v1)

- Afficher en temps réel ton delta vs une référence stable (P10 des 10% pire runs timées).
- Permettre la comparaison à tes propres runs (plus rapide / plus récente / médiane).
- Anchor le feedback aux boss kills, avec interpolation continue entre.
- Survivre à un `/reload` mid-key (snapshot après chaque boss).
- Branding visuel cohérent avec la palette Claralicious_ (rouge → violet, footer tricolore).

### Non-buts (v1)

- Fallback Raider.IO côté perso (= récupérer ton historique rio). Perso = live-record only.
- Tracking trash % entre les bosses (`SCENARIO_CRITERIA_UPDATE`).
- Multi-langues au-delà de FR + EN.
- Configurations par-personnage (un seul pool per-account).
- Sharing / export de runs vers un format public.
- Synchronisation cloud / cross-account.

---

## 3. Architecture & data flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Script Python (privé, branche main, jamais publié sur master)  │
│  scripts/jit_update/  →  fetch Raider.IO  →  écrit Data.lua     │
└────────────────────────────┬────────────────────────────────────┘
                             │ commit + ship via master
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  addon/JustInTime/Data.lua  (référence publique uniquement)     │
└────────────────────────────┬────────────────────────────────────┘
                             │ chargé au login
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Addon runtime                                                  │
│                                                                 │
│  EventTracker  ──►  State  ◄──  SavedVariables JustInTimeDB    │
│        │               │          (runs perso, configs, snap)  │
│        └───────────────┼─────────────────────────────────┐     │
│                        ▼                                 │     │
│                  PaceEngine ◄── Data.lua / Personal      │     │
│                        │    selon mode actif             │     │
│                        ▼                                 │     │
│              ┌─────────┴─────────┐                       │     │
│              ▼                   ▼                       │     │
│         Overlay (CD-1)      ChatPrinter                  │     │
│              │                   │                       │     │
│              └────────── critical alerts (visuel/chat/son)─────┘
└─────────────────────────────────────────────────────────────────┘
```

Trois flux distincts :
1. **Build-time** (Python) — populate `Data.lua` avec la référence publique. Manuel ou via cron / CI privée.
2. **Runtime ingest** (addon) — capture des runs live dans SavedVariables au fil des clés.
3. **Runtime render** (addon) — pace engine compare l'elapsed vs référence interpolée, met à jour overlay et chat.

---

## 4. Data layer

### 4.1 `addon/JustInTime/Data.lua` (généré, public)

```lua
JustInTimeData = {
  meta = {
    generated_at = "2026-04-25T14:30:00Z",
    season       = "season-mn-1",
    schema_version = 1,
  },
  affix_id_to_slug = {
    [9]   = "tyrannical",
    [10]  = "fortified",
    [147] = "xalataths-guile",
    -- ...
  },
  dungeons = {
    ["algethar-academy"] = {
      short_name        = "AA",
      challenge_mode_id = 402,
      timer_ms          = 1800999,
      num_bosses        = 4,
      bosses = {
        { ordinal = 1, slug = "overgrown-ancient",   name = "Overgrown Ancient",   wow_encounter_id = 2563 },
        { ordinal = 2, slug = "...",                 name = "...",                 wow_encounter_id = ... },
        { ordinal = 3, slug = "...",                 name = "...",                 wow_encounter_id = ... },
        { ordinal = 4, slug = "...",                 name = "...",                 wow_encounter_id = ... },
      },
      levels = {
        [12] = {
          ["fortified-xalataths-guile"] = {
            sample_size    = 23,
            clear_time_ms  = 1742000,
            boss_splits_ms = { 280000, 740000, 1200000, 1742000 },
          },
          ["tyrannical-xalataths-guile"] = { ... },
        },
        -- niveaux 2..20
      },
    },
    -- 8 donjons MN1 : algethar-academy, magisters-terrace, maisara-caverns,
    -- nexuspoint-xenas, pit-of-saron, seat-of-the-triumvirate, skyreach,
    -- windrunner-spire
  },
}
```

**Convention combo affixes** : slugs triés alphabétiquement, joints par `-`. Stable et déterministe (`fortified-xalataths-guile`, `tyrannical-xalataths-guile`).

**Lookup** : `JustInTimeData.dungeons[slug].levels[lvl][affix_combo]` → struct avec `boss_splits_ms` et `clear_time_ms`.

### 4.2 SavedVariables `JustInTimeDB` (local, par-compte)

Déclaré dans le `.toc` via `## SavedVariables: JustInTimeDB`.

```lua
JustInTimeDB = {
  schema_version = 1,

  config = {
    reference_mode    = "public",     -- public | perso_fastest | perso_recent | perso_median
    ignore_affixes    = false,
    overlay_visibility = "always",    -- always | popup
    overlay_position  = { x = 0, y = 0, locked = false },

    triggers = {
      chat_boss_kill        = true,
      chat_key_end          = true,
      chat_threshold_cross  = false,
    },

    critical_alerts = {
      visual = true,
      chat   = true,
      sound  = false,
    },
  },

  runs = {
    {
      run_id          = "1745700412-AA-12",
      completed_at    = "2026-04-24T20:30:12Z",
      dungeon_slug    = "algethar-academy",
      level           = 12,
      affix_combo     = "fortified-xalataths-guile",
      timer_ms        = 1800999,
      clear_time_ms   = 1798500,
      timed           = true,
      depleted        = false,
      boss_splits_ms  = { 280000, 720000, 1180000, 1798500 },
      character       = { name = "Tartabis", realm = "Hyjal", class = "druid" },
    },
    -- N entries
  },

  active_session = nil,
  -- when active: { dungeon_slug, level, affix_combo, started_epoch,
  --                boss_kills = { [n] = relative_ms, ... }, snapshot_at_epoch }
}
```

### 4.3 Lookup logique au runtime

```
au CHALLENGE_MODE_START :
  resolve (dungeon_slug, level, affix_combo) depuis l'API WoW
  init active_session

au ENCOUNTER_END (success en M+) :
  active_session.boss_kills[ordinal] = (now - started_epoch) * 1000
  persist snapshot dans SavedVariables
  fire ChatPrinter trigger A
  recompute pace

à chaque tick (10 Hz) :
  ref = resolveRef()
  delta = elapsed_ms − interp_ref(elapsed_ms, ref.boss_splits_ms)
  ETA   = elapsed_ms + (ref.clear_time_ms − interp_ref(elapsed_ms, ...))
  overlay.update(delta, ETA, progress)
  if delta crosses critical threshold → fire critical alerts (selon config)

resolveRef() :
  si config.reference_mode == "public" :
    primary = JustInTimeData.dungeons[d].levels[l][affix_combo]
    si primary == nil et config.ignore_affixes :
      fallback = JustInTimeData.dungeons[d].levels[l][autre_combo]
    return primary or fallback or nil  (nil → état "réf indispo")
  sinon (perso) :
    pool = filter(JustInTimeDB.runs, dungeon=d, level=l)
    si config.ignore_affixes off, filter aussi par affix_combo
    si pool vide → fallback public + chat info
    selon reference_mode :
      perso_fastest = run avec min(clear_time_ms)
      perso_recent  = run avec max(completed_at)
      perso_median  = construire splits médians par boss à partir du pool
    return { boss_splits_ms = ..., clear_time_ms = ... }
```

### 4.4 Modèle de pace

Soit `ref_splits = { T_1, T_2, ..., T_K }` les timestamps relatifs (en ms) auxquels la référence a tué les bosses 1..K, avec `T_K = clear_time_ms`. Soit `your_split[n]` ton elapsed au moment où tu as tué le boss n, et `t` l'elapsed courant.

#### Anchors aux boss kills

À chaque `ENCOUNTER_END` du boss `n` :

```
your_split[n]       = t                    (elapsed au moment du kill)
delta_at_anchor[n]  = your_split[n] − T_n  (signed ms ; >0 retard, <0 avance)
pace_ratio[n]       = your_split[n] / T_n  (>1 retard, <1 avance)
```

#### Delta continu entre kills

Soit `n` le dernier boss tué (`n = 0` avant le premier kill, `delta_at_anchor[0] = 0`).

```
si t ≤ T_{n+1} :
    delta_continuous(t) = delta_at_anchor[n]
    # tu es encore "dans la fenêtre" où la référence n'a pas non plus
    # tué le prochain boss → delta gelé à l'anchor
sinon (t > T_{n+1}) :
    delta_continuous(t) = delta_at_anchor[n] + (t − T_{n+1})
    # la référence aurait dû tuer le prochain boss à T_{n+1} ;
    # chaque seconde au-delà ajoute au delta
```

Quand tu tues finalement boss `n+1`, un nouvel anchor s'établit (qui peut absorber ou aggraver l'accumulation), et le cycle reprend.

#### Projection ETA

```
projected_finish(t) = T_K × max( pace_ratio[n], t / T_{n+1} )
                      où n = dernier boss tué, et T_{n+1} = T_K si n == K

ETA = projected_finish(t)
deplete_projected = projected_finish(t) > timer_ms
```

Cette formulation garantit :
- continuité (pas de saut entre kills, drift linéaire après dépassement de `T_{n+1}`),
- conservatisme (le delta ne peut que s'aggraver entre deux kills, jamais s'améliorer artificiellement),
- réactivité (au moment du kill, l'anchor met à jour le delta avec la valeur exacte).

---

## 5. Script Python

### 5.1 Structure projet

```
scripts/
├── pyproject.toml          # uv-managed, Python ≥ 3.11, mypy strict, pytest
├── jit_config.toml         # config user (levels, sample threshold, output path)
├── jit_update/
│   ├── __init__.py
│   ├── cli.py              # entry-point: `uv run jit-update`
│   ├── config.py           # parse jit_config.toml
│   ├── raiderio.py         # HTTP client + rate limiter + cache
│   ├── pipeline.py         # orchestration : fetch → sample → aggregate → render
│   ├── lua_renderer.py     # Python dict → Lua déclaratif (string templating)
│   └── models.py           # Pydantic : Run, RunDetails, Encounter, ReferenceCell
├── tests/
│   ├── fixtures/           # responses Raider.IO captures (json)
│   ├── test_pipeline.py
│   ├── test_lua_renderer.py
│   ├── test_raiderio.py    # avec httpx.MockTransport
│   └── test_cli.py
└── README.md               # instructions de génération
```

### 5.2 Dépendances

- `httpx` — client HTTP sync, rate-limit aware
- `pydantic` v2 — validation des réponses API
- `tomli` (stdlib `tomllib` ≥ 3.11) — parsing config
- `click` ou `typer` — CLI
- `rich` — output console pretty (optionnel)
- `pytest`, `pytest-mock`, `pytest-cov`, `mypy`, `ruff`, `black` — dev

### 5.3 Pipeline

```
1. Lire jit_config.toml :
   - season slug (default season-mn-1)
   - levels = [2..20]
   - sample_threshold = 20    (min runs timées par cellule)
   - slowest_percentile = 10  (% des plus lents pour aggregate)
   - output_path = "../addon/JustInTime/Data.lua"

2. Fetch static-data → liste des donjons + affix mapping

3. Pour chaque (dungeon, level, affix_combo) :
   a. Paginer /mythic-plus/runs?season=...&dungeon=...&affixes=all
      Filter côté client par mythic_level == level et weekly_modifiers == affix_combo
      Continuer jusqu'à ≥20 runs timées (num_chests >= 1) ou max_pages
   b. Trier par clear_time_ms desc → garder les 10% les plus lents (≥ 2 runs)
   c. Pour chaque run du sample : fetch /run-details?id=keystone_run_id
   d. Extraire encounters[].approximate_relative_ended_at par ordinal
   e. Calculer médiane par boss → boss_splits_ms[]
   f. Calculer médiane des clear_time_ms → clear_time_ms

4. Render Data.lua :
   - meta.generated_at (UTC ISO)
   - meta.season + schema_version
   - affix_id_to_slug
   - dungeons[].bosses[] et levels[].affixes[]
   - écrire dans output_path

5. Print summary : nb cellules remplies / vides, durée totale, requêtes faites
```

### 5.4 Robustesse

- **Rate limiter** : 300 req/min par défaut (configurable, sous quota 1000/min Raider.IO).
- **Cache HTTP local** : `.cache/raiderio/` keyed by URL hash, TTL 1h. Permet `--dry-run` ou re-run rapide.
- **Retry** : 3 tentatives avec backoff exponentiel (1s, 2s, 4s) sur 5xx ou timeout.
- **Sample insuffisant** : si <20 timed runs trouvés pour une cellule, log warning et **omettre** la cellule de Data.lua. L'addon fera fallback runtime.

### 5.5 CLI

```bash
uv run jit-update                          # full pipeline, écrit Data.lua
uv run jit-update --dry-run                # affiche stats sans écrire
uv run jit-update --season season-mn-1     # override
uv run jit-update --out path/to/Data.lua   # override output
uv run jit-update --only algethar-academy  # un donjon (debug)
uv run jit-update --no-cache               # bypass cache HTTP
```

### 5.6 Tests (CLAUDE.md global ≥70% coverage)

- `test_lua_renderer.py` — golden files : `dict in → Lua string out` byte-équivalent
- `test_pipeline.py` — fixtures JSON capturées depuis l'API ; sample selection, P10, structure
- `test_raiderio.py` — `httpx.MockTransport` ; rate limiter, retry, cache hit/miss
- `test_models.py` — Pydantic round-trip
- `test_cli.py` — `CliRunner` / `typer.testing` ; smoke `--dry-run` et `--out`

---

## 6. Composants Lua de l'addon

### 6.1 Structure de fichiers

```
addon/JustInTime/
├── JustInTime.toc        # ordre de chargement strict
├── Locales.lua           # FR + EN
├── Data.lua              # généré par Python (déclaratif, pas de logique)
├── Config.lua            # SavedVariables defaults + Settings panel
├── State.lua             # session active + persistance JustInTimeDB
├── PaceEngine.lua        # interp ref, delta, ETA, projection
├── EventTracker.lua      # CHALLENGE_MODE_*, ENCOUNTER_END → mutations State
├── ChatPrinter.lua       # triggers (boss kill / threshold / end)
├── Overlay.lua           # CD-1 : barre gradient + pips + delta + ETA
└── Core.lua              # bootstrap, slash commands, dispatch
```

### 6.2 `.toc` (ordre de chargement)

```
## Interface: 120001
## Title: JustInTime
## Notes: Lightweight raid timing helper for WoW Retail
## Author: Claralicious_
## Version: 0.1.0
## SavedVariables: JustInTimeDB

Locales.lua
Data.lua
Config.lua
State.lua
PaceEngine.lua
EventTracker.lua
ChatPrinter.lua
Overlay.lua
Core.lua
```

### 6.3 Events WoW

| Event | Module | Rôle |
|---|---|---|
| `ADDON_LOADED` | Core | init SavedVariables, BuildPanel |
| `PLAYER_LOGIN` | Core | restauration `active_session` si `C_ChallengeMode.IsChallengeModeActive()` |
| `CHALLENGE_MODE_START` | EventTracker | nouvelle session : resolve `(slug, combo)` |
| `ENCOUNTER_END` | EventTracker | record boss split, persist snapshot, fire trigger A, recompute |
| `CHALLENGE_MODE_COMPLETED` | EventTracker | finalise run, archive `runs[]`, fire trigger C, clear `active_session` |
| `CHALLENGE_MODE_RESET` | EventTracker | abandon → clear `active_session` (jeté) |
| `PLAYER_LOGOUT` | State | flush final snapshot |

### 6.4 PaceEngine API

```lua
PaceEngine.GetReferenceForActive() → { boss_splits_ms, clear_time_ms, source_label }
PaceEngine.ComputeDelta(elapsed_ms, your_splits, ref) → ms (signed)
PaceEngine.ProjectFinish(elapsed_ms, your_splits, ref) → ms
PaceEngine.IsDepleteProjected(elapsed_ms, your_splits, ref, timer_ms) → bool
PaceEngine.ResolveAffixCombo(affix_ids[]) → string slug
PaceEngine.MapIdToSlug(map_id) → string slug or nil
```

### 6.5 Slash commands

```
/jit                                       → ouvre Settings panel
/jit help                                  → liste les commandes
/jit show / /jit hide                      → overlay visibility runtime
/jit lock / /jit unlock                    → overlay drag
/jit mode <public|fastest|recent|median>   → switch reference mode
/jit reset                                 → vide JustInTimeDB.runs (avec confirmation)
```

Les slash commands sont des **facilitateurs in-game**. Le panel Settings (`/jit`) reste la source canonique pour configurer les triggers chat (3 cases), les alertes critiques (3 cases), et `ignore_affixes` qui n'a pas de slash dédié.

### 6.6 Settings panel (Config.lua)

```
┌─ JustInTime ──────────────────────────────────────────────┐
│  ── Référence ──                                          │
│  Mode :  ( ) Publique (P10 worst-timed)                   │
│          ( ) Mes runs : la plus rapide                    │
│          ( ) Mes runs : la plus récente                   │
│          ( ) Mes runs : médiane                           │
│  [x] Ignorer les affixes (élargir le sample)              │
│                                                           │
│  ── Overlay graphique ──                                  │
│  Visibilité :  ( ) Toujours visible                       │
│                ( ) Popup transitoire (6s post-boss kill)  │
│  [x] Verrouiller la position                              │
│  [Bouton: Réinitialiser la position]                      │
│                                                           │
│  ── Mode texte (chat) ──                                  │
│  [x] Print à chaque boss kill                             │
│  [x] Récap en fin de clé                                  │
│  [ ] Alerte au passage de seuil (vert ↔ rouge)            │
│                                                           │
│  ── Alerte "tu vas déplate" ──                            │
│  [x] Visuel (pulsation rouge)                             │
│  [x] Chat warning                                         │
│  [ ] Son d'alerte                                         │
│                                                           │
│  ── Données ──                                            │
│  Référence générée le : 2026-04-25 (il y a 0 jours) ✓     │
│  [Bouton: Effacer mes runs (confirmation)]                │
│                                                           │
│  By Claralicious_                                         │
└───────────────────────────────────────────────────────────┘
```

---

## 7. UI/UX polish

### 7.1 Overlay CD-1 (layout final)

- frame ancrée par défaut sous le tracker M+ Blizzard (TopRight, offset (-180, -200))
- draggable si `cfg.overlay_position.locked == false`
- `OnUpdate` à 10 Hz, désactivé hors `IsChallengeModeActive()`
- éléments : brand title gradient + delta numérique coloré + barre gradient progression + 4 pips bosses (variable selon donjon) + rows écoulé/last split/réf

### 7.2 Mapping couleur barre

`delta_normalized = clamp(delta_ms / timer_ms, -0.10, +0.10)`

| delta_norm | couleur (hex) | sémantique |
|---|---|---|
| ≤ −0.05 | `#30c864` vert vif | confortable |
| −0.025 | `#7ed87a` vert pâle | léger |
| 0 | `#c8a0ff` violet pâle (brand) | neutre |
| +0.025 | `#d878a0` violet rosé | léger retard |
| +0.05 | `#ff5050` rouge | retard significatif |
| ≥ +0.10 | `#ff5050` pulsation | déplate imminent |

Interpolation HSL entre les ancres (smooth).

### 7.3 Comportement temporel

- **Avant boss 1 tué** : barre gris clair, pas de delta affiché.
- **Au premier ENCOUNTER_END** : computation initiale, couleur s'établit, ETA s'affiche.
- **Entre boss kills** : interpolation continue (cf. §4.4).
- **Au passage du seuil critique** (projection > timer) : alerte une seule fois selon `cfg.critical_alerts`. Barre passe en pulsation `#ff5050`.
- **Post-deplete** : barre rouge sombre pulsée, delta `+M:SS (DEPLETE)`. ETA continue jusqu'à fin.
- **Mode popup** : show + fade-in 0.3s à chaque ENCOUNTER_END, hold 6s, fade-out 0.5s. Position figée pendant ce temps.

### 7.4 Branding (cohérent Claralicious_)

- Tag chat `[JIT]` : crochets verts `#33ff99`, `J` rouge `#ff3333`, `IT` violet pâle `#c8a0ff`.
- Brand title : gradient per-letter rouge → violet pâle (`#ff4444 → #b860d0 → #c8a0ff`).
- Footer panel : `By Claralicious_` gradient bleu/blanc/rouge.
- Logo / icône addon : à designer en v2 (skip v1).

### 7.5 Localisation

`Locales.lua` étendu (~30-40 clés) : labels panel, formats chat triggers, options. FR par défaut, fallback EN si `GetLocale()` retourne `enUS`/`enGB`. Pas d'autre langue v1.

---

## 8. Edge cases & robustesse

| Scénario | Comportement |
|---|---|
| `Data.lua` absent | Print `[JIT] ⚠ Data.lua manquant — lance le script Python` ; overlay désactivé en mode public ; mode perso reste fonctionnel. |
| `Data.lua` âge > 14j | Warning au login `[JIT] ⚠ données vieilles de N jours, considère relancer le script` ; fonctionnement normal sinon. |
| Combo (donjon × level × affix) absent dans Data.lua | Si `ignore_affixes` off, fallback auto sur l'autre combo affixes ; sinon état "réf indispo" dans l'overlay. |
| Mode perso mais `runs` filtré donne 0 entry | Fallback automatique vers public + chat info `[JIT] pas encore de run perso ici, fallback sur public`. |
| `ENCOUNTER_END` raté | Boss split manquant ; suivants restent valides ; recap final affiche `?`. |
| Tag chat / affixe inconnu | Locales fallback sur la clé brute (`__index` de Locales) ; pas de crash. |
| Snapshot SavedVariables corrompu | Schema version check au load ; mismatch → reset des `runs` (pas de wipe `config`). |
| `/reload` mid-key | Snapshot après chaque ENCOUNTER_END ; au load, si `IsChallengeModeActive()`, restaurer `active_session`. |
| Run abandonnée (party disbands, leave group) | Clear `active_session`, jeté (pas archivé en partiel). |
| Deplete (timer expiré, run continue) | Tracking continue jusqu'à `CHALLENGE_MODE_COMPLETED` ; recap final montre "DEPLETE +M:SS". |

---

## 9. Tests

### 9.1 Python (pytest, ≥70% coverage)

- `test_lua_renderer.py` — golden files
- `test_pipeline.py` — fixtures JSON
- `test_raiderio.py` — `httpx.MockTransport`
- `test_models.py` — Pydantic round-trip
- `test_cli.py` — `CliRunner` smoke

### 9.2 Lua

- Pas de framework de test natif côté addon WoW.
- **Logique pure (PaceEngine)** exposée sur `NS.PaceEngine` ; scenarios reproductibles via `/jit test pace` (slash de debug, masquée hors debug mode).
- **Assertions au load** : valider la structure de `JustInTimeData` (fields obligatoires, types). Mismatch → log warning + désactiver overlay en mode public.
- Suite externe via [busted](https://lunarmodules.github.io/busted/) sur PaceEngine candidat v2.

---

## 10. Hypothèses à valider en implémentation

1. L'API Raider.IO `/mythic-plus/runs` permet la pagination jusqu'à des niveaux bas (+2..+8) avec sample suffisant. Sinon `ignore_affixes` couvre.
2. `ENCOUNTER_END` fire fiable en M+ pour les 4-5 bosses des 8 donjons MN1.
3. Mapping `affixID → slug` Raider.IO stable (à hardcoder dans `affix_id_to_slug` côté Data.lua).
4. `C_ChallengeMode.GetActiveKeystoneInfo()` retourne `affixIDs` au début de la run (pas avant).
5. Le filtrage par `mythic_level` est fait côté client (l'API ne supporte pas le filtre direct).
6. La pagination `/mythic-plus/runs` sort par score, donc pour trouver les "worst-timed" il faut paginer profond. Profondeur acceptable à valider.

---

## 11. Décisions log (Q1–Q12)

| # | Question | Décision |
|---|---|---|
| Q1 | Définition "pire timing" public | **B** — médiane des 10% les plus lentes timées (P10) |
| Q2 | "Mes runs" = quoi | **B + C + D** — fastest / récente / médiane (jamais worst) |
| Q3 | Source données perso | **C** initialement → **simplifié v1 : live-record only** (rio fallback en non-but v2) |
| Q4 | Filtrage affixes | **B** — auto par combo + toggle "ignorer affixes" |
| Q5 | Triggers chat | **a + c on, b opt-in, d non** (boss kill + key end par défaut) |
| Q6 | Moment critique "déplate" | **D** — visuel/chat/son toggleable indépendamment (defaults : visuel on, chat on, son off) |
| Q7 | Python packaging + sortie | **b + α** — pyproject.toml + uv, `Data.lua` Lua natif |
| Q8 | Architecture data files | `Data.lua` (public, shipped) + `JustInTimeDB` (perso, local SavedVariables) |
| Q9 | SavedVariables scope | **a** — per-account |
| Q10 | Edge cases mid-key | **c (hybride)** — snapshot par boss kill, abandon jeté, deplete continue tracking |
| Q11 | Niveaux trackés | **+2 à +20** explicite |
| Q12 | Wrap-up | localisation FR+EN ; staleness 14j ; interpolation continue |
| UI | Layout overlay | **CD-1** (barre progression gradient + pips + delta + ETA + last split + ref) avec toggle visibilité always/popup |

---

## 12. Glossaire

- **MN1 / Midnight S1** — Mythic+ Season 1 de l'expansion 12.0 World of Warcraft, slug `season-mn-1`.
- **Déplate** — argot M+ : run qui dépasse le timer du donjon, échoue à upgrade la clé.
- **P10** — 10ᵉ percentile (équivalent ici : médiane des 10% les plus lentes timées).
- **Affix combo** — paire d'affixes hebdomadaires qui modifient la difficulté (Fortified ou Tyrannical) + affixe saisonnier (Xal'atath's Guile).
- **Boss split** — timestamp relatif au début du donjon auquel un boss est mort.
- **Live-record** — enregistrement de tes runs en temps réel dans SavedVariables au moment où tu joues.

---

*Spec validé. Prochaine étape : `superpowers:writing-plans` pour produire `docs/specs/2026-04-25-jit-plan.md`.*
