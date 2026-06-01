from shared.finance.entity_names import find_matching_label, labels_equal


def test_labels_equal_normalized():
    assert labels_equal("Т Банк", "тбанк")
    assert not labels_equal("Сбер", "Тинькофф")


def test_find_matching_label():
    assert find_matching_label("тбанк", ["Тинькофф", "Сбербанк"]) is None
    assert find_matching_label("Сбербанк", ["Тинькофф", "Сбербанк"]) == "Сбербанк"
