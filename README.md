# Study Copilot

Copilote personnel pour réviser 2 ans de cours (CPE 4A/5A) : questions/réponses avec citations, génération de quiz/exercices, suivi de progression. Voir le plan complet dans `.claude/plans` (ou l'historique de la conversation) pour le détail de l'architecture.

## Prérequis
- Python 3.10+ avec [uv](https://docs.astral.sh/uv/)
- Node 18+
- Un LLM pour la génération de réponses/quiz — deux options (voir `LLM_PROVIDER` dans `.env`) :
  - **Ollama (par défaut, gratuit)** : installe [Ollama](https://ollama.com), puis `ollama pull llama3.1:8b`. Tourne en local, sans clé API, sans coût récurrent.
  - **Anthropic (payant)** : une clé API sur https://console.anthropic.com, meilleure qualité de réponse mais facturé à l'usage (~1-15$/mois pour un usage perso, voir la conversation pour le détail).
- Aucun des deux n'est nécessaire pour tester l'ingestion et la recherche seules (100% locales et gratuites).

## Setup

```bash
cp .env.example backend/.env
# éditer backend/.env : vérifier COURSE_ROOTS, choisir LLM_PROVIDER (ollama par défaut)
```

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Le premier démarrage télécharge le modèle d'embedding local (`intfloat/multilingual-e5-base`, ~1GB, mis en cache par `sentence-transformers`).

### Frontend

```bash
cd frontend
npm install   # déjà fait si tu viens de cloner et lancer le setup initial
npm run dev
```

Ouvre http://localhost:5173.

## Ingestion

Depuis l'onglet "Sujets" de l'appli, clique sur "Sync now" — ou directement :

```bash
curl -X POST http://localhost:8000/ingest/run
curl http://localhost:8000/ingest/status
```

La première ingestion peut prendre plusieurs minutes (extraction + embedding local de tous les PDF/DOCX/code). Les ingestions suivantes sont incrémentales (seuls les fichiers modifiés sont retraités).

Pour exclure des dossiers spécifiques en plus des exclusions automatiques (node_modules, venvs, builds...), crée un fichier `.ingestignore` (syntaxe gitignore) directement à la racine de `4A/` ou `5A/`.

## État actuel

- ✅ Ingestion (PDF/DOCX/code) + stockage vectoriel local (`sqlite-vec`)
- ✅ Q&A avec citations (RAG streaming)
- ⏳ Génération de quiz/exercices — à venir
- ⏳ Dashboard de progression — à venir
