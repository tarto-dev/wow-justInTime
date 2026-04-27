local addonName, NS = ...

local locale = GetLocale()
local L = setmetatable({}, { __index = function(_, k) return k end })

-- Affix slug → localized display name (used in chat / overlay tooltips).
-- Falls back to the slug itself when missing.
local AFFIX_DISPLAY_FR = {
    fortified = "Fortifiée",
    tyrannical = "Tyrannique",
    ["xalataths-guile"] = "Ruse de Xal'atath",
}

local AFFIX_DISPLAY_EN = {
    fortified = "Fortified",
    tyrannical = "Tyrannical",
    ["xalataths-guile"] = "Xal'atath's Guile",
}

local fr = {
    ADDON_LOADED          = "%s chargé. /jit pour les options.",
    FRAME_TITLE           = "JustInTime",
    SLASH_HELP            = "Commandes : /jit | /jit show | /jit hide | /jit lock | /jit unlock | /jit mode <public|fastest|recent|median> | /jit reset | /jit help",
    SLASH_UNKNOWN         = "Commande inconnue : %s. /jit help",

    REF_NONE              = "réf. indispo",
    REF_PUBLIC_LABEL      = "ref publique",
    REF_PERSO_FASTEST     = "Mes runs (la + rapide)",
    REF_PERSO_RECENT      = "Mes runs (la + récente)",
    REF_PERSO_MEDIAN      = "Mes runs (médiane)",

    BOSS_KILL_TRIGGER     = "%s tué — %s vs %s",
    KEY_END_TIMED         = "Run terminée %s ✓ timée — %s vs %s",
    KEY_END_DEPLETED      = "Run dépletée %s ✗ — %s vs %s",
    THRESHOLD_AHEAD       = "tu viens de basculer en avance (+%s)",
    THRESHOLD_BEHIND      = "tu viens de basculer en retard (−%s)",
    CRITICAL_DEPLETE      = "⚠ projection : déplate prévue à %s (%s) — envisage un reset",

    DELTA_AHEAD           = "%s d'avance",
    DELTA_BEHIND          = "%s de retard",
    DELTA_ZERO            = "à l'heure",

    OVERLAY_LABEL_ELAPSED = "Écoulé",
    OVERLAY_LABEL_TIMER   = "Timer",
    OVERLAY_LABEL_ETA     = "ETA",
    OVERLAY_LABEL_LAST    = "Last split",
    OVERLAY_LABEL_REF     = "Réf",
    OVERLAY_REF_NONE      = "réf indispo",
    OVERLAY_REF_LEVEL_FALLBACK = "%s (clé +%d)",
    LEVEL_FALLBACK_INFO   = "pas de réf pour clé +%d, fallback sur clé +%d",

    PANEL_REF_HEADER      = "Référence",
    PANEL_REF_PUBLIC      = "Publique (les pires runs timées)",
    PANEL_REF_FASTEST     = "Mes runs : la plus rapide",
    PANEL_REF_RECENT      = "Mes runs : la plus récente",
    PANEL_REF_MEDIAN      = "Mes runs : médiane",
    PANEL_IGNORE_AFFIXES  = "Ignorer les affixes (élargir le sample)",

    PANEL_OVERLAY_HEADER  = "Overlay graphique",
    PANEL_OVERLAY_ALWAYS  = "Toujours visible",
    PANEL_OVERLAY_POPUP   = "Popup transitoire (6s post-boss kill)",
    PANEL_OVERLAY_LOCK    = "Verrouiller la position",
    PANEL_OVERLAY_RESET   = "Réinitialiser la position",
    PANEL_OVERLAY_ANCHOR_SHOW = "Afficher le cadre (déplaçable)",
    PANEL_OVERLAY_ANCHOR_HIDE = "Masquer le cadre",

    PANEL_CHAT_HEADER     = "Mode texte (chat)",
    PANEL_CHAT_BOSS_KILL  = "Print à chaque boss kill",
    PANEL_CHAT_KEY_END    = "Récap en fin de clé",
    PANEL_CHAT_THRESHOLD  = "Alerte au passage de seuil (vert ↔ rouge)",

    PANEL_CRIT_HEADER     = "Alerte « tu vas déplate »",
    PANEL_CRIT_VISUAL     = "Visuel (pulsation rouge)",
    PANEL_CRIT_CHAT       = "Chat warning",
    PANEL_CRIT_SOUND      = "Son d'alerte",

    PANEL_DATA_HEADER     = "Données",
    PANEL_DATA_GENERATED  = "Référence générée le : %s (il y a %d jours) %s",
    PANEL_DATA_RESET_RUNS = "Effacer mes runs (confirmation)",
    PANEL_DATA_NONE       = "Aucune référence chargée",

    DATA_STALE            = "⚠ données de référence vieilles de %d jours",
    DATA_MISSING          = "⚠ référence indisponible — mode publique désactivé",
    DATA_SCHEMA_INVALID   = "⚠ référence invalide — mode publique désactivé",

    NO_PERSO_RUNS         = "pas encore de run perso ici, fallback sur public",
    NO_REF_AT_ALL         = "réf indispo (cellule vide)",

    CONFIRM_RESET_RUNS    = "Effacer toutes tes runs perso ? (impossible à annuler)",
    BTN_YES               = "Oui",
    BTN_NO                = "Non",
    RESET_DONE            = "Runs perso effacées (%d entrées)",
}

local en = {
    ADDON_LOADED          = "%s loaded. Type /jit for options.",
    FRAME_TITLE           = "JustInTime",
    SLASH_HELP            = "Commands: /jit | /jit show | /jit hide | /jit lock | /jit unlock | /jit mode <public|fastest|recent|median> | /jit reset | /jit help",
    SLASH_UNKNOWN         = "Unknown command: %s. /jit help",

    REF_NONE              = "ref unavailable",
    REF_PUBLIC_LABEL      = "public ref",
    REF_PERSO_FASTEST     = "My runs (fastest)",
    REF_PERSO_RECENT      = "My runs (most recent)",
    REF_PERSO_MEDIAN      = "My runs (median)",

    BOSS_KILL_TRIGGER     = "%s killed — %s vs %s",
    KEY_END_TIMED         = "Run timed %s ✓ — %s vs %s",
    KEY_END_DEPLETED      = "Run depleted %s ✗ — %s vs %s",
    THRESHOLD_AHEAD       = "you just moved ahead (+%s)",
    THRESHOLD_BEHIND      = "you just fell behind (−%s)",
    CRITICAL_DEPLETE      = "⚠ projection: deplete predicted at %s (%s) — consider reset",

    DELTA_AHEAD           = "%s ahead",
    DELTA_BEHIND          = "%s behind",
    DELTA_ZERO            = "on pace",

    OVERLAY_LABEL_ELAPSED = "Elapsed",
    OVERLAY_LABEL_TIMER   = "Timer",
    OVERLAY_LABEL_ETA     = "ETA",
    OVERLAY_LABEL_LAST    = "Last split",
    OVERLAY_LABEL_REF     = "Ref",
    OVERLAY_REF_NONE      = "ref unavailable",
    OVERLAY_REF_LEVEL_FALLBACK = "%s (key +%d)",
    LEVEL_FALLBACK_INFO   = "no ref for key +%d, falling back to key +%d",

    PANEL_REF_HEADER      = "Reference",
    PANEL_REF_PUBLIC      = "Public (slowest timed runs)",
    PANEL_REF_FASTEST     = "My runs: fastest",
    PANEL_REF_RECENT      = "My runs: most recent",
    PANEL_REF_MEDIAN      = "My runs: median",
    PANEL_IGNORE_AFFIXES  = "Ignore affixes (widen sample)",

    PANEL_OVERLAY_HEADER  = "Graphic overlay",
    PANEL_OVERLAY_ALWAYS  = "Always visible",
    PANEL_OVERLAY_POPUP   = "Popup transient (6s after boss kill)",
    PANEL_OVERLAY_LOCK    = "Lock position",
    PANEL_OVERLAY_RESET   = "Reset position",
    PANEL_OVERLAY_ANCHOR_SHOW = "Show overlay (drag to move)",
    PANEL_OVERLAY_ANCHOR_HIDE = "Hide overlay",

    PANEL_CHAT_HEADER     = "Text mode (chat)",
    PANEL_CHAT_BOSS_KILL  = "Print on each boss kill",
    PANEL_CHAT_KEY_END    = "Key end recap",
    PANEL_CHAT_THRESHOLD  = "Alert on threshold cross (green ↔ red)",

    PANEL_CRIT_HEADER     = "Deplete-imminent alerts",
    PANEL_CRIT_VISUAL     = "Visual (red pulse)",
    PANEL_CRIT_CHAT       = "Chat warning",
    PANEL_CRIT_SOUND      = "Sound alert",

    PANEL_DATA_HEADER     = "Data",
    PANEL_DATA_GENERATED  = "Reference generated at: %s (%d days ago) %s",
    PANEL_DATA_RESET_RUNS = "Erase my runs (confirmation)",
    PANEL_DATA_NONE       = "No reference loaded",

    DATA_STALE            = "⚠ reference data is %d days old",
    DATA_MISSING          = "⚠ reference unavailable — public mode disabled",
    DATA_SCHEMA_INVALID   = "⚠ reference invalid — public mode disabled",

    NO_PERSO_RUNS         = "no personal runs here yet, falling back to public",
    NO_REF_AT_ALL         = "ref unavailable (empty cell)",

    CONFIRM_RESET_RUNS    = "Erase all your personal runs? (cannot be undone)",
    BTN_YES               = "Yes",
    BTN_NO                = "No",
    RESET_DONE            = "Personal runs erased (%d entries)",
}

local active = (locale == "enUS" or locale == "enGB") and en or fr
for k, v in pairs(active) do L[k] = v end

NS.L = L
NS.AffixDisplayFR = AFFIX_DISPLAY_FR
NS.AffixDisplayEN = AFFIX_DISPLAY_EN

function NS.AffixDisplayName(slug)
    local map = (locale == "enUS" or locale == "enGB") and AFFIX_DISPLAY_EN or AFFIX_DISPLAY_FR
    return map[slug] or slug
end
