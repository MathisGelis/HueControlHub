# CLAUDE.md — Ambient Status Light

## 1. Mission du projet

Construire une application locale qui transforme une ampoule Philips Hue Bluetooth en indicateur lumineux intelligent pour l'environnement de travail.

La lumière doit refléter les événements provenant de :
- Claude Code : tâche terminée, autorisation requise, saisie utilisateur nécessaire.
- Microsoft Teams : nouveaux messages, appels entrants, appels en cours et réunions.
- Éventuellement, plus tard : calendrier, tâches longues, notifications système et autres outils.

L'application doit être fiable, discrète, simple à installer et facile à faire évoluer.

**Objectif final :** pouvoir travailler sans surveiller constamment les notifications sur l'écran. La lumière indique quand une intervention est nécessaire.

## 2. Contraintes non négociables

- Compatibilité cible : macOS et Linux.
- Fonctionnement local, sans serveur distant obligatoire.
- Aucun serveur domotique permanent requis.
- Aucun Hue Bridge requis pour la première version.
- Aucun dongle Bluetooth ou USB supplémentaire requis si le Bluetooth intégré est compatible.
- L'ampoule existante doit être réutilisée : Philips Hue White and Color Ambiance Bluetooth, 800 lumens, culot E27.
- La lampe physique est une lampe E27 classique, alimentée par le secteur.
- Le logiciel ne doit pas couper l'alimentation de l'ampoule pour la piloter.
- Les événements de Claude Code doivent être intégrés en priorité.
- Les événements Teams doivent être intégrés ensuite, avec une attention particulière aux limitations des API et des permissions.
- Le système doit fonctionner uniquement lorsque l'ordinateur est allumé et que l'application est lancée.
- Les secrets, jetons d'accès et données personnelles ne doivent jamais être écrits en clair dans les logs.

Ne jamais présenter une fonctionnalité comme fonctionnelle tant qu'elle n'a pas été testée sur un environnement compatible.

## 3. Principes de développement

Agis comme un ingénieur logiciel senior chargé de livrer un produit utilisable.

Avant toute modification :
1. Inspecter le dépôt, les fichiers existants et l'environnement.
2. Identifier les fonctionnalités déjà présentes.
3. Vérifier les versions des dépendances et les API réellement disponibles.
4. Définir les étapes d'implémentation.
5. Signaler les limitations techniques avant de choisir une solution fragile.

Pendant le développement :
- Privilégier une architecture simple, modulaire et testable.
- Éviter les abstractions prématurées.
- Éviter les dépendances inutiles.
- Ne jamais inventer une API de bibliothèque ou un événement système.
- Lire la documentation officielle et le code source des dépendances si nécessaire.
- Ne pas remplacer une fonctionnalité existante sans raison.
- Conserver une séparation nette entre logique métier, intégrations et matériel.
- Tester chaque fonctionnalité indépendamment avant l'intégration globale.

À chaque étape importante, indiquer :
- Ce qui a été implémenté.
- Les fichiers modifiés.
- Les tests exécutés et leurs résultats.
- Les limitations restantes.
- La prochaine étape recommandée.

Ne demande une décision à l'utilisateur que lorsqu'un choix a un impact significatif sur l'architecture, la sécurité, le coût ou l'expérience utilisateur. Pour les détails réversibles, choisis un défaut raisonnable et documente-le.

## 4. Architecture cible

L'application doit être organisée autour de cinq composants indépendants.

### 4.1. Event Sources

Responsable de la récupération des événements externes.

Sources initiales :
- Hooks Claude Code.
- Intégration Microsoft Teams.
- Éventuellement, événements système propres à macOS ou Linux.

Chaque source doit produire des événements normalisés, indépendamment de la manière dont ils sont récupérés.

### 4.2. Event Normalizer

Convertit les événements des différentes sources dans un format interne commun.

Exemple conceptuel :

- `source` : claude ou teams.
- `event_type` : permission_required, task_completed, message_received, call_started, etc.
- `priority` : niveau de priorité.
- `timestamp` : date de réception.
- `requires_acknowledgement` : indique si l'événement doit rester visible jusqu'à acquittement.
- `metadata` : données strictement nécessaires au traitement.

Ne pas conserver le contenu intégral des messages Teams par défaut.

### 4.3. State Manager

Maintient l'état global des notifications.

Responsabilités :
- Stocker les événements actifs.
- Gérer les priorités entre applications.
- Éviter qu'un événement secondaire efface une alerte importante.
- Gérer les événements expirés.
- Déterminer l'état lumineux effectif.
- Gérer les acquittements et les retours à l'état précédent.

Les événements doivent être traités comme des états indépendants, pas comme de simples commandes concurrentes de changement de couleur.

### 4.4. Hue Controller

Expose une interface indépendante de la bibliothèque utilisée pour contrôler l'ampoule.

Fonctions conceptuelles :
- Connecter et déconnecter l'ampoule.
- Vérifier sa disponibilité.
- Allumer et éteindre.
- Modifier couleur et luminosité.
- Appliquer un état lumineux.
- Gérer les erreurs et les tentatives de reconnexion.

Le reste du projet ne doit jamais dépendre directement de l'API d'une bibliothèque Bluetooth.

### 4.5. Local Application

Gère :
- Le démarrage et l'arrêt propres.
- La configuration.
- Les journaux.
- L'état des connexions.
- Le diagnostic des intégrations.
- Les commandes de test.
- L'acquittement des notifications.

Une interface graphique complète n'est pas nécessaire pour le MVP. Une CLI et une configuration lisible suffisent, à condition que le fonctionnement soit facile à diagnostiquer.

## 5. Contrôle de l'ampoule Philips Hue Bluetooth

C'est la première fonctionnalité à valider.

L'ampoule est une Philips Hue White and Color Ambiance Bluetooth de 800 lumens. Le format de douille est E27.

Avant de choisir une bibliothèque :
1. Vérifier son existence, sa maintenance et sa licence.
2. Vérifier la compatibilité réelle avec cette génération d'ampoule.
3. Vérifier la prise en charge de macOS et Linux.
4. Vérifier les versions de Python ou d'autres runtimes requises.
5. Vérifier les permissions Bluetooth nécessaires.
6. Tester la découverte, la connexion et le changement de couleur.
7. Vérifier le comportement lors de la perte de connexion.
8. Documenter les éventuelles limites de connexions concurrentes.

HueBLE peut être étudiée comme piste, mais ne doit pas être considérée comme compatible sans validation de son API et de son fonctionnement réel.

Le Bluetooth intégré de l'ordinateur est le moyen de communication privilégié.

Ne pas implémenter un protocole Bluetooth propriétaire en supposant que les commandes sont connues. Privilégier une bibliothèque documentée et maintenue.

### Critères d'acceptation du contrôleur Hue

- L'ampoule peut être détectée.
- L'application peut se connecter à l'ampoule.
- Une commande permet d'allumer l'ampoule.
- Une commande permet de définir une couleur.
- Les couleurs rouge, orange, vert et bleu peuvent être reproduites de façon suffisamment distincte.
- Une erreur Bluetooth ne fait pas planter l'application.
- Une déconnexion est détectée et signalée.
- Le comportement après reconnexion est documenté et testé.

Si l'ampoule ne peut pas être pilotée directement depuis le système cible, produire un rapport expliquant la cause et les alternatives avant d'imposer un achat matériel.

## 6. Intégration Claude Code

Claude Code est la première intégration applicative à implémenter.

Étudier les hooks officiels disponibles et leur sémantique exacte dans la version installée.

Événements à prendre en charge :

### Permission requise

Lorsqu'une intervention ou une autorisation est nécessaire :
- Créer une alerte de haute priorité.
- Passer la lumière en rouge fixe.
- Maintenir l'alerte tant qu'elle n'est pas résolue ou acquittée selon les règles configurées.

### Tâche terminée

Lorsqu'une tâche se termine :
- Produire un bref signal vert.
- Ne pas écraser une alerte de priorité supérieure.
- Ne pas considérer toute fin d'exécution comme une demande d'intervention.

### Saisie utilisateur nécessaire

Lorsqu'un hook documenté indique que Claude attend une réponse :
- Créer une alerte appropriée.
- Utiliser le rouge ou une autre couleur configurable selon le type d'attente.

### Erreurs et arrêts

Ne pas confondre :
- fin normale ;
- erreur ;
- demande d'autorisation ;
- demande de saisie ;
- arrêt explicite.

Le traitement doit correspondre à la sémantique réelle de chaque hook.

### Configuration

Fournir une procédure permettant d'installer les hooks dans la configuration utilisateur de Claude Code, sans écraser les hooks existants.

Les scripts de hooks doivent être :
- courts ;
- fiables ;
- documentés ;
- rapides ;
- compatibles avec les chemins contenant des espaces ;
- silencieux en fonctionnement normal.

Ne pas exécuter de commande arbitraire issue d'un événement. Valider les données reçues et traiter uniquement les types d'événements autorisés.

## 7. Intégration Microsoft Teams

Cette intégration est plus complexe que celle de Claude Code et doit être traitée séparément.

L'objectif est de récupérer :
- les nouveaux messages ;
- les appels entrants ;
- les appels en cours ;
- les réunions qui commencent ou se terminent.

Ne pas supposer qu'une API unique permet de récupérer tous ces événements.

### Étape 1 : étudier les sources possibles

Évaluer les options suivantes :

1. Notifications natives de macOS ou Linux.
2. Microsoft Graph et ses autorisations.
3. Une intégration locale compatible avec la version de Teams utilisée.
4. Des mécanismes d'événements ou d'extension officiellement documentés.

Comparer les solutions selon :
- compatibilité macOS/Linux ;
- fonctionnement avec le compte Teams de l'utilisateur ;
- permissions nécessaires ;
- disponibilité des événements ;
- latence ;
- maintenance ;
- confidentialité ;
- dépendance à un service externe.

Ne pas utiliser de scraping fragile de l'interface Teams ni contourner les restrictions d'accès.

### Étape 2 : appels et réunions

Détecter les appels et réunions en cours lorsqu'une source fiable le permet.

Une notification de réunion à venir ne doit pas être confondue avec un appel réellement commencé.

### Étape 3 : nouveaux messages

L'objectif est de signaler chaque nouveau message pertinent.

Définir explicitement :
- messages directs ;
- mentions ;
- conversations de groupe ;
- canaux ;
- messages envoyés par l'utilisateur lui-même ;
- notifications dupliquées.

Éviter de générer une alerte pour chaque événement redondant concernant le même message.

Si une API exige une autorisation administrative ou un consentement spécifique, expliquer précisément cette contrainte.

### Confidentialité

- Ne pas stocker les messages complets.
- Ne pas journaliser les jetons d'accès.
- Ne pas transmettre les contenus des conversations à un service tiers non nécessaire.
- Ne demander que les autorisations indispensables.
- Documenter les données récupérées et leur durée de conservation.

Si une fonction Teams ne peut pas être mise en œuvre de manière fiable, l'indiquer clairement et proposer la meilleure solution compatible avec les contraintes du projet.

## 8. Système de couleurs et priorités

La lumière doit représenter l'événement le plus important encore actif.

Configuration initiale recommandée :

| Événement | Couleur | Comportement |
|---|---|---|
| Permission Claude requise | Rouge | Persistant |
| Claude attend une saisie | Rouge | Persistant |
| Appel Teams entrant | Rouge | Persistant pendant la sonnerie |
| Appel ou réunion en cours | Bleu | Persistant pendant l'appel |
| Nouveau message Teams | Orange | 5 secondes |
| Tâche Claude terminée | Vert | 3 secondes |
| Aucun événement actif | Couleur neutre configurable | Persistant |

La durée et les couleurs doivent être configurables.

Ces règles sont des valeurs par défaut, pas des constantes codées en dur.

### Arbitrage

La priorité initiale est :

1. Intervention urgente ou permission Claude.
2. Appel Teams entrant.
3. Appel ou réunion en cours.
4. Autre attente bloquante.
5. Message Teams.
6. Signal de tâche terminée.
7. État de repos.

Une réunion en cours ne doit pas nécessairement masquer un appel entrant. Définir une stratégie explicite pour les événements simultanés.

Un message Teams ne doit jamais effacer une demande d'autorisation Claude.

Une tâche Claude terminée ne doit pas remplacer un état rouge actif.

Les événements temporaires doivent expirer sans effacer les événements persistants.

Le gestionnaire d'état doit être déterministe : pour un ensemble donné d'événements actifs, le résultat lumineux doit être prévisible.

## 9. Configuration utilisateur

Prévoir un fichier de configuration local lisible, avec des valeurs par défaut.

Il doit permettre de régler :
- les couleurs ;
- la luminosité ;
- les durées ;
- les priorités ;
- les sources activées ;
- le comportement en cas de déconnexion ;
- les notifications à acquitter ;
- les préférences de démarrage.

Les secrets doivent être conservés séparément du fichier de configuration et exclus du dépôt Git.

Fournir un exemple de configuration sans secret.

Ne pas ajouter une base de données pour le MVP si des structures en mémoire suffisent. La persistance des événements peut être ajoutée ultérieurement si un besoin réel est identifié.

## 10. Architecture multiplateforme

Ne pas supposer que les mécanismes Bluetooth, notifications ou démarrage automatique sont identiques sous macOS et Linux.

Créer des adaptateurs spécifiques uniquement lorsque cela est nécessaire.

Pour macOS :
- documenter les permissions Bluetooth ;
- documenter les limitations liées à l'exécution en arrière-plan ;
- vérifier les mécanismes de notifications disponibles.

Pour Linux :
- documenter les dépendances Bluetooth ;
- documenter les permissions et services nécessaires ;
- éviter de dépendre d'un environnement de bureau particulier sans le signaler.

Les fonctionnalités qui ne sont pas disponibles sur les deux plateformes doivent être explicitement marquées.

Le code commun doit rester indépendant du système d'exploitation autant que possible.

## 11. Tests obligatoires

### Tests unitaires

Tester :
- la normalisation des événements ;
- le classement des priorités ;
- l'expiration des alertes ;
- les acquittements ;
- les doublons ;
- les événements simultanés ;
- les transitions entre états ;
- la configuration ;
- la gestion des erreurs.

### Tests d'intégration

Tester :
- la réception d'un événement Claude ;
- la traduction en état lumineux ;
- la transmission au contrôleur Hue ;
- les pertes et reprises de connexion ;
- les événements Teams simulés ;
- les événements Teams réels lorsque les autorisations sont disponibles.

Créer un faux contrôleur Hue pour les tests afin de tester la logique sans ampoule physique.

Créer des sources d'événements simulées pour permettre le développement avant que toutes les intégrations soient disponibles.

Ne pas déclarer un test matériel réussi si seule une simulation a été exécutée.

### Tests manuels

Fournir une checklist de validation pour macOS et Linux.

Elle doit permettre de vérifier :
1. Le démarrage.
2. La connexion Bluetooth.
3. Les changements de couleur.
4. Les événements Claude.
5. Les événements Teams.
6. Les priorités.
7. La déconnexion et la reconnexion.
8. L'arrêt propre.
9. Le redémarrage de l'application.

## 12. Commandes et diagnostic

Prévoir des commandes simples, adaptées au langage retenu, pour :

- démarrer l'application ;
- vérifier la configuration ;
- détecter les ampoules ;
- tester chaque couleur ;
- simuler un événement Claude ;
- simuler un événement Teams ;
- afficher l'état courant ;
- vérifier la santé des intégrations.

La syntaxe définitive doit être documentée dans le README.

Un mode de simulation doit permettre de tester l'ensemble du système sans modifier l'ampoule réelle.

## 13. Sécurité et robustesse

- Ne jamais enregistrer de secrets dans Git.
- Ne pas exposer de serveur réseau si ce n'est pas nécessaire.
- Si un webhook local est utilisé, limiter son accès au strict nécessaire.
- Vérifier les événements reçus.
- Gérer les timeouts et les erreurs de Bluetooth.
- Prévoir une fermeture propre.
- Éviter les boucles de reconnexion agressives.
- Ne pas consommer inutilement le CPU ou la batterie.
- Éviter que les logs contiennent des données privées.
- Ne jamais bloquer un hook Claude Code sur une opération Bluetooth lente.
- Éviter les changements de couleur répétés qui pourraient surcharger l'ampoule.

## 14. Documentation attendue

Maintenir un README qui contient :
- présentation du projet ;
- architecture ;
- prérequis ;
- installation macOS ;
- installation Linux ;
- configuration Bluetooth ;
- appairage de l'ampoule si nécessaire ;
- installation des hooks Claude Code ;
- configuration de Teams ;
- démarrage et arrêt ;
- commandes de diagnostic ;
- dépannage ;
- limites connues ;
- confidentialité ;
- tests exécutés.

Documenter les intégrations facultatives séparément.

Le projet doit pouvoir être repris par un autre développeur sans dépendre de connaissances implicites.

## 15. Ordre de réalisation

Ne pas implémenter toutes les fonctionnalités en une seule fois.

### Phase 0 — Audit et faisabilité

- Inspecter le dépôt.
- Identifier le langage et les outils déjà utilisés.
- Vérifier les bibliothèques de contrôle Hue Bluetooth.
- Vérifier les possibilités réelles de macOS et Linux.
- Évaluer les options Teams.
- Rédiger un plan de réalisation et signaler les risques.

Ne pas commencer par une refonte architecturale complète.

### Phase 1 — MVP Bluetooth

- Implémenter le contrôleur Hue.
- Détecter l'ampoule.
- Tester l'allumage et les couleurs.
- Ajouter un mode de simulation.
- Documenter l'installation.

Cette phase doit fonctionner avant de passer aux intégrations applicatives.

### Phase 2 — Claude Code

- Ajouter les hooks.
- Normaliser les événements.
- Implémenter le gestionnaire d'état.
- Tester les permissions et les fins de tâche.
- Vérifier que les hooks n'interrompent pas le travail de Claude Code.

### Phase 3 — Teams

- Implémenter une source d'événements fiable.
- Commencer par les appels et réunions.
- Ajouter les nouveaux messages.
- Documenter les autorisations et les limitations.
- Tester les doublons et les événements simultanés.

### Phase 4 — Fiabilité

- Ajouter la reconnexion.
- Finaliser les priorités.
- Améliorer les diagnostics.
- Tester les deux systèmes d'exploitation.
- Documenter les cas limites.

### Phase 5 — Améliorations éventuelles

Uniquement après un MVP fiable :
- petite interface graphique ;
- lancement automatique au démarrage de session ;
- acquittement physique ;
- statistiques ;
- profils de couleurs ;
- autres applications.

## 16. Définition du MVP terminé

Le MVP est considéré comme terminé lorsque :

- L'application fonctionne localement sur au moins un système cible.
- Elle pilote effectivement l'ampoule Hue Bluetooth sans Bridge.
- Elle reçoit les événements Claude Code documentés.
- Elle distingue les demandes d'intervention des tâches terminées.
- Elle maintient correctement les priorités.
- Elle possède un mode de simulation.
- Elle ne plante pas lorsqu'une connexion échoue.
- L'installation et l'utilisation sont documentées.
- Les limitations de l'intégration Teams sont connues et explicites.

La compatibilité avec le deuxième système d'exploitation et la réception des messages Teams doivent ensuite être validées avant de déclarer le projet entièrement terminé.

## 17. Première action attendue de Claude Code

Commence par auditer le dépôt et la machine.

Ne génère pas immédiatement l'intégralité de l'application.

Présente :
1. L'état actuel du projet.
2. Les technologies déjà présentes.
3. Les possibilités de pilotage direct de l'ampoule Hue Bluetooth.
4. Les options réalistes pour récupérer les événements Teams sur macOS et Linux.
5. Les risques techniques majeurs.
6. Le plan minimal permettant d'obtenir rapidement une ampoule qui change réellement de couleur en réponse à un événement Claude Code.

Ensuite, implémente la première étape validée, teste-la et documente le résultat avant de poursuivre.
