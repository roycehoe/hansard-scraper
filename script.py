from database.init import create_db_and_tables, get_session
from populate.handsard_sitting_dates import populate_handsard_sitting_dates
from populate.mp_links import populate_mp_links
from populate.sitting_attendances import populate_sitting_attendances
from populate.sittings import populate_sittings

if __name__ == "__main__":
    create_db_and_tables()
    session = next(get_session())
    populate_handsard_sitting_dates(session)
    populate_sittings(session)
    populate_sitting_attendances(session)
    populate_mp_links(session)
