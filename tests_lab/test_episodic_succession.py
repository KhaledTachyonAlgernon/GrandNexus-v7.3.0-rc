"""Offline test of the v7.4.x repairs (logbook 77): the episodic memory retrieves by the question's words and knows
succession for a single-valued relation; the grammar pathway reads a two-word role in a question."""
import sys, logging
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
from grandnexus.memory.episodic import EpisodicMemory, EpisodicMemoryConfig
from grandnexus.cognition.reasoning.text_reasoner import TextReasoner

tr = TextReasoner()
assert tr.answer("Bob is a chess player. Is Bob a chess player?", mode="grammar")["answer"] == "yes"
assert tr.answer("Bob is a painter. Is Bob a painter?", mode="grammar")["answer"] == "yes"
assert tr.answer("Every chess player is calm. Bob is a chess player. Is Bob calm?", mode="grammar")["answer"] == "yes"

LIVES = {"lives in": "{subject} does not live in {value}."}
def lives(p, c):
    return {"subject": p, "relation": "lives in", "value": c}

em = EpisodicMemory(EpisodicMemoryConfig(single_valued_relations=LIVES))
e = em.create_episode("session").episode_id
for f in ["Tom is a painter.", "Bob is a chess player.", "Every chess player is patient.", "Nina is a baker."]:
    em.add_event(e, f)
em.add_event(e, "Alice lives in Lyon.", metadata=lives("Alice", "Lyon"))
em.close_episode(e)
def ctx(q, k=3):
    return [x.content for x in em.retrieve_events(text=q, max_results=k)]
assert set(ctx("Is Bob patient?", 2)) == {"Bob is a chess player.", "Every chess player is patient."}, ctx("Is Bob patient?", 2)
e2 = em.create_episode("session").episode_id
em.add_event(e2, "Alice lives in Paris.", metadata=lives("Alice", "Paris"))
assert "Alice lives in Lyon." not in ctx("Does Alice live in Lyon?", 10), "the superseded fact is left out"
assert "Alice does not live in Lyon." in ctx("Does Alice live in Lyon?")
assert any(x.content == "Alice lives in Lyon." for x in em.retrieve_events(text="Alice", include_superseded=True, max_results=10))
for q, a in [("Does Alice live in Lyon?", "no"), ("Does Alice live in Paris?", "yes")]:
    assert tr.answer(" ".join(ctx(q) + [q]), mode="grammar")["answer"] == a, q
em.add_event(e2, "Alice lives in Lyon.", metadata=lives("Alice", "Lyon"))           # back to Lyon
c = ctx("Does Alice live in Lyon?", 10)
assert "Alice does not live in Lyon." not in c and "Alice does not live in Paris." in c, c
assert tr.answer(" ".join(ctx("Does Alice live in Lyon?") + ["Does Alice live in Lyon?"]), mode="grammar")["answer"] == "yes"

old = EpisodicMemory(EpisodicMemoryConfig(lexical_retrieval=False))                  # the 2025 behaviour stays available
e3 = old.create_episode("session").episode_id
for f in ["Tom is a painter.", "Bob is a chess player.", "Every chess player is patient."]:
    old.add_event(e3, f)
assert [x.content for x in old.retrieve_events(text="Is Bob patient?", max_results=1)] == ["Tom is a painter."]
print("ALL OK")
