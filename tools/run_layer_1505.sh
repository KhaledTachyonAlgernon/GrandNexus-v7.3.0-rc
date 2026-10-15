#!/usr/bin/env bash
# Couche 15/05 : extraction puis réparations, un commit chacune.
set -e
cd "$(dirname "$0")"
declare -A MSG=(
 [r15_orchestrator_imports]="R15 orchestrateur: adaptateurs ReasoningEngine/LearningManager/PerceptionModule + fabrique sortie de la classe"
 [r16_layer_bugs]="R16 couche 15/05: dataclass Homeostasis, shell/JS collé (dialogue), alias grandnexus.dialogue, openai protégé"
 [r18_orchestrator_state]="R18 orchestrateur: état PERCEPTION référencé mais absent de l'énumération"
 [r17_resource_history]="R17 ResourceManager.get_usage_history (demandé par l'orchestrateur)"
)
for r in r15_orchestrator_imports r16_layer_bugs r17_resource_history r18_orchestrator_state; do
  python3 repairs.py "$r"
  (cd .. && git add -A && git commit -qm "${MSG[$r]}")
done
