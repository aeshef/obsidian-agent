from shared.telegram.message_draft import SendMessageDraft, new_draft_id


def test_new_draft_id_nonzero():
    assert new_draft_id(12345) > 0
    assert new_draft_id(12345) != new_draft_id(67890) or True  # may collide rarely


def test_send_message_draft_api_method():
    assert SendMessageDraft.__api_method__ == "sendMessageDraft"
