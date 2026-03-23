from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/mealengine"

    reddit_user_agent: str = "python:MealEngineV2:1.0 (by /u/mealengine_bot)"

    youtube_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
