# SOAR-RL-Agent

Projet de base pour un agent d’apprentissage par renforcement (RL) orienté SOAR.

## Architecture du projet

- Backend: API FastAPI, pipeline de données, environnement RL, récompenses, simulation SOC et services métiers.
- Frontend: interface web pour visualiser les alertes, les métriques et l’état du système.
- Data: jeux de données d’entraînement et de test.
- Docs: documentation technique et organisationnelle.
- Scripts: helpers d’automatisation et préparation des données.
- Tests: validation automatisée et qualité logicielle.

## Distribution de l’équipe

- Développeur 1 (PM + RL): branche feature/rl-agent
- Développeur 2 (Data Pipeline): branche feature/data-pipeline
- Développeur 3 (Environnement): branche feature/environment
- Développeur 4 (Reward System): branche feature/reward-system
- Développeur 5 (Backend API): branche feature/backend-api
- Développeur 6 (Database & Monitoring): branche feature/database-monitoring
- Développeur 7 (Frontend): branche feature/frontend

## Stratégie Git

Branches principales:

- main
- develop
- feature/rl-agent
- feature/data-pipeline
- feature/environment
- feature/reward-system
- feature/backend-api
- feature/database-monitoring
- feature/frontend

## Workflow collaboratif

1. Créer ou basculer sur la branche fonctionnelle correspondante.
2. Travailler sur un périmètre clair et limité.
3. Ouvrir une Pull Request vers develop.
4. Valider la qualité, la documentation et les tests.
5. Fusionner uniquement après revue.

## Guide de contribution

- Ne pas modifier la logique métier existante.
- Ne pas déplacer ou supprimer des fichiers existants.
- Conserver l’architecture actuelle.
- Prioriser la documentation, l’organisation et l’automatisation.

## Convention de commits

- feat(api)
- feat(agent)
- fix(environment)
- refactor(reward)
- docs(readme)
- test(training)

## Comment basculer sur une branche

```bash
git checkout develop
git checkout -b feature/your-module
```

## Comment committer et pousser

```bash
git add .
git commit -m "feat(api): add endpoint documentation"
git push -u origin feature/your-module
```

## Comment ouvrir une Pull Request

Ouvrir une PR depuis votre branche de fonctionnalité vers develop sur GitHub.

## Documentation supplémentaire

- Page équipe: docs/team_structure.html
- Page branches: docs/branch_responsibilities.html
- Script de branches: scripts/create_branches.sh

## Démarrage rapide

```bash
docker compose up --build
```

## Exécution locale sans Docker

Le frontend et le backend peuvent être lancés directement depuis le répertoire racine du projet.

```bash
./run_local.sh
```

Cela démarre le backend sur `http://127.0.0.1:8000` et le frontend sur `http://127.0.0.1:5173`.
