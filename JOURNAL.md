# Journal de bord — Hermès Newsletter Intelligence Agent

Référence principale : [PLAN.md](PLAN.md) | [SPECS.md](SPECS.md) | [decisions_architecture.md](decisions_architecture.md)

---

## État d'avancement global

| Phase | Titre | État |
|---|---|---|
| 1 | Infrastructure & base de données | **Terminée** |
| 2a | Gmail & ingestion | **Terminée** |
| 2b | Enrichissement | **Terminée** |
| 2c | Scheduler | **Terminée** |
| 2d | API interne FastAPI | Partielle |
| 3a | Déploiement Hermes Agent | À faire |
| 3b | Flux digest journalier | À faire |
| 3c | Flux conversationnel | À faire |
| 4 | Configuration & préférences | Partielle (fichiers créés) |
| 5 | Sécurité & observabilité | Partielle (base en place) |

---

## Phase 1 — Infrastructure & base de données ✅

**Commits** : `f21c588`, `ca18268`, `e168870`, `2ddc384`

### Ce qui est en place

- **Docker Compose** : 3 services (`postgres`, `newsletter-engine`, `hermes`), healthchecks sur chaque service.
- **Postgres** : image 16, volume persistant, init via `postgres/init.sh`.
  - Rôle `newsletter_engine` : read/write sur toutes les tables.
  - Rôle `hermes_readonly` : SELECT uniquement (via `ALTER DEFAULT PRIVILEGES`).
- **Schéma DB** (migration `migrations/versions/001_initial_schema.py`) :
  - `emails` + `EmailState` enum (received → ingested → cleaned → summarized → ready_for_hermes → selected_for_digest → ignored_by_hermes → sent_in_digest → archived)
  - `summaries` (résumé, key_points JSONB, tags JSONB, model_used, tokens)
  - `digests` + `DigestState` enum
  - `user_messages` + `UserMessageState` enum
  - `audit_logs` (JSONB payload)
  - `processing_events` (transitions d'état avec from/to)
- **Alembic** : configuré dans `migrations/`, migrations automatiques au démarrage via `entrypoint.sh`.
- **Config** : `config.py` charge `settings.yaml` et `sources.yaml` via pydantic.

---

## Phase 2a — Gmail & ingestion ✅

**Commits** : `ca18268`, `0e98828`, `1061b51`

### Ce qui est en place

- **`gmail/client.py`** : `GmailClient`, scope `gmail.modify`, lazy-load credentials, auto-refresh token.
- **`gmail/auth.py`** : script d'authentification initiale OAuth2 (à lancer une seule fois).
- **`gmail/parser.py`** : `parse_message()` → `ParsedEmail`. Préfère `text/plain`, fallback `text/html`, gère `multipart/*` récursif.
- **`processing/whitelist.py`** : `WhitelistFilter.classify()` → `EmailAction` (newsletter / user_message / ignored). Supporte `match` (email exact) et `match_domain`.
- **`processing/cleaner.py`** : `clean_content()` — HTML → texte avec liens conservés (`text (url)`), nettoyage whitespace.
- **`processing/ingestion.py`** : `ingest_newsletter()` et `ingest_user_message()`. Transitions d'état + audit log.
- **`processing/state.py`** : helpers `transition_state()` et `audit()`.
- **`gmail/poller.py`** : `poll()` — fetch unread → classify → ingest ou ignorer → mark as read. Déduplication par `gmail_message_id`. Gestion d'erreurs par message (non-fatal).
- **`main.py`** : FastAPI app, endpoint `GET /health` et `POST /trigger/poll`.
- **Tests** : `test_whitelist.py`, `test_cleaner.py`, `test_parser.py`.
- **Qualité** : ruff check + format, bandit configurés.

---

## Phase 2b — Enrichissement ✅

**Commits** : `6d7d37d`, `a971673`

### Ce qui est en place

- **`processing/enrichment.py`** : `enrich_email()` appelle Haiku 4.5 (`claude-haiku-4-5-20251001`) pour générer summary + key_points + tags. JSON-only response. Truncature à 4000 chars. Non-fatal : retourne `None` en cas d'échec.
- Transitions : `cleaned → summarized → ready_for_hermes`.
- Audit log `email_enriched` avec model, tokens, tags.
- Appel intégré directement dans `poller.py` après `ingest_newsletter()`.
- **Tests** : `test_enrichment.py` — couvre `_truncate`, `_parse_response`, `_build_prompt`, `enrich_email` (happy path + erreurs API + JSON invalide).

---

## Phase 2c-bis — Migration app_settings + scheduler depuis DB ✅

### Ce qui est en place

- **Migration `002_app_settings.py`** : table `app_settings` (key PK, value, updated_at). Valeurs initiales : `digest_schedule=07:00`, `digest_timezone=Europe/Zurich`. GRANT SELECT à `hermes_readonly`.
- **`db/models.py`** : modèle `AppSetting` ajouté.
- **`scheduler.py`** :
  - `load_digest_config(session)` : lit `digest_schedule` et `digest_timezone` depuis `app_settings`, fallback sur les defaults si absents.
  - `reschedule_digest(scheduler, schedule, timezone)` : reschedule le job `daily_digest` à chaud via `scheduler.reschedule_job()`.
  - `create_scheduler(digest_schedule, digest_timezone, ...)` : signature mise à jour (plus de `settings` passé).
  - `_wake_hermes` : URL webhook construite comme `{HERMES_URL}/webhooks/{event}` (ex: `/webhooks/daily-digest`, `/webhooks/user-message`).
- **`main.py`** : lit la config depuis DB au démarrage via `load_digest_config`, stocke le scheduler sur `app.state.scheduler` pour que les routes puissent reschedule.
- **Tests** : 3 nouveaux tests (`load_digest_config` happy path + fallbacks, `reschedule_digest`), tests existants mis à jour pour la nouvelle signature.

---

## Phase 2c — Scheduler ✅

**Commits** : à venir

### Ce qui est en place

- **`scheduler.py`** : `AsyncIOScheduler` APScheduler avec 3 jobs wired dans le lifespan FastAPI :
  - `daily_digest` : `CronTrigger` à l'heure `settings.digest.schedule` / `settings.digest.timezone`. Crée un enregistrement `Digest` (`digest_due`) si aucun n'existe pour aujourd'hui, puis appelle `_wake_hermes` avec `event=daily_digest_due`.
  - `gmail_poll` : `IntervalTrigger` toutes les 5 minutes. Appelle le pipeline `poll()` existant.
  - `check_user_messages` : `IntervalTrigger` toutes les minutes. Trouve les `UserMessage` en état `user_message_received`, les passe à `passed_to_hermes`, puis appelle `_wake_hermes` pour chaque message.
- **`_wake_hermes(payload)`** : appel HTTP `POST {HERMES_URL}/api/trigger` via httpx async. Non-fatal : log l'erreur sans lever d'exception.
- **`main.py`** : scheduler démarré/arrêté via `asynccontextmanager lifespan` FastAPI.
- **`tests/conftest.py`** : fixe `DATABASE_URL` pour que `db/session.py` s'importe sans DB réelle en test.
- **Tests** : `test_scheduler.py` — 14 tests couvrant `_wake_hermes`, `_run_daily_digest`, `_check_user_messages`, `create_scheduler`.

### Points d'attention

- `_wake_hermes` appelle `{HERMES_URL}/api/trigger` — endpoint à confirmer lors de la configuration Hermes Agent (Phase 3a).
- `max_instances=1` sur chaque job : pas de chevauchement si un job prend du retard.
- `misfire_grace_time` : digest=5min, poll=1min, user_messages=30s.

---

## Phase 2d — API interne FastAPI ⏳ À faire

**Objectif** : les 3 endpoints que Hermes peut appeler sur newsletter-engine. Hermes lit les données directement en DB — pas d'endpoint de query.

### Ce qui existe déjà

- `GET /health`
- `POST /trigger/poll`

### Endpoints à implémenter

| Endpoint | Rôle | Garde-fous |
|---|---|---|
| `POST /actions/send-digest` | Envoie le digest + marque `digest_sent` | `to` == `authorized_user_address` |
| `POST /actions/send-reply` | Répond à un `UserMessage` + marque `answered` | Idem |
| `POST /hermes/preferences` | Met à jour `app_settings` DB et/ou Markdown | Clés autorisées, diff journalisé, reschedule si besoin |

### Points d'attention

- Nécessite la migration `app_settings` en DB (voir 2c-bis) pour que `POST /hermes/preferences` puisse modifier le schedule.
- `send-digest` prend un `digest_id` pour retrouver l'enregistrement et le marquer.
- Factoriser dans `newsletter-engine/api/routes.py`.

---

## Phase 3 — Hermes Agent ⏳ À faire

**Répertoire `hermes/`** : vide pour l'instant.

### Ce qu'on sait sur Hermes Agent (NousResearch)

- Expose `POST /v1/chat/completions` (OpenAI-compatible), `POST /v1/runs` (async SSE), et un **webhook platform**.
- Le webhook platform est la bonne approche : routes nommées dans `hermes/config.yaml`, newsletter-engine POSTe des données JSON, Hermes injecte les variables dans un template de prompt.
- Dispose d'outils natifs : terminal, Python exec, web fetch/search — aucun outil custom à implémenter côté newsletter-engine pour la lecture de données.
- Authentification API via `API_SERVER_KEY`.

### 3a — Déploiement Hermes Agent

- Créer `hermes/config.yaml` avec : provider LLM, connexion DB (`hermes_readonly`), webhooks `daily-digest` et `user-message`, outils autorisés.
- Mettre à jour `scheduler.py` pour utiliser les bons endpoints webhook (`/webhooks/daily-digest`, `/webhooks/user-message`).
- Variables d'environnement dans `.env` : `API_SERVER_KEY`, provider LLM key.

### 3b — Flux digest journalier (révisé)

```
1. Scheduler → POST /webhooks/daily-digest { date }
2. Hermes → SQL SELECT emails + summaries WHERE ready_for_hermes
3. Hermes → SQL SELECT app_settings + lit Markdown config
4. Hermes génère le digest
5. Hermes → POST /actions/send-digest → newsletter-engine envoie + marque digest_sent
```

### 3c — Flux conversationnel (révisé)

```
1. Scheduler → POST /webhooks/user-message { message_id, subject, content }
2. Hermes interprète → SQL si analytique, POST /hermes/preferences si config/feedback
3. Hermes → POST /actions/send-reply → newsletter-engine envoie la réponse
```

---

## Phase 4 — Configuration & préférences ⏳ Partielle

### Ce qui existe

- `config/settings.yaml` : structure en place (digest schedule + timezone + email + web.allowed_domains).
- `config/sources.yaml` : whitelist expéditeurs (exemples placeholder).
- `config/user_profile.md` : créé.
- `config/digest_style.md` : créé.
- `config/learned_preferences.md` : créé.

### À compléter

- Remplir `settings.yaml` avec les vraies valeurs (adresses email, heure digest, domaines autorisés).
- Remplir `sources.yaml` avec les vraies sources newsletter.
- Documenter le format attendu par Hermes pour lire ces fichiers.

---

## Phase 5 — Sécurité & observabilité ⏳ Partielle

### Ce qui est en place

- Séparation des rôles DB (hermes_readonly / newsletter_engine).
- Audit logs dans `audit_logs` : email_ingested, email_ignored_not_whitelisted, email_enriched, user_message_received.
- Bandit configuré (scan sur `config.py main.py gmail/ processing/ db/`).
- Hermes sans accès Gmail (accès uniquement via endpoints newsletter-engine).

### À faire

- Restreindre l'accès réseau sortant du conteneur Hermes (domaines whitelistés uniquement).
- Valider que Hermes tourne en non-root (option `HERMES_UID`/`HERMES_GID` présente, à confirmer).
- Vérifier que les secrets (tokens OAuth, API keys) ne sont pas accessibles depuis le conteneur Hermes.
- Ajouter audit logs pour les actions Hermes : décision digest, email envoyé, préférence modifiée.
- Journal de diff pour les modifications de fichiers Markdown.

---

## Prochaine étape recommandée

**2c-bis** : migration `app_settings` en DB + mise à jour scheduler. Puis **2d** : les 3 endpoints (`send-digest`, `send-reply`, `preferences`). Puis **3a** : `hermes/config.yaml` + test des webhooks end-to-end.

---

## Décisions d'architecture notables

Voir [decisions_architecture.md](decisions_architecture.md) pour le détail complet. Résumé :

- Hermes accède directement à Postgres via `hermes_readonly` (SQL natif via outils Hermes Agent) — pas d'endpoint de query dans newsletter-engine.
- Réveil Hermes via webhook platform natif : `POST /webhooks/daily-digest` et `POST /webhooks/user-message`, templates de prompt dans `hermes/config.yaml`.
- Endpoints newsletter-engine réduits à 3 : `send-digest`, `send-reply`, `preferences`.
- Settings runtime (`digest_schedule`, `digest_timezone`) en table `app_settings` DB — pas dans `settings.yaml`.
- Accès web par Hermes directement (outils natifs), contrôle réseau Docker (Phase 5).
- Scheduler intégré dans newsletter-engine (APScheduler).
- Une seule adresse Gmail pour tout (newsletters, messages utilisateur, envoi digest).
- Emails non whitelistés : laissés non lus, non traités.
- Contenu stocké : texte nettoyé (HTML supprimé, liens conservés).
