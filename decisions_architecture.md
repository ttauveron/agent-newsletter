Hermès doit être traité comme un agent potentiellement manipulable.

Le système ne cherche pas à garantir qu’Hermès ne subira jamais de prompt injection. Il cherche à garantir qu’une compromission logique d’Hermès ait un impact limité.

La défense principale est le confinement :

- exécution non-root ;
- filesystem limité ;
- secrets non accessibles ;
- accès réseau sortant restreint ;
- accès base de données en lecture seule ;
- absence d’accès direct à Gmail ;
- absence d’envoi email direct ;
- dépendances installées au build, pas à l’exécution ;
- actions externes exécutées par newsletter-engine après validation.

---
### Accès d’Hermès aux données

**Décision finale** : Hermès accède directement à Postgres via le rôle `hermes_readonly`. Hermes Agent dispose d’outils natifs (terminal, Python) qui lui permettent d’exécuter des requêtes SQL. Le newsletter-engine ne fait pas d’intermédiaire pour les lectures.

On lui fournit le schéma complet des tables métier (`emails`, `summaries`, `digests`, `user_messages`, `audit_logs`) et il se débrouille pour construire ses requêtes.

Compromis :

* gain : aucun endpoint de query à maintenir dans le newsletter-engine ;
* gain : flexibilité maximale pour les requêtes analytiques complexes ;
* gain : Hermès peut itérer sur ses requêtes de manière autonome ;
* garde-fou principal : rôle `hermes_readonly` strictement en lecture, jamais accès aux tables internes sensibles.

### Réveil d’Hermès

**Mécanisme** : Hermes Agent expose nativement un **webhook platform** configurable dans `hermes/config.yaml`. Newsletter-engine ne POSTe pas sur un endpoint générique mais sur des routes nommées qui ont chacune un template de prompt pré-configuré.

Deux webhooks configurés :

```
POST http://hermes:8642/webhooks/daily-digest   → inject: { date, email_count }
POST http://hermes:8642/webhooks/user-message   → inject: { message_id, subject, content }
```

Les données JSON sont injectées dans les templates de prompt via des variables (`{date}`, `{subject}`, etc.). Hermes Agent expose aussi `POST /v1/runs` (async avec SSE) et `POST /v1/chat/completions` (OpenAI-compatible) si besoin d’appels directs.

Compromis :

* gain : la logique du prompt est dans la config Hermes, pas dans newsletter-engine ;
* gain : facile d’ajouter de nouveaux événements sans toucher newsletter-engine ;
* sacrifice : nécessite de maintenir `hermes/config.yaml`.

### Usage de Python par Hermès

Hermès peut utiliser Python (via ses outils natifs) pour analyser les résultats de requêtes SQL : agrégation, comparaison de périodes, préparation d’un résumé. C’est un outil natif de Hermes Agent, pas quelque chose à implémenter.

Compromis :

* gain : analyses plus riches que du SQL simple ;
* gain : flexibilité pour les questions exploratoires ;
* risque : exécution Python dans le conteneur Hermes — confinement réseau et filesystem important (Phase 5).

### Accès web

Hermès utilise ses outils natifs de web fetch/search. Le contrôle des domaines autorisés est géré au niveau réseau Docker (iptables ou proxy sortant), pas via un endpoint newsletter-engine.

Compromis :

* gain : plus simple, aucun endpoint `/hermes/fetch-web` à maintenir ;
* gain : Hermès accède directement sans latence intermédiaire ;
* sacrifice : whitelist gérée en config infrastructure plutôt qu’en code — moins flexible à chaud ;
* garde-fou : règles réseau Docker strictes (Phase 5).

### Settings runtime en base de données

Les paramètres modifiables à chaud (heure du digest, fuseau, etc.) sont stockés dans une table `app_settings` en DB plutôt que dans `settings.yaml`.

Hermès peut lire ces settings via SQL (rôle `hermes_readonly`). Pour les modifier, il passe par `POST /hermes/preferences` sur newsletter-engine — qui écrit en DB **et** applique le changement à chaud (ex : reschedule APScheduler).

`settings.yaml` reste pour la configuration statique (adresses email, sources whitelist) qui ne change pas en cours d’exécution.

Compromis :

* gain : Hermès peut lire l’état courant des settings sans endpoint dédié ;
* gain : les modifications persistent sans redémarrage ;
* sacrifice : migration DB nécessaire pour ajouter un setting.

### Endpoints newsletter-engine exposés à Hermès

Liste finale, après révisions :

| Endpoint | Rôle | Garde-fous |
|---|---|---|
| `POST /actions/send-digest` | Envoie le digest par email + marque `digest_sent` | Destinataire = `authorized_user_address` |
| `POST /actions/send-reply` | Répond à un `UserMessage` + marque `answered` | Idem |
| `POST /hermes/preferences` | Met à jour `app_settings` en DB et/ou fichiers Markdown | Diff journalisé, clés autorisées uniquement |

Tout le reste (lecture des emails, requêtes analytiques, accès web) est fait directement par Hermès via ses outils natifs.

### Configuration utilisateur

Hermès peut modifier directement les fichiers Markdown de préférences utilisateur.

Ces fichiers peuvent contenir :

* profil utilisateur ;
* intérêts ;
* sujets à ignorer ;
* style de digest ;
* préférences apprises ;
* règles qualitatives de priorisation.

Le feedback utilisateur est conservé brut pour audit, puis Hermès décide comment le consolider dans la mémoire Markdown.

Compromis :

* gain : apprentissage simple et inspectable ;
* gain : pas besoin de construire une interface de configuration ;
* gain : l’utilisateur peut relire et corriger la mémoire ;
* sacrifice : Hermès peut mal interpréter un feedback et modifier la mémoire de manière indésirable ;
* garde-fou recommandé : garder un historique des changements Markdown ou un journal de diff.

### Scheduler

Le scheduler doit être implémenté de la manière la plus simple possible.

Options acceptables :

* scheduler intégré au newsletter-engine ;
* cron externe ;
* service séparé seulement si nécessaire.

Le système doit simplement garantir qu’un événement `daily_digest_due` est déclenché à l’heure configurée.

### Gmail

Le système utilise une seule adresse Gmail dédiée pour :

* recevoir les newsletters ;
* recevoir les messages utilisateur ;
* envoyer les digests ;
* envoyer les réponses d’Hermès.

Les emails provenant de l’adresse personnelle autorisée de l’utilisateur sont traités comme des messages conversationnels.

Les emails provenant d’expéditeurs whitelistés sont traités comme newsletters.

Les emails provenant d’expéditeurs non whitelistés sont laissés non lus et ne sont pas traités.

### Whitelist des expéditeurs

La whitelist est une configuration simple.

Elle doit permettre d’indiquer :

* expéditeur exact ;
* catégorie déterministe ;
* comportement par défaut.

Exemple :

```yaml
sources:
  - match: "newsletter@example.com"
    category: "cloud_security"

  - match_domain: "linkedin.com"
    category: "market_signal"
```

### Contenu stocké

Le système stocke une version texte nettoyée de l’email, avec le HTML supprimé ou fortement nettoyé.

L’objectif est de réduire le bruit et de limiter les tokens envoyés aux modèles.

Les liens présents dans l’email doivent être conservés dans le contenu nettoyé lorsque possible.

### Traitement des liens

Les liens présents dans les newsletters sont conservés.

Hermès peut décider qu’un lien semble pertinent, mais l’accès web reste limité.

Aucun composant ne doit accéder librement à Internet.

### Accès web

L’accès web whitelisté est inclus dans la v1.

Hermès doit savoir explicitement que son accès web est limité à certains domaines.

L’accès web doit passer par une fonction ou un composant contrôlé, et non par une navigation libre.

Compromis :

* gain : Hermès peut approfondir certains contenus ;
* gain : meilleure capacité à analyser des newsletters qui ne contiennent que des extraits ;
* sacrifice : surface de sécurité plus large ;
* sacrifice : risque supplémentaire de prompt injection via contenu web ;
* garde-fou : allowlist stricte de domaines, limite de taille, extraction texte, pas d’exécution de contenu actif.

### Feedback utilisateur

Le feedback utilisateur est stocké brut pour audit.

Hermès peut ensuite décider comment le consolider dans les fichiers Markdown de préférences.

Exemples :

* “ce sujet m’intéresse” ;
* “ignore ce genre de contenu” ;
* “fais plus court” ;
* “je veux plus de signaux marché” ;
* “les annonces vendor ne m’intéressent que si elles touchent IAM ou compliance”.

Le système doit conserver :

* le feedback original ;
* la date ;
* le message ou digest concerné ;
* l’interprétation faite par Hermès ;
* les changements éventuels dans la mémoire Markdown.

### États de processing

Granularité proposée :

Pour les emails :

* `received` : email détecté par le newsletter-engine ;
* `ingested` : email stocké en base ;
* `cleaned` : contenu texte extrait et nettoyé ;
* `summarized` : résumé individuel généré ;
* `ready_for_hermes` : email prêt à être considéré par Hermès ;
* `selected_for_digest` : Hermès a décidé de l’inclure ;
* `ignored_by_hermes` : Hermès a décidé de ne pas l’inclure ;
* `sent_in_digest` : l’item a été envoyé dans un digest ;
* `archived` : l’item ne nécessite plus de traitement.

Pour les messages utilisateur :

* `user_message_received` ;
* `passed_to_hermes` ;
* `answered` ;
* `feedback_recorded` ;
* `preference_updated`.

Pour les digests :

* `digest_due` ;
* `digest_generation_requested` ;
* `digest_generated` ;
* `digest_sent` ;
* `digest_failed`.

### Audit logs minimaux

Le système doit journaliser assez pour comprendre ce qui s’est passé, sans devenir une usine à logs.

Logs recommandés :

* email ingéré : message id, expéditeur, sujet, date ;
* décision de whitelist : accepté ou ignoré ;
* état de processing ;
* modèle utilisé pour résumé ou digest ;
* coût approximatif ou nombre de tokens si disponible ;
* décision d’Hermès : inclus, ignoré, pourquoi ;
* digest envoyé : date, destinataire, item ids inclus ;
* feedback utilisateur reçu ;
* modification de préférence ;
* erreur de workflow ;
* action email sortante : destinataire, sujet, timestamp.

Ne pas logger inutilement :

* tokens OAuth ;
* secrets ;
* contenu complet répété partout ;
* headers email sensibles non nécessaires ;
* données personnelles sans utilité d’audit.
