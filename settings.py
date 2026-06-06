from datetime import date, datetime

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql://user:password@localhost:5432/postgres"

    sitting_date_format_change: datetime = datetime(2015, 8, 18)

    parliament_speakers_url: str = "https://www.parliament.gov.sg/history/list-of-mps-by-parliament"
    parliament_anticsrf_url: str = "https://www.parliament.gov.sg/sitefinity/anticsrf"

    handsard_search_url: str = "https://sprs.parl.gov.sg/search/searchResult"
    handsard_topic_url: str = "https://sprs.parl.gov.sg/search/getHansardTopic"
    handsard_report_url: str = "https://sprs.parl.gov.sg/search/getHansardReport/"

    search_page_size: int = 20

    search_from_date: date = date(2025, 8, 24)
    search_to_date: date = date(2025, 8, 24)


settings = AppSettings()
