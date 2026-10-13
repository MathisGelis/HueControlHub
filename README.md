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
| Hooks réels dans Claude Code | **Testé** avec Claude Code 2.1.296 en mode `-p` (Linux, daemon `--simulate`) : `UserPromptSubmit`, `PermissionRequest` → rouge, `Stop` → vert, `SessionEnd`. Session interactive non testée |
| Teams : presence + nouveaux messages (Graph) | Implémenté, **testé uniquement avec des réponses Graph simulées** — jamais appelé sur un vrai tenant |
| Teams : sonnerie d'appel entrant, canaux, mentions | **Non supporté** (voir section Teams) |
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
ambient-light doctor                    # santé : config, hooks, daemon, Teams
ambient-light teams-login | teams-logout | teams-check
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
Les hooks sont **synchrones** (≈ 45 ms mesurés, daemon arrêté ; `async` testé et rejeté : Claude Code tue les hooks async à la sortie en mode `-p`, le signal vert était perdu). Un processus Python par appel d'outil (`PostToolUse`).
`SessionEnd` ne résout que les attentes, pas le vert de fin de tâche.

## Configuration

Voir `config.example.toml`. Défauts : permission/saisie rouge, message orange 5 s, tâche terminée vert 3 s, repos éteint (`off`).
Priorités (défaut) : permission 100 > appel entrant 90 > appel en cours 70 > saisie 60 > erreur 55 > message 50 > tâche terminée 40.
À priorité égale, l'événement le plus récent gagne.

## Confidentialité

Seuls `hook_event_name`, `session_id` (assaini), `notification_type` et `error` sont lus. Contenus de messages, commandes et
sorties d'outils ne sont ni stockés ni journalisés. Les événements ne sont conservés qu'en mémoire.

## Tests

```
.venv/bin/pytest      # 22 tests : normalisation, priorités, expiration, ack, config, install hooks, daemon+reconnexion simulée, Teams (Graph simulé)
```
Dernier résultat : 22 passed + essai réel des hooks Claude Code (daemon simulé). Aucun test matériel, aucun appel Graph réel.

## Checklist de validation manuelle (matériel requis)

1. `ambient-light scan` détecte l'ampoule. 2. `color "#FF0000"`, orange, vert, bleu : 4 couleurs distinctes ?
3. `run` + `simulate permission_required` → rouge ; `simulate task_completed` ne le remplace pas.
4. `install-hooks`, session Claude Code réelle : permission → rouge ; réponse → retour au repos ; fin de tâche → vert 3 s.
5. Éteindre/éloigner l'ampoule : `status` indique `disconnected`, pas de crash ; la rallumer : l'état est réappliqué.
6. `stop` : ampoule éteinte, socket supprimé. 7. Relancer. 8. Répéter sous macOS et Linux.

## Teams (compte professionnel) — `docs` ci-dessous

Étude des options (la doc Microsoft Learn n'était pas accessible depuis l'environnement de dev : les points marqués **à vérifier** viennent de sources secondaires) :

| Besoin | Option retenue | Remarques |
|---|---|---|
| Appel / réunion en cours | Graph `GET /me/presence` (`Presence.Read`, délégué), polling 15 s | `activity` = `InACall`, `InAConferenceCall`, `Presenting`, `InAMeeting`. `InAMeeting` peut aussi venir du calendrier sans réunion rejointe : réglable via `teams.meeting_counts_as_call`. Consentement utilisateur suffisant : **à vérifier** pour votre tenant |
| Nouveaux messages (1:1, groupes) | Graph `GET /me/chats?$expand=lastMessagePreview` (`Chat.Read`, délégué), polling 20 s | Compare l'id du dernier message ; ignore vos propres messages, les messages système et les doublons. Le premier passage n'alerte pas. Consentement admin requis ou non : **à vérifier** |
| Appel entrant (sonnerie) | **Aucune source fiable** | Pas d'événement Graph pour un utilisateur simple (les API d'appels sont pour des bots/applications). Notifications OS : pas d'API supportée sous macOS ; sous Linux, écoute D-Bus possible mais fragile → non implémenté |
| Canaux, mentions | **Non supporté** | Nécessite des permissions administrateur et la lecture du contenu |

Webhooks/change notifications Graph : écartés (exigent une URL publique, contraire au « tout local »).

### Mise en place
1. Dans Microsoft Entra (portail Azure), enregistrer une application : *Comptes de ce répertoire uniquement*, activer *Autoriser les flux clients publics*, permissions déléguées Microsoft Graph `Presence.Read`, `Chat.Read`. Si votre organisation interdit l'enregistrement d'applications ou le consentement utilisateur, demander à l'administrateur — c'est la contrainte principale. Ne pas réutiliser l'identifiant d'une application tierce.
2. Config : `[sources] teams = true` et `[teams] client_id = "..."` (voir `config.example.toml`).
3. `ambient-light teams-login` (code d'appareil), puis `ambient-light teams-check`, puis `ambient-light run`.

### Données et confidentialité
- Lues : `activity` de la presence ; pour chaque chat, id, type, expéditeur (id) et id du dernier message. **Le texte des messages n'est ni lu en détail, ni stocké, ni journalisé** (il est présent dans la réponse Graph mais ignoré et jeté).
- Conservées en mémoire seulement : dernier id de message par chat. Le jeton de rafraîchissement est dans `~/.config/ambient-light/teams_token.json` (0600, hors Git), jamais journalisé. `teams-logout` le supprime.
- Aucun service tiers : seuls `login.microsoftonline.com` et `graph.microsoft.com` sont contactés.
- Si Graph est injoignable pendant un appel, l'état « appel en cours » reste jusqu'au prochain poll réussi.
