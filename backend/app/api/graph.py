import json

from fastapi import APIRouter

from app.db.connection import get_connection
from app.practice.general_knowledge import GENERAL_CYBER_KNOWLEDGE

router = APIRouter(prefix="/knowledge-graph", tags=["graph"])

GENERAL_NODE_ID = "subject:general"


@router.get("")
def get_knowledge_graph():
    """Derived on the fly from subject_overviews -- no separate graph table.
    Subjects are nodes; each key concept is also a node, shared across every
    subject whose overview mentions it, so the edges are exactly the same
    concept-linking structure used in the Obsidian export. The curated
    general-cyber-knowledge list is added as a synthetic 'subject' too, even
    if the player has never played that mode yet (no DB row needed)."""
    with get_connection() as conn:
        subjects = conn.execute("SELECT id, name, year, semester FROM subjects").fetchall()
        overviews = conn.execute("SELECT subject_id, key_topics FROM subject_overviews").fetchall()

    subject_by_id = {s["id"]: s for s in subjects}
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for s in subjects:
        node_id = f"subject:{s['id']}"
        nodes[node_id] = {
            "id": node_id,
            "type": "subject",
            "label": s["name"],
            "year": s["year"],
            "semester": s["semester"],
        }

    for row in overviews:
        subject = subject_by_id.get(row["subject_id"])
        if not subject:
            continue
        subject_node_id = f"subject:{subject['id']}"
        # One malformed row (e.g. from an older key_topics shape, or a
        # partial/corrupt LLM response that slipped past validation) must not
        # take down the graph for every other subject -- skip just this one.
        try:
            topics = json.loads(row["key_topics"])
            for topic in topics:
                concept = topic["concept"].strip()
                if not concept:
                    continue
                concept_node_id = f"concept:{concept.lower()}"
                if concept_node_id not in nodes:
                    nodes[concept_node_id] = {
                        "id": concept_node_id,
                        "type": "concept",
                        "label": concept,
                        "explanation": topic.get("explanation", ""),
                    }
                edges.append({"source": subject_node_id, "target": concept_node_id})
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError):
            continue

    nodes[GENERAL_NODE_ID] = {
        "id": GENERAL_NODE_ID,
        "type": "subject",
        "label": "Culture Cyber Générale",
        "year": "Général",
        "semester": None,
        "virtual": True,
    }
    for item in GENERAL_CYBER_KNOWLEDGE:
        concept_node_id = f"concept:general:{item['topic'].lower()}"
        nodes[concept_node_id] = {
            "id": concept_node_id,
            "type": "concept",
            "label": item["topic"],
            "explanation": item["anchor_fact"],
            "source": "general",
        }
        edges.append({"source": GENERAL_NODE_ID, "target": concept_node_id})

    return {"nodes": list(nodes.values()), "edges": edges}
