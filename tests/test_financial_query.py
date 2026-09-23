from core.financial_query import answer_financial_question


def test_returns_only_existing_deterministic_settlement_value_and_citations():
    index = {"PAY1": {"tier": "STAGE_3", "data": {"status": "MATCH", "matched_records": {"gateway": "G1"},
             "bank_row_ids": ["B1"], "settlement": {"variance": 0.0}}}}
    answer = answer_financial_question("What is the variance for PAY1?", index)
    assert answer["value"] == 0.0
    assert answer["citations"][0]["source_row_id"] == "G1"


def test_does_not_invent_missing_settlement_fields():
    index = {"PAY1": {"tier": "TIER_1", "data": {"matched_records": {"gateway": "G1"}}}}
    answer = answer_financial_question("What is GST for PAY1?", index)
    assert answer["found"] is False
    assert answer["explanation"] == "I don’t have enough uploaded data to answer that."


def test_refuses_ungrounded_questions_without_uploaded_support():
    index = {"PAY7": {"tier": "TIER_1", "data": {"status": "MATCH", "matched_records": {"gateway": "G7"}}}}
    answer = answer_financial_question("What is the GST for PAY7?", index)
    assert answer["supported"] is True
    assert answer["found"] is False
    assert answer["explanation"] == "I don’t have enough uploaded data to answer that."
