from database.init import create_db_and_tables, get_session
from populate.attendances import populate_attendances
from populate.hansard_sitting_dates import populate_hansard_sitting_dates
from populate.sittings import populate_sittings
from populate.speaker_links import populate_speaker_links

if __name__ == "__main__":
    create_db_and_tables()
    session = next(get_session())
    populate_hansard_sitting_dates(session)
    populate_sittings(session)
    populate_attendances(session)
    populate_speaker_links(session)
