# Carnet de bord — GrandNexus 6.4 → 6.5 (réparation)

Branche `main`, tag `v6.4-raw` = extraction brute (témoin). Chaque réparation = 1 commit.
Rejouer : cœur = `tools/extract_notebook.py` puis `tools/run_all.sh` ; couche 15/05 = `tools/extract_layer_1505.py` puis `tools/run_layer_1505.sh`.

| # | Hypothèse | Résultat | Décision |
|---|-----------|----------|----------|
| 1 | Le notebook est cassé par sa structure plus que par sa logique | imports : 8/41 modules de code (témoin brut) → 41/41 après R1–R9 | packager, puis intégrer |
| 2 | Des noms viennent de l'espace de noms partagé de Colab | pyflakes : 12 noms indéfinis dans 9 fichiers → 0 (R10) | garder pyflakes dans la boucle |
| 3 | pyflakes trouve aussi de vrais bugs | 2 bugs logiques (boucle de clustering qui ne progressait pas, arrêt d'ErrorRecovery en code mort) → corrigés (R11) | idem |
| 4 | Le système peut démarrer d'un bloc | boot() : 16/16 étapes OK (R12, boot.py) | tester le câblage |
| 5 | Mémoire sémantique et gestionnaire de graphe partagent un graphe | NON : 2 graphes séparés → 1 graphe partagé pour 7 modules (R13) | ok |
| 6 | La perception reconnaît le type d'entrée | 5/8 : maths et `import` classés TEXT (égalité de scores, TEXT gagne par ordre) | à calibrer (mode laboratoire) |
| 7 | Le routage par priorité bat le hasard | 1/5 vs 0.8/5 (témoin aléatoire) : pas de différence réelle | le goulot n'est pas le routage mais le passage perception → raisonnement (le raisonneur attend prémisses/règles structurées) |

| 8 | Le raisonneur ne reçoit pas les prémisses | reason() rangeait le contexte sous une autre clé que celle lue par les stratégies → corrigé (R14) | brancher l'extracteur |
| 9 | Une extraction de prémisses suffit pour raisonner | voie A : 12/12 dans la grammaire vs 6/12 (toujours-oui), 3/12 (hasard), 2/12 (ancienne voie) ; 0/5 hors grammaire, 0 faux « oui » | élargir l'extracteur (verbes, pronoms, relations) |
| 10 | La couche 15/05 est compatible avec NexusCore | API : oui (register/get/send_message uniquement). Noms : 1 vrai conflit (working_memory v2) détecté et bloqué | couche extraite, collisions en _v2 |
| 11 | L'orchestrateur répond aux questions | après R15-R23, R27 : 12/12, 0 réponse d'une autre question, ~1 s/question (10 itérations × 0,1 s codées en dur) | ok |
| 12 | Tout tourne ensemble sur un NexusCore démarré | AVANT R24 : l'horloge mourait après 1 tick (file de messages : TypeError à priorité égale). APRÈS : ~8 000 messages en 3 s, 13 modules vivants, 1 seule erreur (gymnasium absent) | corriger les adressages et l'arrêt lent |
| 13 | Le CognitionManager parle à ses modules | 12 méthodes appelées n'existaient pas (quick_scan, evaluate, create_plan…) → ponts de délégation (R25) | à valider en mode threads |
| 14 | Les deux WorkingMemory peuvent cohabiter | v2 renommée « working_memory_v2 », AffectRegulator suit (R28) : les deux tournent ensemble, 0 erreur | ok (décision Khaled) |
| 15 | L'extracteur généralise au-delà de sa grammaire | dev 0/5 → 5/5, régression 12/12 conservée ; témoin figé AVANT réglage (commit d5d2894) : 6/7 vs 4/7 toujours-oui, 1,7/7 hasard ; seul échec = féminin « végétarienne » | morphologie féminine ; prochain témoin écrit par Khaled |
| 16 | Les dépendances lourdes sont un mur | pip seul (niveau 1) : 91 → 99 modules importables. Mais Redis/MongoDB = serveurs (connexion refusée / blocage) ; EvolutionManager exige KernelBridge | niveau 1 maintenant, serveurs quand un essai les demande |
| 17 | La voie raisonne sur des phrases qu'elle n'a jamais vues (témoin de Khaled, 10 items) | **4/10 = toujours-inconnu (4/10)** → K1 ÉCHOUÉ ; 0 « oui » à tort → K2 PASSÉ. Sur les 4 réussites, 2 viennent d'une analyse ratée (n°1, n°6), 2 d'un vrai mécanisme (n°3 existentiel, n°9 pas d'affirmation du conséquent) | capacités manquantes identifiées, nouveau témoin requis après réparation |
| 18 | L'échec vient-il du manque de pratique, de la langue, du savoir ou du moteur ? (oracles par couche, tools/lab_niveaux.py) | pratique : 3 passages = 4,4,4 (aucun apprentissage possible) ; +langue 6/10 ; +savoir 5/10 ; +inférences 7/10 ; +chaînage complet 9/10. Le moteur n'enchaîne que 2 déductions sur 4 demandées | priorité 1 = moteur (profondeur, contraposée, cohérence globale) ; 2 = langue (essai comparatif analyseur syntaxique / LLM / grammaire) ; 3 = savoir ; 4 = boucle de correction |
| 19 | Engine depth is the cheapest bottleneck | R32 fixpoint chaining + contraposition: depth probe 2/4 -> 4/4; Khaled set (seen) grammar 4 -> 5/10 (#8 via contraposition); no regression (12/12, 5/5, 6/7, orchestrator 12/12) | wire the LLM as translator |
| 20 | Claude can serve as an anchored translator without breaking K2 | offline pipeline test with a fake SDK: unquoted premise rejected, knowledge-dependent answers flagged (strict vs with-knowledge), apples -> 3 - 1 + 2 = 4 via sympy, hybrid makes 0 API call when the grammar decides. Real-model scores: pending Khaled's Colab run | bake-off on a FRESH set written by Khaled |
| 21 | Claude is really called through Khaled's key (dashboard showed no usage) | direct call msg_011CgDtZk93TyGNGQF4ZVMJ9 (18+4 tokens); GrandNexus receipts msg_011CgDtZtTbpweAcJ19gBAaU and msg_011CgDtZyPWrpueA8EYAUhdZ (534 in + 207 out); apples 4, seeds 6; Colab AI patch = temperature removal only, no rerouting | dashboard delay or other workspace view; run the bake-off |

Raw result: tests_lab/resultats/temoin_khaled_2026-10-16_mesure1.txt. Ce témoin est désormais « vu » :
après les réparations, son score ne vaudra plus comme mesure de généralisation.

Biais à garder en tête (n°15) : le témoin figé a été écrit par Claude, qui connaît sa propre grammaire.
Le piège « Some birds sing » a pu orienter le choix de traiter « some » comme non universel. Un témoin
rédigé par quelqu'un d'autre reste la vraie mesure.

## Ce qui n'est PAS encore fait
- Couche 15/05 : sans requirements-extra.txt, 13 modules attendent une dépendance externe (torch, redis, neo4j, pymongo, pybullet, gymnasium, deap, opentelemetry, slack_sdk, sentence_transformers, sse_starlette).
- Adressages morts en fonctionnement : self_model → « monitor » (le cœur dit « cognitive_monitor »), messages envoyés avant le démarrage de leur destinataire (ordre de démarrage).
- Arrêt lent (~15 s, join avec timeouts) et 2 threads qui survivent (dont Report_Thread du CognitiveMonitor).
- Deux notions nommées CognitiveContext (état de l'orchestrateur / contexte de requête) à réconcilier.
- Horloge : canal « fast » déclaré non sain malgré ~120 ticks en 3 s (critère à lire).
- Seuls PerceptionCore et ReasoningCore déclarent des capacités (@cognitive_capability). Les 20 autres modules ne sont joignables que par appel direct ou par le bus d'événements.
- `CognitionManager.start()` (threads de fond) non testé : boot(start_threads=True).
- Doublons conservés côte à côte, non fusionnés : graph_engine_v1, llm_engine_lite (fallback + embeddings à greffer dans llm_engine), resource_manager_ml.
