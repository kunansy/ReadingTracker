from tracker.cards import db


async def test_get_notes_with_cards():
    cards = await db.get_cards()
    notes_with_cards = await db.get_notes_with_cards()

    assert len(cards) >= len(notes_with_cards)

    expected = {
        card.note_id
        for card in cards
    }

    assert notes_with_cards == expected
