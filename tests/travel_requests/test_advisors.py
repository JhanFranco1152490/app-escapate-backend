from app.travel_requests.services import advisors
from tests.factories import RoleFactory, UserAccountFactory


def test_advisors_are_active_people_who_can_manage_requests_sorted_by_name(
    session, advisor_role, administrator_role, operations_role
):
    zuleta = UserAccountFactory(role=advisor_role, first_name="Zoe", last_name="Zuleta")
    arias = UserAccountFactory(role=advisor_role, first_name="Ana", last_name="Arias")
    boss = UserAccountFactory(role=administrator_role, first_name="Beto", last_name="Bravo")
    UserAccountFactory(role=advisor_role, first_name="Ida", last_name="Inactiva", is_active=False)
    UserAccountFactory(role=operations_role, first_name="Oto", last_name="Operativo")
    UserAccountFactory(role=RoleFactory(), first_name="Sin", last_name="Rol")

    options = advisors.list_advisors(session)

    ids = [option.id for option in options]
    assert [arias.id, boss.id, zuleta.id] == [
        i for i in ids if i in {arias.id, boss.id, zuleta.id}
    ]
    assert all(option.is_active for option in options)
    assert {option.role_id for option in options} <= {advisor_role.id, administrator_role.id}


def test_an_eligible_advisor_is_active_and_can_manage_requests(
    session, advisor_role, operations_role
):
    advisor = UserAccountFactory(role=advisor_role)
    inactive = UserAccountFactory(role=advisor_role, is_active=False)
    viewer = UserAccountFactory(role=operations_role)

    assert advisors.is_eligible_advisor(session, advisor.id)
    assert not advisors.is_eligible_advisor(session, inactive.id)
    assert not advisors.is_eligible_advisor(session, viewer.id)
    assert not advisors.is_eligible_advisor(session, 999_999_999)
