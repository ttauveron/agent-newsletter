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
| 3a | Déploiement Hermes Agent | **Terminée** |
| 3b | Flux digest journalier | **Terminée** |
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

## Phase 2d — API interne FastAPI ✅

**Objectif** : les 3 endpoints que Hermes peut appeler sur newsletter-engine. Hermes lit les données directement en DB — pas d'endpoint de query.

### Ce qui est en place

- **`gmail/client.py`** : méthode `send_email(to, subject, body)` ajoutée (MIME text, base64url, Gmail API).
- **`api/routes.py`** : `create_router(gmail_client, settings)` — 3 endpoints :
  - `POST /actions/send-digest` : valide que le digest est en état `digest_due` ou `digest_generation_requested`, envoie l'email, marque `digest_sent` + `sent_at`, audit log `digest_sent`.
  - `POST /actions/send-reply` : valide que le `UserMessage` existe, envoie la réponse, marque `answered` + `hermes_response`, audit log `reply_sent`. Préfixe "Re:" sans doublon.
  - `POST /hermes/preferences` : clés DB (`digest_schedule`, `digest_timezone`) → `app_settings` + reschedule APScheduler à chaud. Clés Markdown (`user_profile`, `digest_style`, `learned_preferences`) → fichier + diff journalisé en `audit_logs`.
- **`main.py`** : router inclus, `app.state.scheduler/gmail_client/settings` exposés.
- **Tests** : `test_api.py` — 22 tests via `TestClient` + `_patched_client` context manager.

---

## Phase 3 — Hermes Agent ✅ Flux digest validé

### Ce qu'on sait sur Hermes Agent (NousResearch)

- Expose `POST /v1/chat/completions` (OpenAI-compatible), `POST /v1/runs` (async SSE), et un **webhook platform**.
- **API server sur port 8642**, **webhooks sur port 8644** (deux ports distincts).
- Webhook platform : routes nommées dans `hermes/config.yaml`, newsletter-engine POSTe des données JSON, Hermes injecte les variables via `{field.path}` dans le template de prompt.
- Dispose d'outils natifs : terminal, Python exec, web fetch/search — accès DB via Python/psql dans le conteneur.
- Config dans `~/.hermes/config.yaml` (monté via volume Docker), secrets dans env vars.
- `API_SERVER_ENABLED=true` + `API_SERVER_HOST=0.0.0.0` requis pour écouter dans Docker.

### 3a — Configuration Hermes Agent ✅

- **`hermes/config.yaml`** : provider `anthropic` / modèle `claude-sonnet-4-6`, terminal `local`, webhooks sur port 8644 avec deux routes :
  - `daily-digest` : prompt guidant Hermes à requêter la DB, lire les Markdown config, générer et envoyer le digest via `POST /actions/send-digest`.
  - `user-message` : prompt guidant Hermes à interpréter le message (SQL, préférences, réponse directe) et répondre via `POST /actions/send-reply`.
- **`docker-compose.yml`** : port 8644 exposé, `hermes/config.yaml` monté en `:ro` à `/root/.hermes/config.yaml` et `/opt/data/config.yaml`, `./config` monté en `:ro` à `/app/config`, webhook platform activée, `HERMES_WEBHOOK_URL=http://hermes:8644` pour newsletter-engine.
- **`.env.example`** : `HERMES_API_KEY` et `HERMES_WEBHOOK_SECRET` ajoutés, `HERMES_URL` → `HERMES_WEBHOOK_URL`.
- **`scheduler.py`** : `_wake_hermes` lit `HERMES_WEBHOOK_URL` (port 8644), signe les payloads webhook avec `HERMES_WEBHOOK_SECRET` si présent et envoie le JSON brut attendu par Hermes.

### Correction locale — Réponses enrichissement clôturées par Markdown ✅

- **`processing/enrichment.py`** : `_parse_response()` accepte les réponses JSON entourées de fences Markdown (` ```json ... ``` `), cas fréquent avec certains modèles.
- **Tests** : `test_enrichment.py` couvre les fences typées et non typées.

### Correction #8 — Payload `user-message` ✅

- **`scheduler.py`** : le webhook `user-message` reçoit maintenant `content` en plus de `message_id` et `subject`, conformément au template Hermes.
- **Tests** : `test_scheduler.py` vérifie le champ `content` dans le payload transmis à Hermes.

### Correction #9 — Newsletters transférées ✅

- **`processing/whitelist.py`** : les emails de l'utilisateur autorisé dont le sujet commence par `Fwd:`, `FW:`, `Tr:`, `Transf:` ou `WG:` sont routés comme newsletters avec la catégorie `forwarded_newsletter`.
- **`gmail/poller.py`** : le sujet parsé est transmis au filtre de routage.
- **Tests** : `test_whitelist.py` couvre les sujets transférés et les messages utilisateur normaux.

### 3b — Flux digest journalier ✅ (validé 2026-05-30)

```
1. Scheduler → POST /webhooks/daily-digest { date }
2. Hermes → psql "$DATABASE_URL" SELECT emails + summaries WHERE ready_for_hermes
3. Hermes → psql "$DATABASE_URL" SELECT digest_id + lit Markdown config
4. Hermes génère le digest (Sonnet 4.6 via LiteLLM)
5. Hermes → POST /actions/send-digest → newsletter-engine envoie + marque digest_sent
```

**Points d'attention découverts en test :**
- `psycopg2` non installé dans Hermes, l'agent essayait Python → fix : `hermes/Dockerfile` custom avec `postgresql-client` pour avoir `psql` CLI.
- Prompt mis à jour pour expliciter `psql "$DATABASE_URL" -t -A -c "SQL"` comme méthode d'accès DB.
- L'agent s'auto-corrige sur les erreurs d'échappement JSON (write_file → curl @file).

### 3c — Flux conversationnel (révisé)

```
1. Scheduler → POST /webhooks/user-message { message_id, subject, content }
2. Hermes interprète → SQL si analytique, POST /hermes/preferences si config/feedback
3. Hermes → POST /actions/send-reply → newsletter-engine envoie la réponse
```

---

## Phase 4 — Configuration & préférences ⏳ Partielle

### Ce qui existe

- `config/settings.yaml` : ignoré par Git (voir `settings.yaml.example` pour la structure). À copier au setup.
- `config/sources.yaml` : whitelist expéditeurs (exemples placeholder).
- `config/user_profile.md` : créé.
- `config/digest_style.md` : créé.
- `config/learned_preferences.md` : créé.

### Issue #14 — Gitignore config/settings.yaml ✅

**Commit** : `fa14a4e` | **PR** : [#16](https://github.com/ttauveron/agent-newsletter/pull/16)

- `config/settings.yaml.example` créé avec des valeurs placeholder.
- `config/settings.yaml` désindexé du tracking git et ajouté au `.gitignore`.
- Step de setup `cp config/settings.yaml.example config/settings.yaml` documenté dans `README.md` et `CLAUDE.md`.

### À compléter

- Remplir `settings.yaml` avec les vraies valeurs (adresses email, heure digest, domaines autorisés).
- Remplir `sources.yaml` avec les vraies sources newsletter.
- Documenter le format attendu par Hermes pour lire ces fichiers.

## Tests end-to-end locaux ⏳ En cours

### Issue #2 — Scénario Docker avec mailbox locale

- **`docker-compose.e2e.yml`** : active `EMAIL_BACKEND=local`, `ENRICHMENT_BACKEND=local` et une mailbox fichier dans le conteneur `newsletter-engine`.
- **`config/e2e/`** : configuration déterministe pour lancer le pipeline sans Gmail.
- **`scripts/e2e-local-mailbox.sh`** : démarre Postgres + newsletter-engine, injecte une newsletter et un message utilisateur, déclenche `/trigger/poll`, vérifie la DB puis l'outbox locale.
- **`README.md`** : documente la commande e2e locale.

---

## Phase 5 — Sécurité & observabilité ⏳ Partielle

### Ce qui est en place

- Séparation des rôles DB (hermes_readonly / newsletter_engine).
- Audit logs dans `audit_logs` : email_ingested, email_ignored_not_whitelisted, email_enriched, user_message_received.
- Bandit configuré (scan sur `config.py main.py gmail/ processing/ db/`).
- Hermes sans accès Gmail (accès uniquement via endpoints newsletter-engine).

### Issue #7 — LiteLLM + isolation réseau Docker ⏳ En review

**Commit** : `4e77595` | **PR** : [#17](https://github.com/ttauveron/agent-newsletter/pull/17)

- Service `litellm` ajouté comme point de sortie unique vers les providers LLM.
- Réseau `backend` (`internal: true`) : `postgres`, `newsletter-engine`, `hermes` — zéro accès internet direct.
- Réseau `public` : `litellm` et `newsletter-engine` uniquement (newsletter-engine conserve l'accès internet pour Gmail).
- `ANTHROPIC_API_KEY` supprimé de l'environnement `hermes` — tout l'accès LLM passe par LiteLLM.
- `litellm/config.yaml` : modèles virtuels `hermes` (sonnet-4-6) et `enrichment` (haiku-4-5).
- `LITELLM_MASTER_KEY` ajouté dans `.env.example`.

**Point d'attention** : hermes sera non-fonctionnel jusqu'à #10 (migration provider LiteLLM). newsletter-engine garde encore `ANTHROPIC_API_KEY` pour l'enrichissement jusqu'à #9.

### Issue #10 — Configurer Hermes pour utiliser LiteLLM ✅

**PR** : [#20](https://github.com/ttauveron/agent-newsletter/pull/20)

- `hermes/config.yaml` : `provider: openai`, `default: hermes`, `base_url: http://litellm:4000/v1`, `api_key: ${LITELLM_HERMES_KEY}`
- `docker-compose.yml` : `LITELLM_HERMES_KEY` ajouté à l'env hermes
- Hermes n'a plus aucune clé Anthropic directe — tout passe par LiteLLM avec la virtual key restreinte au modèle `hermes`.

### Issue #8 — Virtual keys LiteLLM par service ⏳ En review

**PR** : [#18](https://github.com/ttauveron/agent-newsletter/pull/18)

- Base `litellm_db` dédiée sur la même instance postgres — isolation totale des données métier.
- Rôle `litellm` owner de `litellm_db`, aucun accès à `hermes_db`.
- `postgres/init.sh` : création du rôle et de la base séparée (`CREATE DATABASE` hors transaction).
- `docker-compose.yml` : `DATABASE_URL` de litellm pointe sur `litellm_db`.
- Virtual key `hermes` (modèle `hermes` uniquement) et `enrichment` (modèle `enrichment` uniquement).
- `scripts/litellm-init-keys.sh` : génération one-shot des clés (pattern identique à `gmail.auth`).
- Décision documentée dans `decisions_architecture.md`.

### À faire

- Valider que Hermes tourne en non-root (option `HERMES_UID`/`HERMES_GID` présente, à confirmer).
- Vérifier que les secrets (tokens OAuth, API keys) ne sont pas accessibles depuis le conteneur Hermes.
- Ajouter audit logs pour les actions Hermes : décision digest, email envoyé, préférence modifiée.
- Journal de diff pour les modifications de fichiers Markdown.

---

## Prochaine étape recommandée

Flux digest validé end-to-end (2026-05-30). Prochaines priorités :

- **Phase 3c** : Valider le flux conversationnel (envoyer un message utilisateur et vérifier que Hermes répond)
- **Réglage du digest** : ajuster `user_profile.md`, `digest_style.md`, `sources.yaml` pour affiner la sélection et le style éditorial
- **Phase 5** : Audit logs actions Hermes, vérification non-root container

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
