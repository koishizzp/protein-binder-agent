from agent.memory import AgentMemory


def test_memory_roundtrip(tmp_path):
    m = AgentMemory(max_messages=2)
    m.add_user_message("u1")
    m.add_assistant_message("a1")
    m.add_user_message("u2")
    assert len(m.get_messages()) == 2
    out = tmp_path / "memory.json"
    m.save(str(out))
    assert out.exists()
