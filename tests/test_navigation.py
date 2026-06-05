from shared.telegram.navigation import is_host_navigation
from shared.telegram.host import labels as L


def test_host_navigation_rejects_main_menu_button():
    assert is_host_navigation(L.back_home())
    assert not is_host_navigation("347 вендомат")
