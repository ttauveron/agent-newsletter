# Vision & Spécification initiale — Hermès Newsletter Intelligence Agent

## 1. Objectif

L’objectif est de construire un agent nommé **Hermès** qui suit l’actualité pertinente pour l’utilisateur, revalorise les newsletters non lues, et extrait des signaux utiles du marché.

Hermès doit permettre à l’utilisateur de recevoir un résumé régulier des nouvelles importantes, mais aussi de dialoguer avec l’agent afin d’affiner progressivement ses préférences.

Le système doit être capable de :

* récupérer des newsletters depuis une adresse email dédiée ;
* filtrer les sources autorisées ;
* résumer les contenus utiles ;
* ignorer ou minimiser les contenus peu pertinents ;
* extraire des signaux marché ;
* générer un digest personnalisé ;
* recevoir du feedback utilisateur ;
* adapter les préférences utilisateur au fil du temps ;
* garder une traçabilité des contenus, décisions et actions.

## 2. Principes d’architecture

L’architecture repose sur trois composants principaux :

```text
docker-compose
  ├── hermes
  ├── newsletter-engine
  └── postgres
```

### 2.1 Hermès

Hermès est le cerveau du système.

Il ne récupère pas directement les emails. Il ne gère pas directement les accès Gmail. Il ne fait pas lui-même les opérations techniques dangereuses.

Son rôle est de :

* comprendre les demandes de l’utilisateur ;
* lire l’état métier exposé en base de données ;
* raisonner sur les digests et les signaux ;
* décider quoi communiquer à l’utilisateur ;
* adapter les préférences utilisateur ;
* demander certaines actions au `newsletter-engine` via une API contrôlée.

Hermès peut être réveillé par le `newsletter-engine` dans deux cas principaux :

1. l’heure planifiée du digest journalier est atteinte ;
2. un email provenant de l’adresse personnelle autorisée de l’utilisateur est reçu.

Dans le premier cas, Hermès prépare le résumé des actualités à envoyer.

Dans le second cas, Hermès traite le message de l’utilisateur comme une demande conversationnelle ou comme du feedback.

Hermès peut interroger la base de données en lecture seule sur les données métier exposées. Il peut, par exemple, répondre à des questions comme :

* combien d’articles ont été résumés sur la dernière année ;
* quels sujets reviennent le plus souvent ;
* quelles différences apparaissent dans les signaux de marché depuis six mois ;
* quelles sources produisent le plus de contenu utile ;
* quels sujets ont été ignorés ou dépriorisés.

Hermès peut aussi accéder à Internet, mais seulement vers des domaines explicitement autorisés.

### 2.2 Newsletter Engine

Le `newsletter-engine` est la couche d’exécution technique.

Son rôle est de :

* récupérer les emails depuis l’adresse email dédiée ;
* lire uniquement les emails non lus ou non traités ;
* vérifier que l’émetteur est autorisé ou pertinent ;
* stocker les emails dans Postgres ;
* marquer les emails comme lus ou traités pour éviter les doublons ;
* produire une première data augmentation des emails, par exemple résumé court, extraction des titres, métadonnées, source, catégorie déterministe ;
* détecter les emails provenant de l’utilisateur ;
* réveiller Hermès si une demande utilisateur est reçue ;
* réveiller Hermès lorsqu’un digest journalier doit être généré ;
* envoyer à l’utilisateur les emails préparés par Hermès ;
* mettre à jour les états de processing.

Le `newsletter-engine` peut utiliser des workflows déterministes et, si nécessaire, des modèles peu coûteux pour les tâches simples.

Exemples de tâches déterministes :

* classification par adresse email ou domaine expéditeur ;
* déduplication ;
* filtrage par source whitelistée ;
* routage entre newsletter et message utilisateur ;
* gestion des états de traitement.

Exemples de tâches pouvant utiliser un petit modèle :

* résumé court d’un email ;
* extraction des points clés ;
* détection de bruit marketing ;
* proposition de tags.

### 2.3 Postgres

Postgres sert de jonction entre Hermès et le `newsletter-engine`.

La base de données contient :

* les emails originaux ;
* les métadonnées ;
* les résumés intermédiaires ;
* les digests générés ;
* les décisions d’Hermès ;
* les feedbacks utilisateur ;
* les préférences utilisateur ;
* les logs d’audit ;
* les états de traitement.

Deux utilisateurs Postgres distincts doivent être prévus :

* un utilisateur pour le `newsletter-engine` ;
* un utilisateur pour Hermès.

Hermès doit avoir un accès **read-only** aux données métier exposées.

Le `newsletter-engine` doit avoir les droits nécessaires pour ingérer, enrichir et mettre à jour les états de traitement.

L’accès d’Hermès doit idéalement se faire via des vues ou des tables métier exposées, et non via les tables internes sensibles.

## 3. Flux principal : digest journalier

Le flux journalier cible est le suivant :

```text
1. Le scheduler ou newsletter-engine détecte que l’heure du digest est atteinte.
2. Newsletter-engine vérifie les nouveaux emails pertinents.
3. Newsletter-engine récupère les emails whitelistés non traités.
4. Newsletter-engine stocke les emails originaux en base.
5. Newsletter-engine enrichit les emails avec un résumé ou des métadonnées.
6. Newsletter-engine marque ces éléments comme prêts pour Hermès.
7. Newsletter-engine réveille Hermès.
8. Hermès interroge la base et lit les éléments prêts.
9. Hermès sélectionne ce qui mérite d’être communiqué.
10. Hermès produit un digest personnalisé.
11. Hermès transmet le contenu du digest au newsletter-engine.
12. Newsletter-engine envoie le digest par email à l’utilisateur.
13. Newsletter-engine met à jour l’état de traitement pour éviter les doublons.
14. Les décisions et actions sont journalisées.
```

Le digest doit être court, utile et personnalisé. Il ne doit pas tout résumer. Il doit surtout faire gagner du temps à l’utilisateur.

## 4. Flux conversationnel : message utilisateur

L’utilisateur peut écrire directement à l’adresse email dédiée d’Hermès.

Si un email reçu provient de l’adresse email personnelle autorisée de l’utilisateur, le `newsletter-engine` ne le traite pas comme une newsletter.

Il déclenche un workflow spécifique :

```text
1. Newsletter-engine reçoit un email.
2. Il détecte que l’expéditeur est l’utilisateur autorisé.
3. Il stocke le message en base.
4. Il réveille Hermès avec le message utilisateur.
5. Hermès interprète la demande.
6. Hermès peut :
   - répondre à l’utilisateur ;
   - modifier ou proposer une modification des préférences ;
   - changer la configuration autorisée ;
   - demander plus de contexte ;
   - interroger la mémoire des newsletters.
7. Newsletter-engine envoie la réponse préparée par Hermès.
8. L’action est journalisée.
```

Exemples de messages utilisateur :

```text
Fais-moi un résumé des nouvelles de cette semaine.
```

```text
Ignore les annonces produit trop marketing.
```

```text
Je veux plus de signaux liés à IAM et aux banques suisses.
```

```text
Quels sujets reviennent le plus depuis six mois ?
```

```text
Change le digest quotidien à 08:00.
```

## 5. Configuration utilisateur

La configuration doit permettre de personnaliser Hermès sans hardcoder le profil de l’utilisateur dans le code.

Exemples d’éléments configurables :

* adresse email personnelle autorisée ;
* adresse email dédiée à Hermès ;
* sources newsletter whitelistées ;
* heure du digest journalier ;
* fuseau horaire ;
* préférences éditoriales ;
* sujets d’intérêt ;
* sujets à ignorer ;
* profil utilisateur ;
* domaines web autorisés pour navigation éventuelle.

Les préférences et le profil peuvent être stockés au format Markdown, afin de rester lisibles, versionnables et modifiables.

Hermès peut proposer ou appliquer certaines modifications de configuration, selon les droits qui lui sont accordés.

## 6. Sécurité

Le modèle de sécurité repose sur la séparation des responsabilités.

### 6.1 Hermès

Hermès doit être limité dans ses capacités.

Il peut :

* lire les données métier en base ;
* interroger les vues ou tables explicitement exposées ;
* lire et proposer des changements de configuration utilisateur ;
* appeler certaines fonctions de l’API `newsletter-engine` ;
* accéder à Internet uniquement via des domaines whitelistés, si cette capacité est activée.

Il ne doit pas :

* accéder aux tokens Gmail ;
* récupérer directement les emails ;
* envoyer directement des emails sans passer par le `newsletter-engine` ;
* écrire directement dans les tables internes sensibles ;
* modifier les états de processing sans passer par l’API prévue ;
* accéder librement à Internet ;

### 6.2 Newsletter Engine

Le `newsletter-engine` possède les capacités techniques.

Il peut :

* accéder à Gmail ;
* récupérer les emails ;
* envoyer des emails à l’utilisateur ;
* écrire les emails et états en base ;
* exécuter les workflows déterministes ;
* appeler un modèle peu coûteux pour certaines étapes d’enrichissement.

Il doit valider les actions demandées par Hermès avant exécution.

Par exemple, si Hermès demande l’envoi d’un email, le `newsletter-engine` doit vérifier que le destinataire est bien l’utilisateur autorisé.

### 6.3 Postgres

Postgres doit appliquer des droits séparés.

Un rôle `newsletter_engine` peut écrire les données d’ingestion et de processing.

Un rôle `hermes_readonly` peut lire les données métier exposées, mais ne peut pas modifier les emails, états internes ou logs techniques.

Les écritures sensibles doivent passer par des fonctions ou APIs contrôlées.

## 7. Traçabilité et audit

Le système doit garder suffisamment d’information pour comprendre ce qui s’est passé.

Il faut conserver :

* l’email original ;
* les métadonnées de l’email ;
* le résumé généré ;
* les décisions de routage ;
* les décisions d’Hermès ;
* le digest envoyé ;
* les feedbacks utilisateur ;
* les changements de configuration ;
* les erreurs de workflow ;
* les timestamps des actions importantes.

L’objectif est de pouvoir répondre à des questions comme :

* pourquoi cet email a été inclus dans le digest ;
* pourquoi cet email a été ignoré ;
* quel modèle ou workflow a produit tel résumé ;
* quel feedback utilisateur a changé telle préférence ;
* quel digest a été envoyé à telle date.

## 8. Exemple de cas d’usage

L’utilisateur fait de la veille en sécurité informatique, cloud security, IAM, platform engineering, et vit à Zurich.

Hermès reçoit une newsletter ou alerte job provenant d’une source whitelistée, par exemple LinkedIn Jobs ou Indeed.

Un email mentionne :

```text
UBS recrute un Cloud Security Engineer à Zurich.
```

Le `newsletter-engine` ingère l’email, détecte la source et extrait les informations principales.

Hermès peut interpréter ce contenu comme un signal de marché :

* une grande banque suisse recrute sur le sujet cloud security ;
* le besoin est localisé à Zurich ;
* cela peut indiquer une demande active sur ce segment ;
* ce signal peut être utile pour le positionnement, la prospection ou la préparation d’entretien.

Hermès peut ensuite inclure dans le digest :

```text
Signal marché : UBS recrute un Cloud Security Engineer à Zurich. Cela confirme une demande locale sur cloud security dans la banque suisse. À surveiller : compétences demandées, wording de l’offre, technologies mentionnées.
```

## 9. Exigences non fonctionnelles

### Coût

Le coût doit rester minimal.

Principes :

* utiliser des workflows déterministes lorsque c’est suffisant ;
* éviter les appels LLM inutiles ;
* utiliser des modèles moins chers pour les tâches simples ;
* réserver les modèles plus coûteux aux synthèses finales ou aux raisonnements à forte valeur ;
* éviter les composants cloud managés coûteux au départ.

### Sécurité

Le projet doit être conçu comme un blueprint de sécurité pour agents IA.

Principes :

* séparation des services ;
* séparation des rôles DB ;
* accès read-only pour Hermès sur les données métier ;
* actions externes contrôlées par le `newsletter-engine` ;
* whitelisting des sources et domaines ;
* audit logs ;
* aucun accès libre aux secrets ;

### Simplicité opérationnelle

Le système doit tourner via Docker Compose.

## 10. Points à clarifier

Les points suivants doivent être clarifiés avant implémentation complète :

1. Est-ce que Hermès interroge Postgres via SQL read-only direct, via une API, ou via un mélange des deux ?
2. Est-ce que les données exposées à Hermès sont des tables directes ou des vues dédiées ?
3. Est-ce que Hermès peut modifier directement les fichiers Markdown de préférences, ou doit-il proposer des changements validés par un workflow ?
4. Où vit le scheduler : dans `newsletter-engine`, dans un service séparé, ou via cron externe ?
5. Quels scopes Gmail sont nécessaires pour lire les emails et envoyer les digests ?
6. Est-ce qu’on utilise une seule adresse Gmail pour recevoir les newsletters et envoyer les réponses, ou deux adresses séparées ?
7. Quelle est la politique exacte de whitelist des expéditeurs ?
8. Que fait-on des emails non whitelistés : ignorer, archiver, stocker comme rejetés, ou laisser non lus ?
9. Quel niveau de contenu original doit être stocké : texte nettoyé seulement, HTML complet, ou les deux ?
10. Est-ce qu’on traite les liens dans les newsletters, ou seulement le contenu de l’email ?
11. Est-ce que l’accès web whitelisté est inclus en v1 ou repoussé ?
12. Comment éviter qu’une newsletter injecte des instructions malveillantes dans le contexte d’Hermès ?
13. Quelle est la stratégie de feedback : stockage brut, consolidation périodique, ou modification immédiate des préférences ?
14. Quelle est la granularité des états de processing ?
15. Quels logs sont nécessaires pour l’audit sans stocker trop d’informations sensibles ?
