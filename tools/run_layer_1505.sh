#!/usr/bin/env bash
# Couche 15/05 : extraction puis réparations, un commit chacune.
set -e
cd "$(dirname "$0")"
declare -A MSG=(
 [r15_orchestrator_imports]="R15 orchestrateur: adaptateurs ReasoningEngine/LearningManager/PerceptionModule + fabrique sortie de la classe"
 [r16_layer_bugs]="R16 couche 15/05: dataclass Homeostasis, shell/JS collé (dialogue), alias grandnexus.dialogue, openai protégé"
 [r18_orchestrator_state]="R18 orchestrateur: état PERCEPTION référencé mais absent de l'énumération"
 [r19_working_memory_sort]="R19 WorkingMemory: tri sur le score seul (égalités -> TypeError)"
 [r20_working_memory_item]="R20 WorkingMemoryItem.access_count déclaré (utilisé partout, jamais défini)"
 [r21_orchestrator_session_output]="R21 orchestrateur: sortie limitée à la session courante (fuite de la réponse précédente)"
 [r22_orchestrator_cleanup]="R22 orchestrateur: actions finies libérées à chaque passage de file (famine après 1 question)"
 [r23_orchestrator_memory_queries]="R23 orchestrateur: requêtes mémoire typées (SemanticQuery/EpisodicQuery) + division par zéro en méta-analyse"
 [r17_resource_history]="R17 ResourceManager.get_usage_history (demandé par l'orchestrateur)"
)
for r in r15_orchestrator_imports r16_layer_bugs r17_resource_history r18_orchestrator_state r19_working_memory_sort r20_working_memory_item r21_orchestrator_session_output r22_orchestrator_cleanup r23_orchestrator_memory_queries; do
  python3 repairs.py "$r"
  (cd .. && git add -A && git commit -qm "${MSG[$r]}")
done
