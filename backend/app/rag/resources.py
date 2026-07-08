"""Curated public resource links, matched by keyword against LLM-extracted
key topics. Deliberately NOT LLM-generated: model-invented URLs are prone to
hallucination (wrong slugs, dead links), so this stays a small hand-picked
list of stable, well-known documentation sites. Anything that doesn't match
falls back to a safe search-query link rather than a guessed destination."""

CURATED_RESOURCES: list[dict] = [
    {"keywords": ["terraform"], "label": "Terraform — Documentation officielle", "url": "https://developer.hashicorp.com/terraform/docs"},
    {"keywords": ["ansible"], "label": "Ansible — Documentation officielle", "url": "https://docs.ansible.com/"},
    {"keywords": ["docker", "conteneur", "container"], "label": "Docker — Documentation officielle", "url": "https://docs.docker.com/"},
    {"keywords": ["kubernetes", "k8s"], "label": "Kubernetes — Documentation officielle", "url": "https://kubernetes.io/docs/home/"},
    {"keywords": ["owasp", "vulnerabilit", "injection sql", "xss"], "label": "OWASP Top 10", "url": "https://owasp.org/www-project-top-ten/"},
    {"keywords": ["mitre", "att&ck", "attack framework", "threat"], "label": "MITRE ATT&CK", "url": "https://attack.mitre.org/"},
    {"keywords": ["spring boot"], "label": "Spring Boot — Documentation officielle", "url": "https://spring.io/projects/spring-boot"},
    {"keywords": ["spring"], "label": "Spring Framework — Documentation officielle", "url": "https://spring.io/projects/spring-framework"},
    {"keywords": ["oauth"], "label": "OAuth 2.0 — Guide officiel", "url": "https://oauth.net/2/"},
    {"keywords": ["jwt", "json web token"], "label": "JWT — Introduction", "url": "https://jwt.io/introduction"},
    {"keywords": ["nmap"], "label": "Nmap — Reference Guide", "url": "https://nmap.org/book/man.html"},
    {"keywords": ["metasploit"], "label": "Metasploit — Documentation", "url": "https://docs.metasploit.com/"},
    {"keywords": ["wireshark"], "label": "Wireshark — Documentation", "url": "https://www.wireshark.org/docs/"},
    {"keywords": ["aws", "amazon web services"], "label": "AWS — Documentation", "url": "https://docs.aws.amazon.com/"},
    {"keywords": ["azure"], "label": "Azure — Documentation", "url": "https://learn.microsoft.com/en-us/azure/"},
    {"keywords": ["gcp", "google cloud"], "label": "Google Cloud — Documentation", "url": "https://cloud.google.com/docs"},
    {"keywords": ["cisco", "devnet"], "label": "Cisco DevNet", "url": "https://developer.cisco.com/"},
    {"keywords": ["rest", "api rest"], "label": "REST API — Guide de référence", "url": "https://restfulapi.net/"},
    {"keywords": ["microservice"], "label": "Microservices (Martin Fowler)", "url": "https://martinfowler.com/articles/microservices.html"},
    {"keywords": ["osint"], "label": "OSINT Framework", "url": "https://osintframework.com/"},
    {"keywords": ["python"], "label": "Python — Documentation officielle", "url": "https://docs.python.org/3/"},
    {"keywords": ["java"], "label": "Java — Documentation officielle", "url": "https://docs.oracle.com/en/java/"},
    {"keywords": ["typescript"], "label": "TypeScript — Documentation officielle", "url": "https://www.typescriptlang.org/docs/"},
    {"keywords": ["react"], "label": "React — Documentation officielle", "url": "https://react.dev/"},
    {"keywords": ["spark", "apache spark"], "label": "Apache Spark — Documentation", "url": "https://spark.apache.org/docs/latest/"},
    {"keywords": ["hadoop"], "label": "Apache Hadoop — Documentation", "url": "https://hadoop.apache.org/docs/stable/"},
    {"keywords": ["sql", "base de donnees relationnelle", "postgres"], "label": "PostgreSQL — Documentation", "url": "https://www.postgresql.org/docs/"},
    {"keywords": ["reseau", "network", "protocole reseau", "tcp/ip"], "label": "RFC Editor (standards Internet)", "url": "https://www.rfc-editor.org/"},
]

MAX_RESOURCES = 6


def _normalize(text: str) -> str:
    return text.lower().strip()


def match_resources(key_topics: list[dict], subject_name: str) -> list[dict]:
    # Defensive: an under-following local LLM could omit 'concept' on one
    # entry despite the schema marking it required -- don't let one bad
    # entry take down overview generation for the whole subject.
    concepts = [t["concept"] for t in key_topics if isinstance(t, dict) and t.get("concept")]
    haystack = [_normalize(t) for t in [*concepts, subject_name]]
    matched: list[dict] = []
    seen_urls: set[str] = set()

    for entry in CURATED_RESOURCES:
        if any(kw in text for kw in entry["keywords"] for text in haystack):
            if entry["url"] not in seen_urls:
                matched.append({"label": entry["label"], "url": entry["url"]})
                seen_urls.add(entry["url"])
        if len(matched) >= MAX_RESOURCES:
            break

    if len(matched) < 2:
        # Safe fallback: a search-query link (not a guessed destination page)
        # for the first couple of topics we couldn't match to a curated doc.
        for concept in concepts[:2]:
            query = concept.replace(" ", "+")
            matched.append(
                {
                    "label": f"Rechercher \"{concept}\"",
                    "url": f"https://www.google.com/search?q={query}",
                }
            )

    return matched[:MAX_RESOURCES]
