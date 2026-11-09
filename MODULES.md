# GrandNexus — module status

Generated from `grandnexus/module_status.py` (v7.3.0, logbook 64-65). core: the demonstrated pathway, loaded by `boot(profile="minimal")`; supported: tested, used by the benches or kept for comparison; experimental: the 2025 ground, runs, not demonstrated; archive: superseded duplicates kept for history. A module moves up only with a measurement.

| Module | Tag | Why |
|---|---|---|
| `grandnexus` | core | package root (subsystem import aliases) |
| `grandnexus.boot` | core | assembly; profile='minimal' is the core, profile='full' adds the experimental ground |
| `grandnexus.cognition` | core | package of the cognitive modules |
| `grandnexus.cognition.contracts` | core | shared result types of the reasoning pathway |
| `grandnexus.cognition.perception` | core | package of the premise extractor |
| `grandnexus.cognition.perception.premise_extractor` | core | grammar pathway: text -> premises |
| `grandnexus.cognition.reasoning` | core | package of the text reasoner |
| `grandnexus.cognition.reasoning.text_reasoner` | core | pathways (grammar, JSON, nx) -> reference engine -> strict verdict |
| `grandnexus.core` | core | package of NexusCore |
| `grandnexus.core.errorRecoveryManager` | core | imported and started by NexusCore |
| `grandnexus.core.event_bus` | core | installed by NexusCore |
| `grandnexus.core.nexus_core` | core | NexusCore: the orchestrator (registers, starts, stops the modules) |
| `grandnexus.llm_interface` | core | package of the translators (lazy exports since v7.3.0) |
| `grandnexus.llm_interface.translator_v5` | core | Claude as anchored translator into the nexus_logic language |
| `grandnexus.nexus_logic` | core | language spec and reference engine (package) |
| `grandnexus.nexus_logic.asp` | core | clingo export (differential check, 1,218/1,218) |
| `grandnexus.nexus_logic.bridge` | core | atoms of the grammar pathway -> nexus_logic program |
| `grandnexus.nexus_logic.core` | core | parser and reference engine (ref-2.3) |
| `grandnexus.cognition.deliberation` | supported | deliberation experiment (several readings), rejected (logbook 44), bench kept |
| `grandnexus.cognition.experience` | supported | experience memory of the learning loop; measured, no effect shown (logbook 62) |
| `grandnexus.cognition.reasoning.reasoning_core` | supported | home engine, kept for the comparison with the reference engine |
| `grandnexus.llm_interface.llm_engine` | supported | LLM engine used by the JSON translator |
| `grandnexus.llm_interface.llm_translator` | supported | earlier JSON translator (prompts v1-v4), kept for comparison |
| `grandnexus.llm_interface.prompt_templates` | supported | templates of the LLM engine |
| `grandnexus.llm_interface.response_parser` | supported | parsers of the LLM engine |
| `grandnexus.module_status` | supported | this file: the tags and their checks |
| `grandnexus.actuators` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.actuators.actuator_hub` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.actuators.drivers` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.actuators.drivers.virtual_gripper` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.clock` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.clock.cognitive_clock` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.adapters` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.cognition_manager` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning.continuous_learner` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning.curriculum` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning.intrinsic_motivation` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning.learning_core` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning.meta_learner` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning.reinforcement` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.learning.world_model_learner` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.manager_bridges` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition.adaptation` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition.affect_regulator` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition.confidence` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition.explainability_engine` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition.monitor` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition.reflection` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.metacognition.self_model` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.orchestration` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.orchestration.cognitive_orchestrator` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.perception.code_analyzer` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.perception.filters` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.perception.filters.attention_filter` | experimental | not loaded by any profile |
| `grandnexus.cognition.perception.filters.attention_filter_v2` | experimental | variant of attention_filter, not loaded by any profile |
| `grandnexus.cognition.perception.pattern_recognizer` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.perception.perception_core` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.perception.symbolic_parser` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.reasoning.hybrid_inference` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.reasoning.neural_reasoner` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.reasoning.planning` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.reasoning.symbolic_engine` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.reasoning.uncertainty` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.computation` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.computation.resource_manager` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.core.registry` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.distributed` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.distributed.federated_learning_coordinator` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.evolution` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.evolution.evolution_manager` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.graph` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.graph.graph_engine` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.graph.graph_module_manager` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.graph.graph_pattern_interface` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.graph.graph_sync_service` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.graph.pattern_mining` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.homeostasis` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.homeostasis.homeostasis_manager` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.io` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.io.dialogue_interface` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.io.external_connector_hub` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.kernel` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.kernel.kernel_bridge` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.memory` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.memory.episodic` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.memory.memory_manager` | experimental | not loaded by any profile |
| `grandnexus.memory.semantic` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.memory.semantic_v2` | experimental | variant of semantic, not loaded by any profile |
| `grandnexus.memory.working` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.memory.working_v2` | experimental | variant of working, not loaded by any profile |
| `grandnexus.multiagent` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.multiagent.multi_agent_coordinator` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.ops` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.ops.cost_optimizer` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.ops.decision_history_archive` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.ops.devsecops_orchestrator` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.ops.metrics_exporter` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.planning` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.planning.executive_planner` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.security` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.security.safety_guard` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.sensors` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.sensors.drivers` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.sensors.drivers.gym_driver` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.sensors.sensor_hub` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.simulation` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.simulation.digital_twin_service` | experimental | 2025 ground: runs, not demonstrated |
| `grandnexus.cognition.orchestration.cognitive_orchestrator_v1` | archive | earlier version of cognitive_orchestrator |
| `grandnexus.computation.resource_manager_ml` | archive | duplicate of resource_manager |
| `grandnexus.graph.graph_engine_v1` | archive | duplicate of graph_engine (kept side by side, logbook: legacy notes) |
| `grandnexus.llm_interface.llm_engine_lite` | archive | duplicate of llm_engine (fallback and embeddings to graft, never wired) |
