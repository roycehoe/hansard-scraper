from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql://user:password@localhost:5432/postgres"

    handsard_search_url: str = "https://sprs.parl.gov.sg/search/searchResult"
    handsard_topic_url: str = "https://sprs.parl.gov.sg/search/getHansardTopic"
    handsard_report_url: str = "https://sprs.parl.gov.sg/search/getHansardReport/"

    search_page_size: int = 20

    search_from_day: str = "24"
    search_from_month: str = "08"
    search_from_year: str = "2025"
    search_to_day: str = "24"
    search_to_month: str = "08"
    search_to_year: str = "2025"


settings = AppSettings()
