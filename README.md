# Hermes Newsletter Intelligence Agent

Agent de veille qui ingere des newsletters Gmail, les nettoie, les enrichit, puis
prepare un digest personnalise via Hermes Agent.

## Configuration email

La configuration fonctionnelle se trouve dans `config/settings.yaml`.

```yaml
digest:
  schedule: "07:00"
  timezone: "Europe/Zurich"

email:
  hermes_address: "adresse-gmail-dediee@example.com"
  authorized_user_address: "adresse-personnelle@example.com"

web:
  allowed_domains: []
```

- `email.hermes_address` : adresse Gmail dediee qui recoit les newsletters et envoie les digests.
- `email.authorized_user_address` : adresse personnelle autorisee a dialoguer avec Hermes.
- `digest.schedule` / `digest.timezone` : valeurs de demarrage. Le scheduler lit ensuite les valeurs runtime depuis la table `app_settings`.

Les sources newsletters autorisees se configurent dans `config/sources.yaml`.

```yaml
sources:
  - match: "newsletter@example.com"
    category: "cloud_security"

  - match_domain: "example.org"
    category: "market_signal"
```

Les emails non whitelistes sont ignores et restent non lus.

## Integration Google Gmail

Le moteur utilise l'API Gmail avec le scope suivant :

```text
https://www.googleapis.com/auth/gmail.modify
```

Ce scope permet de lire, modifier les labels et envoyer des emails. Il est necessaire pour :

- recuperer les emails non lus ;
- marquer les emails traites comme lus ;
- envoyer les digests et les reponses via Gmail.

### 1. Creer le projet Google Cloud

1. Ouvrir Google Cloud Console.
2. Creer ou selectionner un projet dedie.
3. Activer l'API **Gmail API** dans `APIs & Services`.

### 2. Configurer l'OAuth consent screen

Dans `APIs & Services` -> `OAuth consent screen` :

1. Choisir `External`.
2. Laisser le statut en `Testing` pour un usage personnel.
3. Ajouter l'adresse Gmail dediee dans `Test users`.
4. Dans `Data Access`, ajouter le scope Gmail :

```text
.../auth/gmail.modify
```

Google classe ce scope comme scope Gmail restreint. En mode `Testing`, l'ecran
"Google hasn't verified this app" est attendu. Cliquer sur `Continue` est normal
pour un usage personnel avec un utilisateur de test.

### 3. Creer le client OAuth

Dans `APIs & Services` -> `Credentials` :

1. Cliquer sur `Create credentials`.
2. Choisir `OAuth client ID`.
3. Choisir le type **Desktop app**.
4. Telecharger le fichier JSON.
5. Copier ce fichier ici :

```bash
config/client_secret.json
```

Ne pas utiliser un client `Web application` pour cette commande d'auth locale.

### 4. Variables d'environnement

Copier l'exemple :

```bash
cp .env.example .env
```

Verifier au minimum :

```env
GMAIL_CLIENT_SECRET_PATH=/app/config/client_secret.json
GMAIL_TOKEN_PATH=/app/config/gmail_token.json
GMAIL_AUTH_PORT=8888
```

`GMAIL_AUTH_PORT` sert uniquement pendant l'authentification OAuth locale.

### 5. Generer le token Gmail

Utiliser Google Chrome ou Chromium pour ce flow. Firefox peut echouer sur
l'ecran Google "app non verifiee" avec une erreur interne Google 500.

Commande standard :

```bash
docker compose run --rm -p 8888:8888 newsletter-engine python -m gmail.auth
```

Si le port `8888` est deja utilise :

```bash
docker compose run --rm -e GMAIL_AUTH_PORT=8889 -p 8889:8889 newsletter-engine python -m gmail.auth
```

Le script affiche une URL Google :

1. Ouvrir l'URL dans Chrome/Chromium.
2. Selectionner le compte Gmail dedie.
3. Passer l'avertissement "app non verifiee" avec `Continue`.
4. Accepter le scope Gmail.
5. Attendre la page de succes.

Le token est ecrit dans :

```text
config/gmail_token.json
```

Ce fichier est ignore par Git et ne doit pas etre commite.

### Depannage OAuth

- `Bind for 0.0.0.0:8888 failed: port is already allocated` :
  utiliser un autre port avec `GMAIL_AUTH_PORT` et `-p PORT:PORT`.
- Erreur Google sur l'ecran "app non verifiee" :
  tester avec Chrome/Chromium en navigation privee, un seul compte Google connecte.
- `access_denied` ou utilisateur refuse :
  verifier que le compte est bien dans `Test users`.
- Le scope n'apparait pas dans l'ecran de consentement :
  verifier `Data Access` et attendre la propagation Google Cloud, qui peut prendre plusieurs minutes.

## Demarrage

Apres creation de `.env`, du `client_secret.json` et du `gmail_token.json` :

```bash
docker compose up
```

L'API `newsletter-engine` expose notamment :

```text
GET  /health
POST /trigger/poll
```

## Developpement

Depuis `newsletter-engine/` :

```bash
uv run ruff check .
uv run ruff format --check .
uv run bandit -r config.py main.py gmail/ processing/ db/ -q
uv run pytest -q
```

Suite complete :

```bash
cd newsletter-engine && uv run ruff check . && uv run ruff format --check . && uv run bandit -r config.py main.py gmail/ processing/ db/ -q && uv run pytest -q
```
