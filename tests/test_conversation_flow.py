import pytest

from app.intents import IntentRouter, SlotFiller
from app.services.conversation_service import ConversationService
from app.services.order_service import OrderService
from app.services.verification_service import VerificationService
from app.session import SessionManager, InMemorySessionStore
from app.state_machine import ConversationStateMachine


class FakeCustomerRepo:
    def __init__(self, customer=None):
        self.customer = customer

    async def get_by_name_dob(self, name: str, dob: str):
        if not self.customer:
            return None
        if name.lower() == self.customer["full_name"].lower() and dob == self.customer["date_of_birth"]:
            return self.customer
        return None

    async def soft_delete(self, customer_id: int) -> bool:
        return False


class FakeOrderRepo:
    def __init__(self, orders=None):
        self.orders = orders or []

    async def get_all_for_customer(self, customer_id: int):
        return self.orders

    async def get_latest_for_customer(self, customer_id: int):
        return self.orders[0] if self.orders else None

    async def soft_delete(self, order_id: int) -> bool:
        return False


def build_service(customer=None, orders=None):
    session_manager = SessionManager(InMemorySessionStore())
    intent_router = IntentRouter()
    slot_filler = SlotFiller()
    state_machine = ConversationStateMachine()
    verification = VerificationService(FakeCustomerRepo(customer))
    order_service = OrderService(FakeOrderRepo(orders))
    return ConversationService(
        session_manager=session_manager,
        intent_router=intent_router,
        slot_filler=slot_filler,
        state_machine=state_machine,
        verification_service=verification,
        order_service=order_service,
    )


@pytest.mark.anyio
async def test_greeting_only():
    service = build_service()
    result = await service.handle_user_text("sess-1", "Hi")
    assert "help" in result.reply_text.lower()
    assert result.state == "WAITING_FOR_INTENT"


@pytest.mark.anyio
async def test_direct_name_and_dob_order_status():
    customer = {"id": 1, "full_name": "Parshuram Singh", "date_of_birth": "1990-05-15"}
    orders = [
        {
            "order_number": "ORD-100",
            "status": "Shipped",
            "estimated_arrival": "2026-05-27",
        }
    ]
    service = build_service(customer=customer, orders=orders)
    text = "My name is Parshuram Singh and DOB is 1990-05-15. I want my order status."
    result = await service.handle_user_text("sess-2", text)
    assert "order" in result.reply_text.lower()
    assert "2026-05-27" in result.reply_text
    assert result.state == "FOLLOWUP"


@pytest.mark.anyio
async def test_name_only_then_dob():
    customer = {"id": 1, "full_name": "John Smith", "date_of_birth": "1990-05-15"}
    orders = [{"order_number": "ORD-101", "status": "Processing", "estimated_arrival": "2026-05-28"}]
    service = build_service(customer=customer, orders=orders)

    step1 = await service.handle_user_text("sess-3", "I want to know my order status.")
    assert "full name" in step1.reply_text.lower()

    step2 = await service.handle_user_text("sess-3", "John Smith")
    assert "date of birth" in step2.reply_text.lower()


@pytest.mark.anyio
async def test_dob_only_then_name():
    customer = {"id": 2, "full_name": "Jane Doe", "date_of_birth": "1985-11-20"}
    orders = [{"order_number": "ORD-202", "status": "Delivered", "estimated_arrival": "2026-05-18"}]
    service = build_service(customer=customer, orders=orders)

    step1 = await service.handle_user_text("sess-4", "I want my order status.")
    assert "full name" in step1.reply_text.lower()

    step2 = await service.handle_user_text("sess-4", "DOB is 1985-11-20")
    assert "full name" in step2.reply_text.lower()

    step3 = await service.handle_user_text("sess-4", "My name is Jane Doe")
    assert "order" in step3.reply_text.lower()


@pytest.mark.anyio
async def test_malformed_dob():
    service = build_service()
    await service.handle_user_text("sess-5", "I want my order status.")
    step2 = await service.handle_user_text("sess-5", "My name is John Smith and DOB is 1990-99-99")
    assert "doesn't look valid" in step2.reply_text.lower()


@pytest.mark.anyio
async def test_unsupported_query():
    service = build_service()
    result = await service.handle_user_text("sess-6", "Tell me a joke.")
    assert "not able to help" in result.reply_text.lower()


@pytest.mark.anyio
async def test_follow_up_delivery_date():
    customer = {"id": 3, "full_name": "Alice Johnson", "date_of_birth": "1992-03-08"}
    orders = [
        {
            "order_number": "ORD-303",
            "status": "In Transit",
            "estimated_arrival": "2026-05-24",
        }
    ]
    service = build_service(customer=customer, orders=orders)
    first = await service.handle_user_text(
        "sess-7",
        "My name is Alice Johnson and DOB is 1992-03-08. I want my order status.",
    )
    assert "anything else" in first.reply_text.lower()

    follow = await service.handle_user_text("sess-7", "When will it arrive?")
    assert "2026-05-24" in follow.reply_text


@pytest.mark.anyio
async def test_repeat_response():
    service = build_service()
    first = await service.handle_user_text("sess-8", "Hi")
    repeat = await service.handle_user_text("sess-8", "repeat that")
    assert first.reply_text in repeat.reply_text


@pytest.mark.anyio
async def test_failed_verification():
    service = build_service(customer=None, orders=[])
    result = await service.handle_user_text(
        "sess-9",
        "My name is Missing User and DOB is 1990-05-15. I want my order status.",
    )
    assert "couldn't verify" in result.reply_text.lower()


@pytest.mark.anyio
async def test_empty_input():
    service = build_service()
    result = await service.handle_user_text("sess-10", "")
    assert "didn't catch" in result.reply_text.lower()
