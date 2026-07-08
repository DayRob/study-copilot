"""Curated cybersecurity fundamentals NOT necessarily covered in the user's
own courses. Each entry gives the LLM a precise, pre-written factual anchor
to turn into a question -- the model only phrases/distracts, it never has to
invent or recall the fact itself. This keeps hallucination risk low even
though these questions aren't grounded in retrieved course chunks (unlike
the rest of the practice generator)."""

GENERAL_CYBER_KNOWLEDGE: list[dict[str, str]] = [
    {"topic": "OWASP Top 10", "anchor_fact": "Broken Access Control est la catégorie n°1 de l'OWASP Top 10 2021, devant les défaillances cryptographiques."},
    {"topic": "Triptyque CIA", "anchor_fact": "Le triptyque CIA en sécurité désigne Confidentialité, Intégrité et Disponibilité (Confidentiality, Integrity, Availability)."},
    {"topic": "Port SSH", "anchor_fact": "Le port par défaut du protocole SSH est le port 22."},
    {"topic": "Port HTTPS", "anchor_fact": "Le port par défaut de HTTPS est le port 443."},
    {"topic": "Chiffrement symétrique vs asymétrique", "anchor_fact": "Le chiffrement symétrique utilise la même clé pour chiffrer et déchiffrer (ex: AES), contrairement au chiffrement asymétrique qui utilise une paire clé publique/clé privée (ex: RSA)."},
    {"topic": "Hachage vs chiffrement", "anchor_fact": "Le hachage (ex: SHA-256) est une fonction à sens unique non réversible, contrairement au chiffrement qui est réversible avec la bonne clé."},
    {"topic": "XSS", "anchor_fact": "Une attaque XSS (Cross-Site Scripting) consiste à injecter du code JavaScript malveillant dans une page web consultée par d'autres utilisateurs."},
    {"topic": "Injection SQL", "anchor_fact": "Une injection SQL exploite une entrée utilisateur non filtrée insérée directement dans une requête SQL pour en altérer le comportement."},
    {"topic": "CSRF", "anchor_fact": "Une attaque CSRF (Cross-Site Request Forgery) force un utilisateur authentifié à exécuter une action non désirée sur un site web sans son consentement."},
    {"topic": "Faille zero-day", "anchor_fact": "Une vulnérabilité zero-day est une faille de sécurité inconnue de l'éditeur au moment où elle est exploitée, donc sans correctif disponible."},
    {"topic": "MITRE ATT&CK", "anchor_fact": "Le framework MITRE ATT&CK catalogue les tactiques et techniques des attaquants, organisées par phase d'une attaque (reconnaissance, accès initial, persistance, etc.)."},
    {"topic": "Principe du moindre privilège", "anchor_fact": "Le principe du moindre privilège consiste à n'accorder à un utilisateur ou processus que les droits strictement nécessaires à sa tâche."},
    {"topic": "Défense en profondeur", "anchor_fact": "La défense en profondeur consiste à empiler plusieurs couches de sécurité indépendantes plutôt que de compter sur un seul mécanisme de protection."},
    {"topic": "Phishing", "anchor_fact": "Le phishing est une technique d'ingénierie sociale visant à tromper une victime pour lui faire divulguer des informations sensibles, via un email ou site imitant une entité légitime."},
    {"topic": "Attaque de l'homme du milieu", "anchor_fact": "Une attaque MITM (man-in-the-middle) consiste à intercepter, et potentiellement modifier, les communications entre deux parties sans qu'elles s'en rendent compte."},
    {"topic": "DDoS", "anchor_fact": "Une attaque DDoS (Distributed Denial of Service) vise à rendre un service indisponible en le submergeant de trafic provenant de multiples sources."},
    {"topic": "VPN", "anchor_fact": "Un VPN (Virtual Private Network) crée un tunnel chiffré entre un appareil et un réseau distant, masquant le trafic et l'adresse IP réelle de l'utilisateur."},
    {"topic": "Pare-feu", "anchor_fact": "Un pare-feu filtre le trafic réseau entrant et sortant selon des règles prédéfinies, bloquant ou autorisant les connexions."},
    {"topic": "IDS vs IPS", "anchor_fact": "Un IDS détecte et alerte sur une activité suspecte sans agir, tandis qu'un IPS peut bloquer activement le trafic malveillant."},
    {"topic": "Authentification multi-facteurs", "anchor_fact": "L'authentification multi-facteurs (MFA) combine au moins deux catégories de preuves d'identité : quelque chose que l'on sait (mot de passe), que l'on possède (token) ou que l'on est (biométrie)."},
    {"topic": "Salage des mots de passe", "anchor_fact": "Le salage (salting) consiste à ajouter une valeur aléatoire unique à chaque mot de passe avant hachage, empêchant l'utilisation de tables précalculées (rainbow tables)."},
    {"topic": "Nmap", "anchor_fact": "Nmap est un outil de scan réseau utilisé pour découvrir les hôtes actifs, les ports ouverts et les services qui y tournent."},
    {"topic": "Débordement de tampon", "anchor_fact": "Un buffer overflow se produit quand un programme écrit plus de données dans une zone mémoire que sa capacité allouée, pouvant corrompre la mémoire adjacente et parfois permettre l'exécution de code arbitraire."},
    {"topic": "Ingénierie sociale", "anchor_fact": "L'ingénierie sociale désigne les techniques de manipulation psychologique visant à pousser une personne à divulguer des informations ou effectuer une action compromettant la sécurité."},
    {"topic": "PKI", "anchor_fact": "Une infrastructure à clés publiques (PKI) gère l'émission, la validation et la révocation de certificats numériques qui lient une identité à une clé publique."},
    {"topic": "Handshake TLS", "anchor_fact": "Le handshake TLS permet au client et au serveur de s'authentifier mutuellement (optionnel côté client) et de négocier une clé de session symétrique pour chiffrer la suite de la communication."},
    {"topic": "Ransomware", "anchor_fact": "Un ransomware chiffre les données de la victime et exige une rançon, généralement en cryptomonnaie, en échange de la clé de déchiffrement."},
    {"topic": "Escalade de privilèges", "anchor_fact": "L'escalade de privilèges consiste à exploiter une faille pour obtenir des droits d'accès supérieurs à ceux initialement accordés, verticale (utilisateur vers admin) ou horizontale (entre comptes de même niveau)."},
]
