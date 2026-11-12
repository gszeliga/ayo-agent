"""The reply: the turn's texts joined, and the fallback."""

from ayo_copilot.conversation.reply import FALLBACK_REPLY, compose_reply


def test_joins_non_empty_texts_in_order() -> None:
    texts = ["  Perfecto, ya tengo los cuatro datos. ", None, "", "  \n", "¿Qué evidencia tienes?"]
    assert compose_reply(texts, capped=False) == (
        "Perfecto, ya tengo los cuatro datos.\n\n¿Qué evidencia tienes?"
    )


def test_capped_appends_the_fallback_after_earlier_texts() -> None:
    assert compose_reply(["Registro el dato."], capped=True) == (
        f"Registro el dato.\n\n{FALLBACK_REPLY}"
    )
    assert compose_reply([None], capped=True) == FALLBACK_REPLY


def test_an_empty_reply_becomes_the_fallback() -> None:
    assert compose_reply([], capped=False) == FALLBACK_REPLY
    assert compose_reply([None, " "], capped=False) == FALLBACK_REPLY
