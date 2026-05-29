# Tâches de suivi

## Suivi

### #8 — Corriger le payload du webhook `user-message`

**État** : Terminée

**Contexte**

Le prompt Hermes `user-message` utilise `{content}`, mais le scheduler ne transmet aujourd'hui que `message_id` et `subject`.

**Objectif**

Transmettre le contenu du `UserMessage` au webhook Hermes, ou ajuster explicitement le prompt si le contenu doit être relu par Hermes en base.

**Critères de validation**

- `_check_user_messages()` envoie un payload compatible avec `hermes/config.yaml`.
- Les tests scheduler couvrent le champ attendu.
- Le flux conversationnel end-to-end ne produit pas de variable manquante dans le prompt Hermes.

### #9 — Router les newsletters transférées par l'utilisateur

**État** : Terminée

**Contexte**

La décision d'architecture prévoit que les emails de l'utilisateur autorisé dont le sujet commence par `Fwd:`, `FW:`, `Tr:`, `Transf:` ou `WG:` soient traités comme des newsletters transférées. Le routage actuel classe tous les emails de l'utilisateur autorisé comme messages conversationnels.

**Objectif**

Ajouter l'heuristique de sujet transféré dans le routage Gmail sans complexifier l'extraction de la source réelle pour la v1.

**Critères de validation**

- Un email de l'utilisateur autorisé avec sujet `Fwd:` / `FW:` / `Tr:` / `Transf:` / `WG:` suit le flux newsletter.
- Un email normal de l'utilisateur autorisé reste un `user_message`.
- Les tests couvrent les deux routes.

### #10 — Aligner la documentation des ports Hermes

**État** : À faire

**Contexte**

Le code et `docker-compose.yml` utilisent le port `8644` pour les webhooks Hermes, mais `PLAN.md` et `decisions_architecture.md` mentionnent encore `8642` pour certaines routes webhook.

**Objectif**

Mettre les documents d'architecture en cohérence avec l'implémentation actuelle : API server Hermes sur `8642`, webhooks sur `8644`.

**Critères de validation**

- `PLAN.md` ne décrit plus les webhooks sur `8642`.
- `decisions_architecture.md` ne décrit plus les webhooks sur `8642`.
- `JOURNAL.md` reste cohérent avec la distinction `8642` / `8644`.
