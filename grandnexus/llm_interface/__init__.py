# llm_interface/__init__.py
"""
Language layer. The package exports stay the same (LLMEngine, LLMConfig, LLMRequest, LLMResponse, LLMProvider,
prompt_templates, response_parser), but they are loaded on first access (PEP 562) instead of at import time
(v7.3.0, logbook 65): llm_engine imports the 2025 memories and graph, and an eager import made the core
translator (translator_v5) drag them into every process that only needs the nexus_logic pathway.
"""
import importlib

_EXPORTS = {
    'LLMEngine': ('.llm_engine', 'LLMEngine'),
    'LLMConfig': ('.llm_engine', 'LLMConfig'),
    'LLMRequest': ('.llm_engine', 'LLMRequest'),
    'LLMResponse': ('.llm_engine', 'LLMResponse'),
    'LLMProvider': ('.llm_engine', 'LLMProvider'),
    'prompt_templates': ('.prompt_templates', None),
    'response_parser': ('.response_parser', None),
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attr = _EXPORTS[name]
    mod = importlib.import_module(module, __name__)
    value = mod if attr is None else getattr(mod, attr)
    globals()[name] = value          # cached: the next access is a plain attribute lookup
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
