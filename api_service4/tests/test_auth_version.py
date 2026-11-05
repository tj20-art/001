from api_service4.app.middleware.auth import _token_version_matches


def test_auth_version_accepts_current_and_legacy_version_zero_tokens():
    current_user = {"auth_version": 0}

    assert _token_version_matches({"auth_version": 0}, current_user)
    assert _token_version_matches({}, current_user)


def test_auth_version_rejects_tokens_after_security_reset():
    current_user = {"auth_version": 2}

    assert not _token_version_matches({"auth_version": 1}, current_user)
    assert not _token_version_matches({}, current_user)
    assert not _token_version_matches({"auth_version": "invalid"}, current_user)
