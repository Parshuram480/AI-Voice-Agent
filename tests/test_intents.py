from app.intents import IntentRouter


def test_intent_greeting():
    router = IntentRouter()
    result = router.route("Hello there")
    assert result.intent == "greeting"


def test_intent_order_status():
    router = IntentRouter()
    result = router.route("Where is my order?")
    assert result.intent == "order_status"


def test_intent_delivery_date():
    router = IntentRouter()
    result = router.route("When will it arrive?")
    assert result.intent == "delivery_date"


def test_intent_repeat():
    router = IntentRouter()
    result = router.route("repeat that")
    assert result.intent == "repeat_response"


def test_intent_unsupported():
    router = IntentRouter()
    result = router.route("Tell me a joke")
    assert result.intent == "unsupported"
