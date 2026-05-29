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

Hermès dispose d’un accès SQL read-only à Postgres.

L’objectif est de lui permettre d’interroger librement la mémoire métier du système : emails ingérés, résumés, digests, feedbacks, sources, signaux, historique et états de traitement.

Hermès peut utiliser SQL pour répondre à des questions analytiques, par exemple :

* combien d’articles ont été résumés sur une période ;
* quelles sources produisent le plus de signaux utiles ;
* quels sujets reviennent le plus souvent ;
* quelles différences apparaissent entre deux périodes ;
* quels contenus ont été ignorés ou inclus dans les digests.

Hermès va apprendre le modèle de données afin de savoir quelles tables consulter.

Le choix initial est de lui exposer les tables métier directement, plutôt que de créer des vues dédiées. Ce choix privilégie la simplicité et la flexibilité.

Compromis :

* gain : Hermès est plus autonome pour explorer les données ;
* gain : moins d’API métier à maintenir ;
* gain : plus simple à faire évoluer pendant l’expérimentation ;
* sacrifice : moins de contrôle fin sur ce qu’Hermès peut voir ;
* sacrifice : risque de requêtes inefficaces ou trop larges ;
* sacrifice : plus grande dépendance à la qualité du schéma et de sa documentation.

Garde-fous minimaux :

* rôle Postgres strictement read-only ;
* accès limité aux tables métier, jamais aux secrets ;
* timeout SQL ;
* limite de taille sur les résultats retournés ;
* logs des requêtes ou au moins des intentions de requêtes ;
* interdiction des écritures directes en base par Hermès.

### Usage de Python par Hermès

Hermès peut utiliser Python pour analyser les résultats de requêtes s’il en a besoin.

Cet usage doit rester orienté analyse locale : agrégation, nettoyage de données, comparaison de périodes, préparation d’un résumé.

Compromis :

* gain : Hermès peut faire des analyses plus riches que du SQL simple ;
* gain : meilleure flexibilité pour les questions exploratoires ;
* sacrifice : Python devient une capacité puissante qui doit être encadrée ;
* risque : accès filesystem, réseau ou exécution non désirée si le sandbox n’est pas clair.

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
