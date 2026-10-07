from fastapi import Response

from app.core.security.cookies import clear_session_cookies, set_session_cookies


def cookies_by_name(response: Response) -> dict[str, str]:
    headers = [value.decode() for name, value in response.raw_headers if name == b"set-cookie"]
    return {header.split("=", 1)[0]: header for header in headers}


def test_session_cookies_have_their_own_paths_and_lifetimes():
    response = Response()

    set_session_cookies(response, "access-token", "refresh-token")

    cookies = cookies_by_name(response)
    access, refresh = cookies["escapate_access"], cookies["escapate_refresh"]
    assert "access-token" in access and "Path=/api/" in access and "Max-Age=900" in access
    assert "refresh-token" in refresh and "Path=/api/auth/" in refresh
    assert "Max-Age=604800" in refresh
    assert all("HttpOnly" in cookie for cookie in cookies.values())


def test_clearing_uses_the_same_paths_so_the_browser_deletes_them():
    response = Response()

    clear_session_cookies(response)

    cookies = cookies_by_name(response)
    assert "Path=/api/" in cookies["escapate_access"]
    assert "Path=/api/auth/" in cookies["escapate_refresh"]
    assert all("Max-Age=0" in cookie for cookie in cookies.values())
