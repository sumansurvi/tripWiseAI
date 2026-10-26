from tripwise_p8.memory import ConversationStore, rewrite_with_slots


def test_new_conversation_clears_slots():
    store = ConversationStore()
    a = store.get_or_create("c1")
    a.active_destination = "Delhi"
    b = store.get_or_create("c2")
    assert b.active_destination is None
    assert a.conversation_id == "c1"


def test_rewrite_short_followup():
    store = ConversationStore()
    st = store.get_or_create("x")
    st.active_destination = "Jaipur"
    assert "Jaipur" in rewrite_with_slots("which is cheaper?", st)
