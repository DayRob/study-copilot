# Veille Culture Cyber — Design

Date: 2026-07-08

## Contexte et objectif

Ajouter à Study Copilot une capacité de veille et de capitalisation de connaissances en cybersécurité, à partir de sources faisant autorité (ANSSI, CERT-FR pour le MVP ; ENISA, NIST, MITRE ATT&CK, OWASP, CIS envisagés ensuite). Le scraping est volontairement maison plutôt qu'un agrégateur RSS générique, pour garder le contrôle total sur les sources retenues.

Study Copilot est déjà "l'outil d'apprentissage" mentionné dans le besoin initial : il dispose d'une ingestion (PDF/DOCX/code), d'un stockage SQLite + vectoriel (sqlite-vec), d'un RAG Q&A avec citations, d'un export Obsidian automatique et d'une abstraction LLM (Ollama/Anthropic). Ce projet s'intègre donc à l'existant plutôt que de dupliquer cette logique.

Décisions actées avec l'utilisateur :
- Intégration à Study Copilot (pas de projet séparé).
- Contenu cyber indexé dans le **même RAG** que les cours (Q&A et génération de quiz peuvent l'utiliser directement, sans étape d'export séparée).
- Déclenchement **manuel** pour le MVP (bouton "Sync" / endpoint API), pas de cron.
- Export Obsidian dans un sous-dossier **`Cours CPE/Culture Cyber/`** du vault existant.
- MVP sur 2 sources (ANSSI + CERT-FR), bout en bout, avant d'élargir.

## Architecture

Nouveau module `backend/app/cyber/`, parallèle à `ingestion/`, qui réutilise au maximum la plomberie existante :

```
backend/app/cyber/
  connectors/
    base.py        # Protocol: list_items(), fetch_item()
    anssi.py
    cert_fr.py
  pipeline.py       # orchestration fetch -> dedup -> tag -> chunk -> embed -> store -> export
  taxonomy.py       # chargement du fichier de config taxonomie
  taxonomy.yaml     # config externalisée des 5 axes + vocabulaires contrôlés
  models.py         # dataclasses pivot (RawItemRef, RawItem, CyberItem, ...)
```

### Connecteurs (MVP : ANSSI + CERT-FR)

- Un module par source, implémentant le protocole `Connector` :
  - `list_items() -> list[RawItemRef]` : liste des entrées disponibles (url, titre, date approximative).
  - `fetch_item(ref) -> RawItem` : contenu complet d'une entrée (texte extrait, date de publication précise, métadonnées brutes).
- Méthode d'extraction : **flux RSS/Atom en priorité** (ANSSI et CERT-FR publient tous deux des flux officiels), qui donnent titre/URL/date structurés gratuitement. Une seule requête HTTP par item est nécessaire ensuite pour récupérer le corps complet de la page. Le scraping HTML brut n'est utilisé qu'en dernier recours si un flux n'existe pas ou est incomplet.
- Respect de `robots.txt` (stdlib `urllib.robotparser`), rate-limiting par domaine (délai minimal configurable entre requêtes), User-Agent identifiable, retry avec backoff sur erreurs réseau transitoires.

### Pipeline (`cyber/pipeline.py`)

Pour chaque connecteur configuré :
1. `list_items()` → liste des entrées.
2. Pour chaque entrée : si l'URL est déjà connue et que le hash du contenu extrait est identique → skip (compteur `skipped`).
3. Sinon : `fetch_item()` → extraction du texte → génération d'un résumé reformulé + tagging taxonomique via le LLM configuré (réutilise `llm/factory.py`, même mécanisme `complete_structured` que `rag/overview.py`, schéma JSON contraint aux vocabulaires de `taxonomy.yaml`).
4. Chunking du texte (réutilise le découpage "prose" de `ingestion/chunking.py`).
5. Embedding des chunks (réutilise `ingestion/embed.py`).
6. Upsert dans `cyber_items` / `cyber_chunks` / `cyber_chunk_embeddings` (par URL).
7. Export Obsidian de l'item (best-effort, n'échoue jamais le pipeline).

Dédoublonnage MVP : hash de contenu uniquement (skip si inchangé). La détection de quasi-doublons sémantiques inter-sources est explicitement hors scope du MVP (YAGNI avec seulement 2 sources) — à ajouter plus tard si la liste de connecteurs grandit et que des chevauchements de contenu apparaissent en pratique.

### Modèle de données (pivot)

Nouvelles tables (migration `0003_cyber_veille.sql`), **parallèles** à `source_files`/`chunks`/`chunk_embeddings` plutôt qu'une extension de ces tables : SQLite ne permet pas d'ajouter proprement une contrainte "exactement un parent FK renseigné" à une table existante sans la reconstruire, et cette séparation évite de toucher au pipeline de cours déjà fonctionnel.

```sql
CREATE TABLE cyber_items (
    id INTEGER PRIMARY KEY,
    connector TEXT NOT NULL,            -- 'anssi' | 'cert_fr' | ...
    url TEXT NOT NULL UNIQUE,           -- URL canonique = clé de dédup
    title TEXT NOT NULL,
    published_at TEXT,                 -- date de publication déclarée par la source
    fetched_at TEXT NOT NULL,          -- date de récupération (citation obligatoire)
    content_hash TEXT NOT NULL,
    raw_text TEXT NOT NULL,            -- texte extrait complet (citations courtes uniquement à l'export)
    summary TEXT,                      -- résumé reformulé par le LLM
    content_type TEXT,                 -- axe 1 (taxonomy.yaml)
    technical_domain TEXT,             -- axe 2
    level TEXT,                        -- axe 3
    authority_source TEXT NOT NULL,    -- axe 4
    referentiel TEXT,                  -- axe 5 (nullable)
    tags_json TEXT,                    -- tags libres/mots-clés détectés
    generation_model TEXT,
    last_synced_at TEXT NOT NULL
);

CREATE TABLE cyber_chunks (
    id INTEGER PRIMARY KEY,
    cyber_item_id INTEGER NOT NULL REFERENCES cyber_items(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL CHECK(content_type IN ('prose')),
    text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL
);

CREATE TABLE cyber_sync_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    items_found INTEGER NOT NULL DEFAULT 0,
    items_added INTEGER NOT NULL DEFAULT 0,
    items_updated INTEGER NOT NULL DEFAULT 0,
    items_skipped INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running','completed','failed')),
    error TEXT
);
```

`cyber_chunk_embeddings` (vec0, dimension = `settings.embedding_dim`) est créée au runtime dans `db/connection.py`, à côté de `chunk_embeddings` existante, avec le même trigger de nettoyage sur suppression.

### Taxonomie (`cyber/taxonomy.yaml`)

Fichier de config externalisé définissant les 5 axes et leurs vocabulaires contrôlés :
1. Type de contenu (référentiel/norme, guide, alerte/vulnérabilité, fiche protocole, fiche outil, actualité)
2. Domaine technique (réseau, cryptographie, IAM, infrastructure, cloud, applicatif/dev, gouvernance/conformité, réponse à incident)
3. Niveau (fondamental, avancé)
4. Source d'autorité (ANSSI, CERT-FR, ENISA, NIST, MITRE, OWASP, CIS — extensible)
5. Référentiel associé (optionnel : ex. contrôle CIS, catégorie MITRE ATT&CK, chapitre ISO 27002)

Le LLM reçoit ce vocabulaire dans son prompt de tagging (`complete_structured`, schéma JSON avec `enum` par axe) — pas de classification hardcodée en Python. Une correction manuelle a posteriori (édition directe des colonnes en base, ou dans le futur frontend) reste possible.

### Retriever / RAG

`rag/retriever.py::retrieve()` est étendu pour interroger les deux tables vec0 (`chunk_embeddings` et `cyber_chunk_embeddings`), fusionner les résultats par distance, puis joindre chacun à sa table de métadonnées respective (`source_files`/`subjects` ou `cyber_items`). Le type de résultat (`RetrievedChunk`) gagne un champ discriminant (`origin: 'course' | 'cyber'`) pour que l'affichage des citations distingue les deux. Pas de filtre de scope pour le MVP (les résultats se mélangent, cités par leur source d'origine).

### API

Nouveau routeur `backend/app/api/cyber.py`, calqué sur `api/ingest.py` :
- `POST /cyber/sync` : démarre une synchronisation en tâche de fond (verrou atomique identique à `ingest.py::_try_claim`), parcourt tous les connecteurs configurés.
- `GET /cyber/status` : état courant + dernier rapport (`cyber_sync_runs`).

### Export Obsidian (`backend/app/obsidian/cyber_export.py`)

- Dossier : `Cours CPE/Culture Cyber/` (sous le vault existant, `EXPORT_FOLDER_NAME` de `obsidian/export.py`).
- Un fichier `.md` par `cyber_item`, frontmatter YAML : `source`, `connector`, `url`, `published_at`, `fetched_at`, `content_type`, `technical_domain`, `level`, `authority_source`, `referentiel`, `tags`.
- Corps : résumé reformulé par le LLM + un court extrait verbatim plafonné (pas de reproduction intégrale du texte protégé) + lien vers l'URL d'origine.
- Wikilinks entre fiches partageant un même référentiel ou tag (même mécanisme que les liens de concepts existants).
- Un ou plusieurs MOC (`_Index.md` par domaine technique), régénérés à chaque sync.
- Écriture idempotente (overwrite), déclenchée en best-effort après chaque `POST /cyber/sync`, sans jamais faire échouer le pipeline (même pattern que `_sync_obsidian_export()` dans `ingestion/pipeline.py`).

### Frontend

Un onglet "Veille Cyber" minimal (bouton Sync + liste des items avec leurs tags), sur le modèle de `pages/Subjects.tsx`. Le Chat existant n'a pas besoin de modification pour bénéficier du nouveau contenu (le retriever fusionne déjà les deux sources).

### Configuration (`config.py` / `.env`)

Nouveaux settings :
- `cyber_connectors: list[str]` — connecteurs actifs (ex: `["anssi", "cert_fr"]`).
- `cyber_rate_limit_seconds: float` — délai minimal entre requêtes vers un même domaine.
- `cyber_user_agent: str` — User-Agent identifiable pour les requêtes HTTP.

### Tests

Fixtures HTML/RSS enregistrées sous `backend/tests/fixtures/cyber/anssi/` et `.../cert_fr/`. Tests sur : parsing des flux (connecteurs), dédoublonnage par hash, tagging taxonomique (LLM mocké), logique d'upsert du pipeline. Aucun test ne dépend d'un appel réseau réel.

## Hors scope (MVP)

- Détection de quasi-doublons sémantiques inter-sources.
- Cron / scheduler (déclenchement manuel uniquement).
- Filtre de scope "cyber seul" vs "cours seuls" dans le Chat.
- Connecteurs autres qu'ANSSI et CERT-FR (ENISA, NIST, MITRE, OWASP, CIS — prévus ensuite, l'architecture "un module par connecteur" les rend faciles à ajouter).
- API REST dédiée pour un outil externe (non nécessaire : le contenu est déjà requêtable via le RAG/API existants de Study Copilot).
