# Brief de session autonome — JustInTime

## Objectif

Livrer l'addon **JustInTime** complet et jouable à partir du spec existant. L'utilisateur checke le résultat demain matin.

## Étapes

1. **Lire le spec** : `docs/specs/<YYYY-MM-DD>-jit-design.md`.
2. **Planifier** : invoquer `superpowers:writing-plans` — sauvegarder dans `docs/specs/<YYYY-MM-DD>-jit-plan.md`.
3. **Implémenter** : déléguer à un sous-agent (`general-purpose`) pour préserver le contexte principal. Le plan contient tout le code.
4. **Packaging** : produire `addon/JustInTime-vX.Y.Z.zip`.
5. **Publier master** : contenu addon uniquement à la racine, tag `vX.Y.Z`, push origin master.

## Workflow git (CRITIQUE — ne pas dévier)

- **`main` (locale uniquement)** : tous les commits dev, docs, spec, plan, zip, rapports. **Jamais push**.
- **`master` (distante)** : uniquement le contenu de `addon/JustInTime/` à la racine.
- Commits conventional + gitmoji. Atomiques.
- Publication master :
  ```bash
  git checkout master
  git rm -rf . 2>/dev/null
  git checkout main -- addon/JustInTime
  mv addon/JustInTime/* .
  rm -rf addon
  git add -A
  git commit -m "🎉 feat: release vX.Y.Z"
  git tag -a vX.Y.Z -m "Release vX.Y.Z"
  git push origin master
  git push origin vX.Y.Z
  git checkout main
  ```

## Notifications Discord

Webhook stocké dans le brief (voir ci-dessous). Ping `@everyone` à chaque jalon. Couleurs embed :
- 🔬 Recherche : `3447003` (bleu)
- 🛠️ Dev : `15105570` (orange)
- 🎨 Branding / polish : `12587743` (violet clair)
- ✅ Succès : `3066993` (vert)
- 🐛 Bug / erreur : `15158332` (rouge)

**Webhook URL** : `https://discord.com/api/webhooks/1497374432489111573/0QGboFrZ36-T9qPbh3dTc32exPDeEUKd_9pnbYfyycD28jcN4CKlqVaM4Wu8CUg02ssv`

## Contraintes techniques

- Lua pur, **aucune lib externe** (pas d'Ace3, pas de LibStub).
- WoW Retail Midnight, `Interface = 120001`.
- Code et commentaires en anglais ; Locales FR par défaut + EN.
- Zéro global leak : tout `local`, namespace via varargs (`local _, RRH = ...` style).
- `OnUpdate` unique, throttle ≥10 Hz, actif **uniquement** quand nécessaire.
- Branding : dégradé rouge → violet sur le titre UI, tag chat `[<slug>]` coloré, footer `By Claralicious_` tricolore.

## Langue

- Code, commentaires, identifiants, commits : **anglais**
- Messages Discord + conversation : **français**
