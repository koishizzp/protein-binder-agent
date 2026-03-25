from protein_agent.agent.memory import AgentMemory


def test_memory_roundtrip(tmp_path):
    memory = AgentMemory(max_messages=2)
    memory.add_user_message("u1")
    memory.add_assistant_message("a1")
    memory.add_user_message("u2")
    assert len(memory.get_messages()) == 2
    output_path = tmp_path / "memory.json"
    memory.save(str(output_path))
    assert output_path.exists()
