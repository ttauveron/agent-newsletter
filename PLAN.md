# Plan d'implémentation — Hermès Newsletter Intelligence Agent

## Stack technologique

| Composant | Technologie |
|---|---|
| `newsletter-engine` | Python, FastAPI, Gmail API, APScheduler, SQLAlchemy |
| `hermes` | [Hermes Agent](https://github.com/NousResearch/hermes-agent) (NousResearch), provider-agnostic |
| `postgres` | PostgreSQL 16, deux rôles distincts |
| Orchestration | Docker Compose |

Hermes Agent est un projet open-source de NousResearch. Il fonctionne avec n'importe quel endpoint OpenAI-compatible (Anthropic, OpenRouter, Ollama, NVIDIA NIM, etc.) — le choix du provider est une question de configuration, pas de code. Le newsletter-engine reste un pipeline déterministe sans LangGraph.

---

## Phase 1 — Infrastructure & base de données

**Objectif** : socle opérationnel avant tout code métier.

### Docker Compose

- 3 services : `hermes`, `newsletter-engine`, `postgres`
- Healthchecks sur chaque service
- Variables d'environnement via `.env` (jamais de secrets en dur)

### Schéma Postgres

| Table | Contenu |
|---|---|
| `emails` | Email original, texte nettoyé, métadonnées, processing state |
| `summaries` | Résumé court par email, modèle utilisé, tokens consommés |
| `digests` | Digest généré, liste des email ids inclus, état d'envoi |
| `user_messages` | Messages conversationnels de l'utilisateur |
| `audit_logs` | Toutes les actions importantes (structuré JSON) |
| `processing_events` | Log des transitions d'état avec timestamp |

### Rôles Postgres

- `newsletter_engine` : read/write sur les tables
- `hermes_readonly` : SELECT uniquement sur les tables métier (pas les tokens, secrets, états internes)

### Migrations

- Alembic pour la gestion des migrations

---

## Phase 2 — Newsletter Engine

**Objectif** : ingestion, enrichissement, déclenchement d'Hermès.

### 2a — Gmail & ingestion

- OAuth2 Gmail (scopes `gmail.modify` : lecture + marquage lu)
- Polling des emails non lus
- Filtrage par whitelist (`config/sources.yaml`)
  - Expéditeur exact ou domaine
  - Emails non whitelistés : laissés non lus, non traités
  - Emails de l'utilisateur autorisé : routés vers flux conversationnel
- Stockage email original + extraction texte nettoyé (BeautifulSoup, liens conservés)
- Transitions : `received → ingested → cleaned`

### 2b — Enrichissement

- Résumé court via Haiku 4.5 (modèle léger)
- Extraction de tags et catégorie (ou règles déterministes si suffisant)
- Transitions : `cleaned → summarized → ready_for_hermes`

### 2c — Scheduler

- APScheduler intégré dans newsletter-engine
- Événement `daily_digest_due` déclenché à l'heure configurée
- Détection des messages utilisateur (expéditeur = adresse personnelle autorisée)

### 2d — API interne (FastAPI)

Endpoints appelables par Hermès uniquement (réseau Docker interne) :

| Endpoint | Rôle |
|---|---|
| `POST /actions/send-email` | Envoi email avec validation du destinataire |
| `POST /actions/mark-digest-sent` | Mise à jour état digest |
| `POST /actions/update-processing-state` | Transition d'état sur un email |
| `POST /trigger/hermes` | Wake-up d'Hermès |

Le newsletter-engine valide chaque action avant exécution (ex : destinataire forcément l'utilisateur autorisé).

---

## Phase 3 — Hermès (Hermes Agent)

**Objectif** : déployer et configurer Hermes Agent comme cerveau du système.

### 3a — Déploiement de Hermes Agent

Hermes Agent (NousResearch) remplace un agent Claude custom. Il est déployé comme service Docker et configuré pour :

- **Provider LLM** : n'importe quel endpoint OpenAI-compatible (configurable via `.env`)
- **Mémoire** : Postgres (rôle `hermes_readonly` pour les données métier)
- **Outils** : endpoints HTTP exposés par le newsletter-engine

Les outils exposés par le newsletter-engine pour Hermes Agent :

| Endpoint | Rôle | Garde-fous |
|---|---|---|
| `GET /hermes/emails` | Emails `ready_for_hermes` avec résumés | Read-only, paginé |
| `GET /hermes/query` | Requête SQL read-only | Timeout 10s, limite résultats |
| `POST /hermes/fetch-web` | Récupération contenu web | Domaines whitelistés uniquement |
| `POST /actions/send-email` | Envoi email | Destinataire validé côté newsletter-engine |
| `POST /actions/mark-digest-sent` | Mise à jour état digest | — |
| `GET /hermes/preferences` | Lecture fichiers Markdown config | — |
| `POST /hermes/preferences` | Modification fichiers Markdown config | Diff journalisé |

### 3b — Flux digest journalier

```
1. Newsletter-engine réveille Hermès (digest_due)
2. Hermès interroge les emails ready_for_hermes
3. Hermès lit les préférences utilisateur
4. Hermès sélectionne ce qui mérite d'être communiqué
5. Hermès génère le digest personnalisé
6. Hermès appelle call_engine_api → send-email
7. Hermès journalise chaque décision (inclus/ignoré + raison)
8. Newsletter-engine marque le digest sent
```

### 3c — Flux conversationnel

```
1. Newsletter-engine détecte email de l'utilisateur autorisé
2. Newsletter-engine réveille Hermès avec le message
3. Hermès interprète : question analytique, feedback, changement de config
4. Hermès répond via call_engine_api → send-email
5. Hermès consolide le feedback dans les Markdown si pertinent
6. Action journalisée
```

Exemples de messages supportés :
- `"Fais-moi un résumé des nouvelles de cette semaine."` → requête SQL + synthèse
- `"Ignore les annonces produit trop marketing."` → mise à jour `learned_preferences.md`
- `"Je veux plus de signaux liés à IAM."` → mise à jour `user_profile.md`
- `"Quels sujets reviennent le plus depuis six mois ?"` → requête SQL analytique
- `"Change le digest quotidien à 08:00."` → mise à jour `settings.yaml`

---

## Phase 4 — Configuration & préférences

```
config/
  settings.yaml           # heure digest, fuseau, adresses email, domaines web autorisés, whitelist expéditeurs avec catégories
  user_profile.md         # profil, intérêts, sujets à ignorer
  digest_style.md         # style éditorial, longueur, format
  learned_preferences.md  # mis à jour par Hermès au fil du temps
```

Les fichiers Markdown sont lisibles, versionnables et modifiables directement par l'utilisateur. Chaque modification faite par Hermès est journalisée avec un diff.

---

## Phase 5 — Sécurité & observabilité

### Confinement d'Hermès

- Exécution non-root
- Pas d'accès aux tokens Gmail
- Pas d'envoi email direct (passe par newsletter-engine)
- Accès réseau sortant restreint (domaines whitelistés uniquement)
- Accès Postgres read-only

### Audit

- Logs structurés JSON dans `audit_logs`
- Journalisation : email ingéré, décision whitelist, transitions d'état, modèle utilisé, tokens, décision Hermès, digest envoyé, feedback reçu, modification de préférence, erreur workflow
- Diff journal des modifications Markdown de préférences
- Ne pas logger : tokens OAuth, secrets, contenu complet répété, données personnelles sans utilité d'audit

### Défense contre prompt injection

- Hermès est traité comme potentiellement manipulable
- La défense est le confinement, pas la confiance
- Newsletter-engine valide toutes les actions avant exécution

---

## Structure de fichiers cible

```
agent-newsletter/
  docker-compose.yml
  .env.example
  config/
    settings.yaml
    sources.yaml
    user_profile.md
    digest_style.md
    learned_preferences.md
  hermes/
    Dockerfile
    main.py
    agent.py
    tools/
      database.py
      python_exec.py
      web_fetch.py
      engine_api.py
      preferences.py
  newsletter-engine/
    Dockerfile
    main.py
    gmail/
      client.py
      poller.py
    processing/
      ingestion.py
      cleaner.py
      enrichment.py
    scheduler.py
    api/
      routes.py
    db/
      models.py
      session.py
  migrations/
    alembic.ini
    versions/
```

---

## Ordre de livraison

| Semaine | Phase |
|---|---|
| 1 | Phase 1 : Docker Compose + schéma DB + migrations |
| 2 | Phase 2a + 2b : Gmail + ingestion + enrichissement |
| 3 | Phase 2c + 2d : Scheduler + API interne |
| 4 | Phase 3a + 3b : Agent Hermès + flux digest |
| 5 | Phase 3c + Phase 4 : Flux conversationnel + config |
| 6 | Phase 5 : Sécurité + audit + polish |
