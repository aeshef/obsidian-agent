from shared.telegram.navigation import is_host_navigation
from shared.telegram.host.keyboards import BACK_HOME


def test_host_navigation_rejects_main_menu_button():
    assert is_host_navigation(BACK_HOME)
    assert not is_host_navigation("347 вендомат")
