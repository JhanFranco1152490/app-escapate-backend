from sqlalchemy import text

TABLE = "CREATE TEMP TABLE IF NOT EXISTS probe (id serial primary key) ON COMMIT PRESERVE ROWS"


def count_rows(session) -> int:
    return session.exec(text("SELECT count(*) FROM probe")).one()[0]


def test_commit_inside_a_test_is_rolled_back_first(session):
    session.exec(text(TABLE))
    session.exec(text("INSERT INTO probe DEFAULT VALUES"))
    session.commit()

    assert count_rows(session) == 1


def test_commit_inside_a_test_is_rolled_back_second(session):
    session.exec(text(TABLE))

    assert count_rows(session) == 0
