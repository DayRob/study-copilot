<h1 align="center">🎓 Study Copilot</h1>

<p align="center">
  <strong>Un copilote de révision 100 % local : il lit tous mes cours, répond avec des citations, génère des fiches et transforme les révisions en jeu.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white" alt="Vite">
  <img src="https://img.shields.io/badge/SQLite-sqlite--vec-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/LLM-Ollama%20%7C%20Claude-black" alt="LLM">
  <img src="https://img.shields.io/badge/Obsidian-export-7C3AED?logo=obsidian&logoColor=white" alt="Obsidian">
</p>

---

## Le projet

Deux années de cycle ingénieur (CPE Lyon, 4A et 5A), ce sont des centaines de PDF, de documents Word et de projets de code éparpillés. **Study Copilot** les indexe tous et les rend exploitables pour réviser :

- 💬 **Questions / réponses** sur l'ensemble des cours, avec les **sources citées** (RAG, réponse en streaming)
- 📚 **Fiches de révision** générées par matière : résumé et notions clés expliquées
- 🗺️ **Carte des connaissances** : graphe interactif reliant matières et notions communes
- 🎮 **Mode jeu** : quiz générés à partir des cours, difficulté adaptative, XP, séries et niveaux, révision espacée des questions ratées
- 🔗 **Export Obsidian** automatique : chaque fiche et chaque notion devient une note liée par `[[wikilinks]]`
- 🔄 **Synchronisation automatique** : un changement dans les dossiers de cours (ou dans ses notes Obsidian) déclenche une ré-ingestion incrémentale

Tout tourne en local : embeddings calculés sur la machine, base SQLite unique, API accessible uniquement en loopback. Le LLM peut être local (**Ollama**, gratuit) ou distant (**Claude**, meilleure qualité).

## Architecture

```
 Dossiers de cours (PDF, DOCX, code)          Coffre Obsidian
            │  watchdog (sync auto)                  ▲
            ▼                                        │ export markdown
 ┌─────────────────────────────────────────────────────────────────┐
 │  Backend FastAPI                                                │
 │  ingestion → extraction → découpage → embeddings (e5, local)    │
 │  SQLite + sqlite-vec (données relationnelles + vecteurs)        │
 │  RAG : recherche vectorielle → LLM (Ollama ou Claude)           │
 │  fiches · graphe de notions · moteur de jeu (XP, difficulté)    │
 └─────────────────────────────────────────────────────────────────┘
            ▲  HTTP (localhost uniquement)
            │
 ┌─────────────────────────────────────────────────────────────────┐
 │  Frontend React + Vite : Questions · Cours · Carte · Jeu        │
 └─────────────────────────────────────────────────────────────────┘
```

| Module | Rôle |
|---|---|
| `backend/app/ingestion/` | Parcours des dossiers, extraction PDF / DOCX / code, découpage, embeddings, surveillance des fichiers |
| `backend/app/rag/` | Recherche vectorielle, Q&A avec citations, génération des fiches |
| `backend/app/practice/` | Génération des questions de quiz |
| `backend/app/game/` | Règles du jeu : paliers de difficulté, XP, niveaux |
| `backend/app/obsidian/` | Export des fiches et notions vers le coffre Obsidian |
| `backend/app/llm/` | Abstraction du fournisseur LLM (Ollama / Anthropic) |
| `frontend/src/pages/` | Onglets Questions, Cours, Carte et Jeu |

## Installation

### Prérequis

- Python 3.11+ et [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- Un LLM, au choix (variable `LLM_PROVIDER`) :
  - **Ollama** (par défaut, gratuit, local) : installer [Ollama](https://ollama.com) puis `ollama pull llama3.1:8b`
  - **Anthropic** (payant à l'usage) : une clé API sur https://console.anthropic.com

L'ingestion et la recherche fonctionnent sans LLM.

### Configuration

```bash
cp .env.example backend/.env
# Éditer backend/.env : chemins des cours (COURSE_ROOTS), coffre Obsidian (optionnel), fournisseur LLM
```

### Lancement

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Frontend (autre terminal)
cd frontend
npm install
npm run dev
```

Ouvrir http://localhost:5173. Au premier démarrage, le modèle d'embedding (`intfloat/multilingual-e5-base`, ~1 Go) est téléchargé puis mis en cache.

### Première ingestion

Depuis l'onglet **Cours**, cliquer sur **Sync now**, ou :

```bash
curl -X POST http://localhost:8000/ingest/run
curl http://localhost:8000/ingest/status
```

La première ingestion peut prendre plusieurs minutes ; les suivantes ne retraitent que les fichiers modifiés. Pour exclure des dossiers, créer un fichier `.ingestignore` (syntaxe gitignore) à la racine d'un dossier de cours.

## Sécurité

L'application est mono-utilisateur et sans authentification ; elle est donc conçue pour rester locale :

- API et frontend exposés uniquement sur `127.0.0.1`
- `TrustedHostMiddleware` pour bloquer les attaques par DNS rebinding
- CORS restreint à l'origine du frontend, méthodes `GET` / `POST` uniquement

## Feuille de route

- [x] Ingestion PDF / DOCX / code et stockage vectoriel local
- [x] Q&A avec citations
- [x] Fiches de révision et carte des connaissances
- [x] Mode jeu avec progression
- [x] Export Obsidian et synchronisation automatique
- [ ] Onglet **Veille cyber** (CERT-FR, ANSSI) intégré au RAG — en cours sur la branche `cyber-veille`
- [ ] Conteneurisation (Dockerfiles)

## Auteur

**Côme Villeroy de Galhau** — [@DayRob](https://github.com/DayRob)
