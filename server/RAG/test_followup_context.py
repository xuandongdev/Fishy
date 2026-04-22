from services.legal_query_context import build_effective_legal_question


def _assert_contains(text: str, expected: str) -> None:
    if expected not in text:
        raise AssertionError(f"Expected '{expected}' in '{text}'")


def run_tests() -> None:
    case1_history = [
        {"role": "user", "content": "xe may vuot den do bi phat bao nhieu"},
        {"role": "assistant", "content": "Xe máy vượt đèn đỏ bị phạt từ 4.000.000 đồng đến 6.000.000 đồng."},
    ]
    case1 = build_effective_legal_question("vay con chay qua 12km", case1_history)
    assert case1["effective_question"] == "vay con chay qua 12km"
    assert case1["vehicle_type"] == "xe_may"
    assert case1["query_km"] == 12.0
    assert case1["action"] == "qua_toc_do"

    case2_history = [
        {"role": "user", "content": "o to chay qua toc do 22km/h phat sao"},
        {"role": "assistant", "content": "Ô tô chạy quá tốc độ 22 km/h sẽ bị xử phạt theo nghị định."},
    ]
    case2 = build_effective_legal_question("neu la 27km thi sao", case2_history)
    assert case2["effective_question"] == "neu la 27km thi sao"
    assert case2["vehicle_type"] == "o_to"
    assert case2["query_km"] == 27.0
    assert case2["action"] == "qua_toc_do"

    case3_history = [
        {"role": "user", "content": "nguoi di bo vi pham bi phat the nao"},
        {"role": "assistant", "content": "Người đi bộ vi phạm sẽ bị xử phạt tùy hành vi."},
    ]
    case3 = build_effective_legal_question("con truong hop vuot den do", case3_history)
    assert case3["effective_question"] == "con truong hop vuot den do"
    assert case3["vehicle_type"] == "di_bo"
    assert case3["action"] == "vuot_den_do"

    case4 = build_effective_legal_question("xe may vuot den do bi phat bao nhieu", [])
    assert case4["effective_question"] == "xe may vuot den do bi phat bao nhieu"

    case5_history = [
        {"role": "user", "content": "xe o to vuot den do bi phat bao nhieu"},
        {"role": "assistant", "content": "Xe o to vuot den do bi phat tu 18.000.000 dong den 20.000.000 dong."},
    ]
    case5 = build_effective_legal_question("con xe may thi sao", case5_history)
    _assert_contains(str(case5["effective_question"]).lower(), "xe may")
    _assert_contains(str(case5["effective_question"]).lower(), "vuot den do")
    assert case5["vehicle_type"] == "xe_may"
    assert case5["action"] == "vuot_den_do"

    print("All follow-up tests passed.")


if __name__ == "__main__":
    run_tests()
