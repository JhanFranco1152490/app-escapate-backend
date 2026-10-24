import pytest

from app.accounts.errors import LastUserManager
from app.accounts.services.manager_guard import ensure_user_managers_remain
from tests.factories import UserAccountFactory


def test_one_of_two_managers_can_leave(session, administrator_role):
    leaving = UserAccountFactory(role=administrator_role)
    UserAccountFactory(role=administrator_role)

    ensure_user_managers_remain(session, leaving={leaving.id})


def test_the_last_managers_cannot_all_leave(session, administrator_role):
    first = UserAccountFactory(role=administrator_role)
    second = UserAccountFactory(role=administrator_role)

    with pytest.raises(LastUserManager):
        ensure_user_managers_remain(session, leaving={first.id, second.id})


def test_someone_who_is_not_a_manager_can_always_leave(session, administrator_role, advisor_role):
    UserAccountFactory(role=administrator_role)
    advisor = UserAccountFactory(role=advisor_role)

    ensure_user_managers_remain(session, leaving={advisor.id})


def test_an_inactive_manager_does_not_count(session, administrator_role):
    UserAccountFactory(role=administrator_role, is_active=False)
    only_active = UserAccountFactory(role=administrator_role)

    with pytest.raises(LastUserManager):
        ensure_user_managers_remain(session, leaving={only_active.id})
