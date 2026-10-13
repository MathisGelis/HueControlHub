# Ambient Status Light

Transforme une ampoule Philips Hue Bluetooth (sans Bridge) en indicateur lumineux
pour Claude Code (et, plus tard, Teams). Voir `CLAUDE.md` pour le cahier des charges.

## État d'avancement (honnête)

| Élément | Statut |
|---|---|
| Normalisation, State Manager, priorités, expiration, acquittement | Implémenté, **testé** (tests unitaires) |
| Daemon + socket local + hooks Claude Code | Implémenté, **testé en simulation** (faux contrôleur) |
| Installation des hooks (fusion sans écrasement) | Implémenté, testé sur fichier temporaire |
| Contrôleur HueBLE (`controllers/hueble.py`) | Écrit d'après le code source de HueBLE 2.2.3, **NON testé sur une vraie ampoule** |
| Reconnexion | Testée avec le faux contrôleur uniquement |
| Hooks réels dans Claude Code | **Non testé** dans une vraie session |
| Teams | **Non implémenté** (seulement événements simulés) |
| macOS / Linux réels | **Non validé** (développé dans un conteneur cloud sans Bluetooth) |

## Architecture

`hook.py` (stdin JSON) → socket Unix 0600 → `daemon.py` → `events.py` (normalisation, liste blanche) →
`state.py` (StateManager) → `controllers/` (interface `HueController`; `fake`, `hueble`).
Le hook n'a aucune dépendance Bluetooth, borne son temps à 0,5 s et sort toujours en 0.
Aucun serveur réseau : socket Unix dans `$XDG_RUNTIME_DIR` (ou `/tmp`), permissions 0600.

## Installation

Prérequis : Python ≥ 3.11.

```
python3 -m venv .venv && .venv/bin/pip install -e '.[hue,dev]'
```
- **macOS** : autoriser le Bluetooth pour le terminal (Réglages > Confidentialité > Bluetooth). Pairing éventuel via l'OS (HueBLE ne pairerait automatiquement que sous Linux).
- **Linux** : BlueZ requis (`bluetoothd` actif) ; l'utilisateur doit pouvoir accéder à D-Bus/BlueZ.

## Commandes

```
ambient-light check-config              # valide la config
ambient-light scan                      # détecte les ampoules Hue BLE
ambient-light color "#FF0000"           # teste une couleur (controller = hueble)
ambient-light run [--simulate]          # lance le daemon (--simulate : aucune écriture matérielle)
ambient-light simulate permission_required   # injecte un événement (types: voir config)
ambient-light status | ack | stop
ambient-light install-hooks | uninstall-hooks
```
`install-hooks` ajoute nos entrées à `~/.claude/settings.json` (sauvegarde `.bak`, hooks existants conservés,
idempotent). Il utilise le Python courant : lancer la commande depuis le venv où le paquet est installé.

## Sémantique des hooks Claude Code

| Hook | Effet |
|---|---|
| `PermissionRequest`, `Notification:permission_prompt` | rouge persistant (`permission_required`) |
| `Notification:idle_prompt` / `elicitation_*` / `agent_needs_input` | `input_required` (rouge, persistant) |
| `Stop` | résout les attentes de la session + vert 3 s (ne masque jamais une alerte plus prioritaire) |
| `StopFailure` | `task_error` (magenta 10 s), distinct de la fin normale |
| `UserPromptSubmit` | résout les attentes de la session |
| `PostToolUse`, `PostToolUseFailure`, `PermissionDenied` | résout `permission_required` |
| `SessionEnd` | efface tous les états de la session |

Limite connue : si l'utilisateur refuse/répond sans qu'un de ces hooks ne se déclenche, l'alerte reste jusqu'à `ambient-light ack`.
Les hooks sont lancés en `async` : un hook par appel d'outil (`PostToolUse`) crée un petit processus Python ; surcoût à mesurer.

## Configuration

Voir `config.example.toml`. Défauts : permission/saisie rouge, message orange 5 s, tâche terminée vert 3 s, repos éteint (`off`).
Priorités (défaut) : permission 100 > appel entrant 90 > appel en cours 70 > saisie 60 > erreur 55 > message 50 > tâche terminée 40.
À priorité égale, l'événement le plus récent gagne.

## Confidentialité

Seuls `hook_event_name`, `session_id` (assaini), `notification_type` et `error` sont lus. Contenus de messages, commandes et
sorties d'outils ne sont ni stockés ni journalisés. Les événements ne sont conservés qu'en mémoire.

## Tests

```
.venv/bin/pytest      # 15 tests : normalisation, priorités, expiration, ack, config, install hooks, daemon+reconnexion simulée
```
Dernier résultat : 15 passed (simulation uniquement — aucun test matériel exécuté).

## Checklist de validation manuelle (matériel requis)

1. `ambient-light scan` détecte l'ampoule. 2. `color "#FF0000"`, orange, vert, bleu : 4 couleurs distinctes ?
3. `run` + `simulate permission_required` → rouge ; `simulate task_completed` ne le remplace pas.
4. `install-hooks`, session Claude Code réelle : permission → rouge ; réponse → retour au repos ; fin de tâche → vert 3 s.
5. Éteindre/éloigner l'ampoule : `status` indique `disconnected`, pas de crash ; la rallumer : l'état est réappliqué.
6. `stop` : ampoule éteinte, socket supprimé. 7. Relancer. 8. Répéter sous macOS et Linux.

## Teams (à faire — Phase 3)

Pistes à évaluer : notifications natives OS, Microsoft Graph (consentement admin probable), aucune API unique pour tout. Rien d'implémenté.
