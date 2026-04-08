from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/mealengine"

    reddit_user_agent: str = "python:MealEngineV2:1.0 (by /u/mealengine_bot)"

    youtube_api_key: str = ""

    anthropic_api_key: str = ""

    # Source scoring configuration
    source_quality_threshold: float = 0.75  # auto-promote candidates above this score
    source_promotion_min_content: int = 2   # min recipes seen before a candidate can be promoted
    source_score_window: int = 20            # number of recent recipes used to compute score
    source_score_decay: float = 0.9         # exponential decay weight per step back in time

    # Discovery configuration
    discovery_min_video_count: int = 5       # min recipe videos before a YouTube channel is a candidate
    discovery_min_subreddit_hits: int = 3    # min search results before a subreddit is a candidate

    # Email delivery (Resend)
    resend_api_key: str = ""
    email_from: str = "plans@mealengine.ca"

    # Gumroad
    gumroad_access_token: str = ""
    gumroad_product_little_ones: str = ""   # product ID from Gumroad listing URL
    gumroad_product_teen_table: str = ""    # product ID from Gumroad listing URL

    # Supabase Storage
    supabase_url: str = ""
    supabase_service_key: str = ""          # service_role key (not anon key)
    supabase_storage_bucket: str = "meal-plans"

    # Internal cron secret — set this in Railway, pass in X-Cron-Secret header
    cron_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
