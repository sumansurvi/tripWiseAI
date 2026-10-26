from tripwise_p6.router import route_query


def test_personal_info_short_circuit():
    r = route_query("What is my passport number?")
    assert r.intent == "personal_info"
    assert r.refuse_reason == "personal_information"
    assert not r.should_retrieve()


def test_practical_currency_routes_to_india():
    r = route_query("What currency in India?")
    assert r.intent == "practical"
    assert "India" in r.title_filters


def test_food_intent_and_delhi_expand():
    r = route_query("What to eat in Delhi?")
    assert r.intent == "food"
    assert any("Delhi" in t for t in r.title_filters)


def test_comparison_intent():
    r = route_query("Delhi vs Mumbai for food")
    assert r.intent == "comparison"
    assert "Delhi" in r.entities and "Mumbai" in r.entities


def test_follow_up_uses_active_destination():
    r = route_query("which is cheaper?", active_destination="Jaipur")
    assert r.intent == "follow_up"
    assert "Jaipur" in r.rewritten_query
