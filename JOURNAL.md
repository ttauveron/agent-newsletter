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

## Phase 2d — API interne FastAPI ⏳ Partielle

**Objectif** : endpoints appelables par Hermes (réseau Docker interne uniquement).

### Ce qui existe déjà

- `GET /health`
- `POST /trigger/poll` (déclenchement manuel du polling Gmail)

### Endpoints manquants (pour Hermes)

| Endpoint | Rôle | Notes |
|---|---|---|
| `GET /hermes/emails` | Emails `ready_for_hermes` avec résumés | Paginé, read-only |
| `GET /hermes/query` | Requête analytique sur les données | Timeout, limite résultats |
| `POST /hermes/fetch-web` | Fetch contenu web | Domaines whitelistés (`settings.web.allowed_domains`) |
| `POST /actions/send-email` | Envoi email via Gmail | Destinataire forcément `authorized_user_address` |
| `POST /actions/mark-digest-sent` | Mise à jour état digest → `digest_sent` | — |
| `POST /actions/update-processing-state` | Transition d'état sur un email | Valider les transitions autorisées |
| `GET /hermes/preferences` | Lecture des fichiers Markdown config | — |
| `POST /hermes/preferences` | Écriture fichiers Markdown config | Journaliser le diff |
| `POST /trigger/hermes` | Wake-up Hermes | Appel HTTP vers `HERMES_URL` |

### Points d'attention

- Tous les endpoints Hermes doivent valider les actions avant exécution (guard-rails côté newsletter-engine).
- `POST /actions/send-email` : valider que `to` == `authorized_user_address` (défense prompt injection).
- Factoriser dans `api/routes.py` (fichier à créer).

---

## Phase 3 — Hermes Agent ⏳ À faire

**Répertoire `hermes/`** : vide pour l'instant.

### 3a — Déploiement Hermes Agent

- Hermes Agent est un projet NousResearch déployé via l'image Docker `nousresearch/hermes-agent:latest`.
- La commande dans docker-compose est `gateway run` (à vérifier avec la doc Hermes Agent).
- À configurer : provider LLM (endpoint OpenAI-compatible), outils HTTP vers newsletter-engine.
- Variables d'environnement : `DATABASE_URL` (hermes_readonly), `NEWSLETTER_ENGINE_URL`.
- Pas de code custom Python dans `hermes/` — configuration uniquement.

### 3b — Flux digest journalier

```
newsletter-engine (scheduler) → POST /trigger/hermes
  → Hermes interroge GET /hermes/emails
  → Hermes lit GET /hermes/preferences
  → Hermes génère digest
  → Hermes appelle POST /actions/send-email
  → Hermes appelle POST /actions/mark-digest-sent
  → Audit logs
```

### 3c — Flux conversationnel

```
UserMessage en DB (state: user_message_received)
  → newsletter-engine réveille Hermes avec contexte
  → Hermes interprète + répond
  → POST /actions/send-email
  → Optionnel : POST /hermes/preferences (feedback → mémoire Markdown)
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

**Phase 2d** : créer `newsletter-engine/api/routes.py` avec les endpoints Hermes (send-email, mark-digest-sent, update-processing-state, hermes/emails, hermes/preferences, etc.). Ensuite Phase 3a : configuration Hermes Agent.

---

## Décisions d'architecture notables

Voir [decisions_architecture.md](decisions_architecture.md) pour le détail complet. Résumé :

- Hermes passe par des endpoints HTTP (pas d'accès SQL direct) — plus de contrôle, plus d'API à maintenir.
- Python exec disponible pour Hermes pour l'analyse locale des résultats.
- Hermes modifie directement les Markdown de préférences (avec journal de diff).
- Scheduler intégré dans newsletter-engine (APScheduler).
- Une seule adresse Gmail pour tout (newsletters, messages utilisateur, envoi digest).
- Emails non whitelistés : laissés non lus, non traités.
- Contenu stocké : texte nettoyé (HTML supprimé, liens conservés).
- Accès web whitelisté inclus en v1 (via `POST /hermes/fetch-web`).
