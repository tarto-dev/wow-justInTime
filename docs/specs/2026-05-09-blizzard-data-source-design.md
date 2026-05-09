# JustInTime — Blizzard Data Source — Design Spec

**Date** : 2026-05-09
**Auteur** : Claralicious_ + Claude
**Statut** : Spec en relecture, prêt pour writing-plans après validation user
**Spec parent** : [2026-04-25-jit-design.md](2026-04-25-jit-design.md)

---

## 1. Vue d'ensemble

Étendre la couverture de niveaux de l'addon JustInTime de **+18 à +20** (état actuel) vers **+15 à +22**, en remplaçant la source de découverte des runs (Raider.IO `/mythic-plus/runs`) par la **Blizzard Battle.net Game Data API** (`mythic-keystone-leaderboard`). Raider.IO reste utilisé en source secondaire pour enrichir les boss splits où ils existent réellement, et pour la métadonnée statique (saison, donjons, bosses).

Le schéma `Data.lua` est simplifié au passage : la couche d'affixes (jusqu'ici `levels[L][affix_combo]`) est supprimée, l'addon ne s'en sert pas en pratique. Les boss splits indisponibles aux bas niveaux sont **synthétisés** à partir des ratios observés sur les niveaux où des splits réels existent.

---

## 2. Contexte et motivation

### Problème

Le pipeline Python actuel (`scripts/jit_update/`) utilise `https://raider.io/api/v1/mythic-plus/runs` qui :

- N'expose **aucun filtre par niveau** (testé : `level=`, `mythic_level=`, `min_level=`, `keystone_level=` rejetés en `400 "X is not allowed"` par le schéma Joi de Raider.IO).
- Trie globalement par score, donc les runs +15-19 sont enfouis derrière des milliers de runs +20+.
- Avec `max_pages_per_query = 50` (config actuelle), les niveaux +15-17 n'atteignent jamais `min_sample = 20`, et leurs cellules sont silencieusement skippées (cf. `pipeline.py:248`).

Résultat observé dans `addon/JustInTime/Data.lua` (commit du 2026-04-27) : seuls les niveaux **18, 19, 20** sont présents. L'utilisateur Curseforge qui pousse une +15 ou une +21 ne voit pas de référence.

### Pourquoi Blizzard

Spike effectué le 2026-05-07 (un appel `connected-realm/1080/mythic-leaderboard/402/period/1062` sur l'EU) a retourné **110 runs couvrant les niveaux +2 à +19** dans une seule réponse. La couverture des bas niveaux est immédiate sans pagination profonde, et les niveaux +21-22 sont disponibles dès qu'ils existent sur la saison.

### Pourquoi pas Blizzard seul

Le payload Blizzard contient `ranking, duration, completed_timestamp, keystone_level, members, mythic_rating` et **aucun split par boss**. Les splits sont nécessaires pour `Overlay.lua:249` (`ref.boss_splits_ms[ord + 1]`) qui affiche la pace par boss en cours de run — feature load-bearing de l'addon.

Raider.IO `/run-details` peut retourner ces splits via `logged_details.encounters[].approximate_relative_ended_at`, mais uniquement quand le run a été uploadé sur Warcraft Logs. Spike : ~50 % des runs +22 indexés Raider.IO ont les splits ; aux bas niveaux, le taux tombe à ~0 %. Une stratégie de fallback synthétique est donc nécessaire pour les +15-17.

---

## 3. Décisions clés

| # | Décision | Choix | Raison |
|---|----------|-------|--------|
| 1 | Source découverte | Blizzard `mythic-keystone-leaderboard` | Couvre +2 à +22, agnostique au sort |
| 2 | Source splits hauts niveaux | Raider.IO `/run-details` (best-effort) | Même chemin que pipeline actuel, fonctionne |
| 3 | Source splits bas niveaux | Synthèse par ratios observés | Raider.IO ~0 % de hit aux bas niveaux |
| 4 | Régions | EU + US (par défaut, configurable) | ~95 % du M+ compétitif, ~1700 calls/scrape |
| 5 | Périodes | Période courante uniquement | Sample de ~20 k runs/donjon, largement suffisant |
| 6 | Schéma Data.lua | v2 — drop la couche affixe | Addon ne s'en sert pas, table morte |
| 7 | OAuth credentials | Variables d'env `BLIZZARD_CLIENT_ID/SECRET` | Pas de fuite git, standard secrets |
| 8 | Cache ratios observés | TTL 7 jours par `(season, dungeon)` | Routes ne changent pas dans une saison |
| 9 | Architecture | Refonte complète (pas hybride par plage) | Schéma unifié, un seul flux |

---

## 4. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      scripts/jit_update/                          │
│                                                                   │
│   blizzard.py    ◄── NEW                                          │
│   ├─ BlizzardClient (OAuth client_credentials, token cache)       │
│   ├─ get_periods_index()           → trouver current_period       │
│   ├─ get_dungeons_index()          → mapping id ↔ name            │
│   ├─ get_connected_realms_index()  → liste realm IDs              │
│   └─ get_leaderboard(realm, dungeon, period) → leading_groups     │
│                                                                   │
│   raiderio.py    ◄── REDUIT                                       │
│   ├─ get_static_data()             → conserve (saison/donjons)    │
│   ├─ get_run_details()             → conserve (splits enrichment) │
│   └─ get_runs()                    → conserve (ratios uniquement) │
│                                                                   │
│   splits_synthesis.py  ◄── NEW                                    │
│   ├─ collect_observed_ratios()     → /runs+/run-details, cache 7j │
│   └─ synthesize_splits(clear_time, ratios) → list[int]            │
│                                                                   │
│   pipeline.py    ◄── REFONTE                                      │
│   ├─ discover_runs(blizz, level)   → via BlizzardClient           │
│   ├─ enrich_or_synthesize(runs)    → Raider.IO si match, sinon    │
│   │                                  synthèse                     │
│   └─ build_document()              → Data.lua schema v2           │
│                                                                   │
│   lua_renderer.py  ◄── ADAPT                                      │
│   └─ Emet schema v2 (drop couche affixe)                          │
│                                                                   │
│   models.py      ◄── ADAPT                                        │
│   ├─ BlizzardRun (nouveau dataclass)                              │
│   └─ ReferenceCell : drop affix_combo key                         │
└──────────────────────────────────────────────────────────────────┘

addon/JustInTime/
   Data.lua          ◄── REGEN (schema v2)
   Overlay.lua       ◄── ADAPT (drop affix lookup ~3 lignes)
   Core.lua          ◄── ADAPT (guard schema_version == 2)
   EventTracker.lua  ◄── À VÉRIFIER (probablement intouché)
   Locales.lua       ◄── ADAPT (clé OUTDATED_DATA si guard ajoutée)
```

### Flux de données

1. **Bootstrap** — `BlizzardClient` obtient un token OAuth (cache disque 23 h), récupère `current_period` et la liste des realms par région
2. **Découverte runs** — pour chaque `(region, realm, dungeon)` : appel `mythic-leaderboard`, parse `leading_groups`, filtre par `keystone_level ∈ scope.levels`, accumule un `dict[dungeon_slug][level] = list[BlizzardRun]`
3. **Sélection sample** — par cellule `(dungeon, level)` : `select_slowest_percentile(runs, 10 %, min_count=2)` (logique existante préservée)
4. **Collecte ratios** (1× par scrape, cache 7 j) — pour chaque donjon : `raiderio.get_runs(page=0)` → 20 top runs → `raiderio.get_run_details(run_id)` → extraction des `boss_splits_ms[i] / clear_time` → médiane par ordinal de boss
5. **Indexation des splits réels par niveau** — pendant la collecte des ratios (étape 4), on remplit aussi un index `real_splits_at[(dungeon_slug, level)] → list[boss_splits_ms]` à partir des runs Raider.IO `/runs?page=0` qui ont des `logged_details.encounters` non vides. Cet index est utilisé tel quel pour les cellules dont le niveau correspond (typiquement 18-22, là où Raider.IO indexe les top runs).
6. **Enrichissement / synthèse** — par cellule `(dungeon, level)` :
   - Si `real_splits_at[(dungeon, level)]` non vide, calculer `boss_splits_ms` comme médiane par position des splits réels (logique existante préservée), `splits_source = "raiderio"`
   - Sinon, `boss_splits_ms[i] = round(clear_time_median × observed_ratios[dungeon][i])`, `splits_source = "synthesized"`
   - Si `observed_ratios[dungeon]` indisponible (collecte ratios a échoué pour ce donjon) : fallback `[clear_time × (i+1)/N]`, `splits_source = "equidistant_fallback"`, log warning
7. **Render** — `lua_renderer.py` émet le document au schéma v2

**Note sur la sémantique** : `clear_time_median` vient toujours du sample **Blizzard** (large, ~100s de runs/cellule). `boss_splits_ms` vient soit du sample **Raider.IO** top-20 (splits réels au même niveau), soit synthétisé depuis `observed_ratios`. C'est volontairement asymétrique : Blizzard donne la couverture, Raider.IO donne la qualité des splits là où elle existe.

---

## 5. Schéma Data.lua v2

### Structure

```lua
JustInTimeData = {
  meta = {
    generated_at   = "2026-05-09T18:30:00Z",
    schema_version = 2,
    season         = "season-mn-1",
    source         = "blizzard+raiderio",   -- doc-only, pas lu par addon
  },

  -- affix_id_to_slug : SUPPRIMÉ

  dungeons = {
    ["algethar-academy"] = {
      keystone_timer_ms = 1860999,
      bosses = {
        [1] = { ordinal = 1, slug = "overgrown-ancient", name = "Overgrown Ancient" },
        [2] = { ordinal = 2, slug = "...",               name = "..." },
        [3] = { ordinal = 3, slug = "...",               name = "..." },
        [4] = { ordinal = 4, slug = "...",               name = "..." },
      },
      levels = {
        [15] = {
          clear_time_ms  = 1850000,
          boss_splits_ms = { 462500, 925000, 1387500, 1850000 },
          sample_size    = 142,
          splits_source  = "synthesized",
        },
        [16] = { clear_time_ms = ..., boss_splits_ms = {...}, sample_size = ..., splits_source = "..." },
        ...
        [22] = { clear_time_ms = ..., boss_splits_ms = {...}, sample_size = ..., splits_source = "raiderio" },
      },
    },
    ["the-rookery"] = { ... },
    -- 9 donjons saison-mn-1
  },
}
```

### Différences vs v1

| Champ | v1 | v2 |
|---|---|---|
| `meta.schema_version` | `1` | `2` |
| `meta.source` | absent | `"blizzard+raiderio"` |
| `affix_id_to_slug` | présent | supprimé |
| `dungeons[d].levels[L]` | `[affix_combo] = {...}` | direct (pas de sous-clé) |
| `dungeons[d].levels[L].splits_source` | absent | `"raiderio"` / `"synthesized"` / `"equidistant_fallback"` |

### Plages de niveaux couvertes

`scope.levels = [15, 16, 17, 18, 19, 20, 21, 22]` dans la nouvelle config TOML. Tout niveau hors range est ignoré dès le filtrage des `leading_groups`.

---

## 6. Client Blizzard

### Authentification

- Endpoint global : `https://oauth.battle.net/token`
- Flow : `client_credentials`
- Credentials lus depuis env : `BLIZZARD_CLIENT_ID`, `BLIZZARD_CLIENT_SECRET`. Échec immédiat avec message clair si manquants.
- Token mis en cache (RAM + disque, TTL 23 h, marge sur `expires_in=86400`) pour éviter les ré-auth fréquentes

### Endpoints utilisés

| Endpoint | Usage | Cache TTL |
|---|---|---|
| `/data/wow/mythic-keystone/period/index?namespace=dynamic-{region}` | Récupère `current_period.id` | 1 h |
| `/data/wow/mythic-keystone/dungeon/index?namespace=dynamic-{region}` | Mapping id ↔ name (debug) | 24 h |
| `/data/wow/connected-realm/index?namespace=dynamic-{region}` | Liste realm IDs (~92 EU, ~146 US) | 24 h |
| `/data/wow/connected-realm/{realm_id}/mythic-leaderboard/{dungeon_id}/period/{period_id}?namespace=dynamic-{region}` | Cœur de la découverte | `[blizzard].cache_ttl_seconds` (default 1 h) |

### Mapping dungeon Raider.IO ↔ Blizzard

Via `map_challenge_mode_id` :
- Raider.IO `static_data.seasons[].dungeons[].map_challenge_mode_id`
- Blizzard `mythic-keystone/dungeon/{id}` — l'ID Blizzard est `map_challenge_mode_id`
- Vérifié spike : Algeth'ar Academy = 402 des deux côtés

### Rate limiting

- Limite documentée Blizzard : 100 req/sec, 36 000 req/heure par client_id
- Charge prévue : 184 realms (EU+US) × 9 donjons × 1 période = **1656 calls par scrape**
- Plafond conservateur : `rate_per_second = 80` (cf. `RateLimiter` existant, instance dédiée Blizzard)
- Backoff exponentiel sur `429` et `503` (3 retries par défaut)

### Section TOML ajoutée

```toml
[blizzard]
regions             = ["eu", "us"]
rate_per_second     = 80
cache_ttl_seconds   = 3600
timeout_seconds     = 30.0
max_retries         = 3

[scope]
levels              = [15, 16, 17, 18, 19, 20, 21, 22]
min_sample          = 20
slowest_percentile  = 10
# max_pages_per_query : SUPPRIMÉ (n'a plus de sens, Blizzard retourne tout d'un coup)
```

---

## 7. Algorithme de synthèse des splits

### 7.1 Collecte des ratios observés

Pour chaque donjon, une fois par cycle hebdo (cache 7 jours par clé `(season, dungeon)`) :

```python
def collect_observed_ratios(raiderio, season, dungeon_slug, num_bosses):
    runs = raiderio.get_runs(season, region="world", dungeon=dungeon_slug, page=0)
    samples_per_ordinal: list[list[float]] = [[] for _ in range(num_bosses)]

    for r in runs["rankings"]:
        rd = raiderio.get_run_details(season, run_id=r["run"]["keystone_run_id"])
        if not rd.encounters:
            continue
        clear_time = rd.clear_time_ms
        if clear_time <= 0:
            continue
        for i, split in enumerate(rd.boss_splits_ms()):
            if split is not None and 0 < split <= clear_time * 1.05:  # tolérance 5 %
                samples_per_ordinal[i].append(split / clear_time)

    return [
        statistics.median(samples) if samples else None
        for samples in samples_per_ordinal
    ]
```

Retourne une liste de `num_bosses` floats (ratios médians) ou `None` aux positions sans données.

### 7.2 Application de la synthèse

```python
def synthesize_splits(clear_time_ms: int, ratios: list[float | None], num_bosses: int) -> list[int]:
    if all(r is None for r in ratios):
        # fallback ultime : équidistant
        return [round(clear_time_ms * (i + 1) / num_bosses) for i in range(num_bosses)]
    return [
        round(clear_time_ms * r) if r is not None
        else round(clear_time_ms * (i + 1) / num_bosses)
        for i, r in enumerate(ratios)
    ]
```

### 7.3 Sélection source par cellule

```python
def aggregate_cell(blizzard_runs, real_splits_at_level, observed_ratios, num_bosses):
    """
    Args:
        blizzard_runs:        list[BlizzardRun] — sample slowest_percentile pour la cellule
        real_splits_at_level: list[list[int]]   — splits réels Raider.IO indexés à ce niveau
                                                  (vide si aucun run Raider.IO indexé à ce niveau)
        observed_ratios:      list[float|None]  — ratios médians par boss ordinal pour ce donjon
    """
    clear_time_median = int(statistics.median(r.duration_ms for r in blizzard_runs))

    if real_splits_at_level:
        boss_splits = median_per_position_with_backfill(
            real_splits_at_level, num_bosses, clear_time_median
        )
        source = "raiderio"
    elif any(r is not None for r in observed_ratios):
        boss_splits = synthesize_splits(clear_time_median, observed_ratios, num_bosses)
        source = "synthesized"
    else:
        boss_splits = [round(clear_time_median * (i + 1) / num_bosses) for i in range(num_bosses)]
        source = "equidistant_fallback"

    return ReferenceCell(
        sample_size=len(blizzard_runs),
        clear_time_ms=clear_time_median,
        boss_splits_ms=boss_splits,
        splits_source=source,
    )
```

### 7.4 Notes sémantiques

- `boss_splits_ms[i]` = temps **cumulatif** (ms relatif au démarrage de la run) auquel le boss à l'ordinal statique `i` est tué
- L'array peut être non-monotone si la route du donjon n'est pas linéaire (boss d'ordinal bas tué après ordinal haut)
- Les ratios médians par ordinal capturent ces non-monotonies naturellement

### 7.5 Cross-référence Blizzard ↔ Raider.IO pour splits aux niveaux 18-22

`leading_groups` Blizzard ne contient **pas** `keystone_run_id`. Pour récupérer les splits Raider.IO d'un run Blizzard donné, le matching par `(realm_id, dungeon_id, period, completed_timestamp, members[].character_id)` serait nécessaire et fragile.

**Décision** : on n'essaie **pas** de cross-référencer. Tous les splits du Data.lua produit sont :
- soit médians de splits réels d'un sample de top runs Raider.IO (uniquement disponible si `raiderio.get_runs(level=18-20)` retourne des runs avec `logged_details`) — détour sur `[scope] levels` réutilisant le chemin existant Raider.IO en parallèle
- soit synthétisés depuis `observed_ratios`

**Implication** : pour les niveaux 18-20, on conserve **deux sources** de runs en parallèle :
- Blizzard pour le `clear_time_median` et `sample_size` (sample plus large)
- Raider.IO `/runs?page=0` (top 20 runs, déjà appelé pour les ratios) → pris comme « splits réels » du sample

Cette dualité est OK car :
- Le `clear_time_median` Blizzard est plus représentatif (sample 100×)
- Les splits Raider.IO sont les seuls « vrais », même s'ils viennent d'un sample distinct
- Le ratio splits / clear_time reste cohérent à un niveau donné (variance < 5 %)

---

## 8. Impact addon Lua

### 8.1 `Overlay.lua`

Trois lookups à patcher (lignes 228, 249, 326) — drop la sous-clé `[affix_combo]` :

```diff
-  local ref = data.dungeons[slug] and data.dungeons[slug].levels[level]
-              and data.dungeons[slug].levels[level][affixCombo]
+  local ref = data.dungeons[slug] and data.dungeons[slug].levels[level]
```

Le code en aval (`ref and ref.boss_splits_ms and ref.boss_splits_ms[ord + 1]`) reste inchangé et nil-safe.

### 8.2 `Core.lua`

Garde de version au load :

```lua
local function checkSchema()
  if not (JustInTimeData and JustInTimeData.meta) then
    ChatPrinter.warn(L.MISSING_DATA)
    return false
  end
  if JustInTimeData.meta.schema_version ~= 2 then
    ChatPrinter.warn(L.OUTDATED_DATA)
    return false
  end
  return true
end
```

Appelée depuis `OnLoad`. Si elle échoue, l'addon n'enregistre pas ses events — pas de crash, juste pas de pace.

### 8.3 `Locales.lua`

Ajout des clés (FR + EN) :

```lua
L.OUTDATED_DATA = "Données de référence obsolètes. Mets à jour l'addon ou regenère Data.lua."  -- FR
L.OUTDATED_DATA = "Reference data is outdated. Update the addon or regenerate Data.lua."       -- EN
L.MISSING_DATA  = "Données de référence introuvables. L'addon est peut-être mal installé."     -- FR
L.MISSING_DATA  = "Reference data missing. The addon may be incorrectly installed."             -- EN
```

### 8.4 `EventTracker.lua`

`grep -n "affix" EventTracker.lua` → 0 hits (vérifié initialement). Aucune modification nécessaire.

### 8.5 Versioning

- Bump `JustInTime.toc` Version : `0.3.4` → `0.4.0` (minor — schéma `Data.lua` change est breaking pour quiconque aurait un `Data.lua` modifié à la main, improbable)
- `CHANGELOG.txt` : nouvelle entrée v0.4.0 documentant l'extension de couverture +15-22

---

## 9. Stratégie de tests

### 9.1 Tests unitaires Python

Localisés dans `scripts/tests/`, exécutés via `pytest`.

| Module testé | Cas couverts |
|---|---|
| `blizzard.py` | OAuth flow (mock `httpx`), token refresh à expiration, retry exponentiel sur 429, parsing leaderboard, mapping `region → base_url`, gestion erreur creds manquants |
| `splits_synthesis.py` | Ratios médians (cas vides, monotonie cassée, mix réel+missing), `synthesize_splits` (rounding, fallback equidistant, ratios partiels), cache disque 7 j |
| `pipeline.py` | Flux complet avec `BlizzardClient` + `RaiderIOClient` mockés, agrégation `slowest_percentile` par level, sélection source splits, gestion `min_sample` insuffisant, doc final |
| `lua_renderer.py` | Output schema v2 (clé `levels[L]` directe sans sous-clé affixe), présence `splits_source`, `schema_version=2`, `affix_id_to_slug` absent |
| `models.py` | Validation Pydantic `BlizzardRun`, `BlizzardLeaderboardResponse`, sérialisation/désérialisation cache disque |

### 9.2 Tests d'intégration (live, opt-in)

Marqueur `@pytest.mark.live` (skippé par défaut, `pytest -m live` pour exécuter). Nécessite `BLIZZARD_CLIENT_ID/SECRET` configurés.

- Auth réelle Battle.net → token valide
- 1 call leaderboard sur 1 realm/donjon EU → parse OK, `leading_groups` non vide
- 1 call /runs Raider.IO → toujours fonctionnel après nos modifs

### 9.3 Validation manuelle

1. `make rebuild` (root Makefile, cible existante depuis commit `0cc384d`) → `Data.lua` v2 généré sans erreur
2. Diff visuel `Data.lua` : niveaux 15-22 présents, `affix_combo` absent, `splits_source` présent, `schema_version=2`
3. Sanity sur splits synthétisés : valeurs cohérentes avec `clear_time × ratios_observés`
4. Test in-game : addon chargé avec nouveau `Data.lua`, lancement d'une +15 (ou simulation via macro existante d'après `Overlay.lua:497`), overlay affiche pace par boss correcte
5. Test régression : +20 in-game, splits réels (Raider.IO) toujours là et cohérents avec ancienne version

### 9.4 Critères d'acceptation

- [ ] `Data.lua` régénéré contient les 9 donjons de la saison `season-mn-1`
- [ ] Chaque donjon contient les niveaux 15 à 22 inclusivement (sauf si `min_sample` non atteint, dans ce cas la cellule est absente — log explicite)
- [ ] Au moins une cellule par donjon est `splits_source = "raiderio"` (sanity sur le détour Raider.IO)
- [ ] Aucun fallback `equidistant_fallback` sur les 9 donjons (sinon ça veut dire que la collecte de ratios a échoué → bug)
- [ ] `pytest scripts/tests/` au vert (unit only, intégration opt-in)
- [ ] Addon in-game charge sans erreur avec nouveau `Data.lua`
- [ ] Pace par boss s'affiche correctement à +18 (réel) et à +15 (synthétisé)

---

## 10. Risques et points ouverts

### Risques identifiés

| Risque | Mitigation |
|---|---|
| API Blizzard rate-limite plus strict que documenté | `rate_per_second = 80` conservateur, backoff exponentiel, cache disque |
| Token OAuth invalidé en cours de scrape | Détection 401 → refresh token + retry une fois |
| Realm sans aucune run M+ pour un donjon | `leading_groups = []` géré comme cas normal, skip silencieux |
| Saison Midnight `season-mn-1` ne mappe pas trivialement à des periods Blizzard | On utilise `current_period` uniquement, pas de range, donc le mapping est implicite (la période courante appartient à la saison courante) |
| Raider.IO change le format de `/run-details` | Tests unitaires figent les assomptions, échec rapide en CI |
| Boss ordinal dans Blizzard ≠ ordinal Raider.IO pour un même donjon | On n'utilise jamais le boss ordinal côté Blizzard (pas exposé dans le payload). Tout le boss ordering vient de Raider.IO `static_data` ou `/run-details` |
| Sample size +21/+22 trop bas en début de saison | `min_sample = 20` filtre proprement, log explicite, cellule absente — comportement attendu |

### Points ouverts (à trancher pendant l'implémentation, pas bloquant pour le spec)

- Format exact du log de fin de scrape (CLI output) — métriques à inclure : `total_runs_discovered`, `runs_per_level`, `splits_source_distribution`, `regions_scanned`, `duration_seconds`
- Faut-il un mode `--dry-run` qui n'écrit pas `Data.lua` ? Vérifier si présent dans `cli.py` actuel
- Comportement quand `BLIZZARD_CLIENT_ID/SECRET` absent : est-ce qu'on tombe sur un fallback Raider.IO-only (legacy v1) ou est-ce qu'on échoue net ? Recommandation : échec net (clarté), avec message qui pointe vers `develop.battle.net`
- Devrait-on persister un `meta.scrape_stats` dans `Data.lua` pour debug (compte de runs par source) ? Pas critique, peut être ajouté plus tard

### Hors scope explicite

- Régions KR + TW : configurable mais désactivées par défaut
- Multi-period historique (lookback de plusieurs semaines) : sample courant suffisant, complexifierait la sémantique des affixes
- Données Mythic+ raid (raid leaderboard) : non concerné
- API Battle.net `WoW Profile API` (caractères des joueurs) : pas nécessaire pour ce design
- Exposition des `splits_source` à l'utilisateur final dans l'overlay : décision UX séparée, le champ est juste posé dans `Data.lua` pour debug
