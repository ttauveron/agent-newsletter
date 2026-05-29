# Hermès — Newsletter Intelligence Agent

Agent de veille automatique qui ingère des newsletters Gmail, les résume, et génère un digest journalier personnalisé.

## Architecture

```
docker-compose
  ├── newsletter-engine   # Pipeline d'ingestion Gmail, enrichissement, API interne
  ├── hermes              # Agent Claude : raisonnement, sélection, digest, conversation
  └── postgres            # Données métier partagées (deux rôles distincts)
```

- **newsletter-engine** : Python, FastAPI, Gmail API, APScheduler, SQLAlchemy, Alembic
- **hermes** : [Hermes Agent](https://github.com/NousResearch/hermes-agent) (NousResearch) — fonctionne avec tout endpoint OpenAI-compatible, provider configurable
- **postgres** : rôle `newsletter_engine` (read/write), rôle `hermes_readonly` (SELECT uniquement)

## Commandes de développement

Toutes les commandes suivantes se lancent depuis `newsletter-engine/`.

### Tests

```bash
uv run pytest -q
```

### Qualité de code

```bash
# Lint (E/F/I)
uv run ruff check .

# Formatage
uv run ruff format --check .

# Sécurité
uv run bandit -r config.py main.py gmail/ processing/ db/ -q
```

Correction automatique des problèmes fixables :

```bash
uv run ruff check --fix . && uv run ruff format .
```

### Suite complète (à lancer après chaque modification)

```bash
cd newsletter-engine && uv run ruff check . && uv run ruff format --check . && uv run bandit -r config.py main.py gmail/ processing/ db/ -q && uv run pytest -q
```

## Démarrage

```bash
cp .env.example .env
# Remplir les valeurs dans .env

docker compose up
```

Authentification Gmail (une seule fois) :

```bash
docker compose run --rm newsletter-engine python -m gmail.auth
```

Migrations DB (automatiques au démarrage, mais aussi lançables manuellement) :

```bash
cd newsletter-engine && DATABASE_URL=... uv run alembic -c /app/migrations/alembic.ini upgrade head
```

## Structure des fichiers

```
newsletter-engine/
  config.py               # Chargement settings.yaml et sources.yaml
  main.py                 # FastAPI app + endpoints déclenchables
  gmail/
    client.py             # Client Gmail OAuth2
    auth.py               # Script d'authentification initiale
    parser.py             # Parsing des messages Gmail API → ParsedEmail
    poller.py             # Boucle d'ingestion : fetch → filter → store
  processing/
    whitelist.py          # Classification expéditeur (newsletter / user / ignored)
    cleaner.py            # HTML → texte, liens conservés
    ingestion.py          # Écriture en DB, transitions d'état
    state.py              # Helpers audit_logs et processing_events
  db/
    models.py             # Modèles SQLAlchemy (Email, Summary, Digest, …)
    session.py            # SessionLocal et context manager get_session()
  tests/
    test_whitelist.py
    test_cleaner.py
    test_parser.py

hermes/
  # Hermes Agent (NousResearch) — déployé via Docker, configuré par .env et config/
  # Pas de code custom : configuration du provider LLM, des outils, et de la mémoire

migrations/
  versions/
    001_initial_schema.py

config/
  settings.yaml           # Heure digest, fuseau, adresses email
  sources.yaml            # Whitelist expéditeurs avec catégories
  user_profile.md         # Profil utilisateur (modifiable par Hermès)
  digest_style.md         # Style éditorial du digest
  learned_preferences.md  # Préférences apprises au fil du temps
```

## Conventions

- Python 3.12+, UV pour la gestion des dépendances
- `uv add <pkg>` pour ajouter une dépendance (met à jour pyproject.toml et uv.lock)
- `uv add --dev <pkg>` pour les dépendances de développement
- Ruff : ligne max 100 caractères, règles E/F/I, format appliqué
- Bandit : scan sécurité sur le code source (hors `.venv` et `tests/`), faux positifs documentés avec `# nosec BXXX`
- Pas de commentaires sauf si le WHY est non-obvious
- Les états de processing sont des strings correspondant aux valeurs des enums dans `db/models.py`
