from database.init import create_db_and_tables, get_session
from populate.handsard_responses import populate_handsard_responses
from populate.reports import populate_reports
from populate.sitting_dates import populate_sitting_dates
from populate.sittings import populate_sittings
from populate.speeches import populate_speeches
from populate.statistics import export_statistics_csv, populate_statistics

if __name__ == "__main__":
    create_db_and_tables()
    session = next(get_session())
    populate_handsard_responses(session)
    populate_reports(session)
    populate_statistics(session)
    export_statistics_csv(session)
    populate_speeches(session)
    populate_sitting_dates(session)
    populate_sittings(session)
