from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/mealengine"

    reddit_user_agent: str = "python:MealEngineV2:1.0 (by /u/mealengine_bot)"

    youtube_api_key: str = ""

    # Source scoring configuration
    source_quality_threshold: float = 0.6   # auto-promote candidates above this score
    source_score_window: int = 20            # number of recent recipes used to compute score
    source_score_decay: float = 0.9         # exponential decay weight per step back in time

    # Discovery configuration
    discovery_min_video_count: int = 5       # min recipe videos before a YouTube channel is a candidate
    discovery_min_subreddit_hits: int = 3    # min search results before a subreddit is a candidate

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
