"""
Set dummy env vars before any app modules are imported during testing.
Unit tests use mocked API clients, so real credentials are not needed.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDDIT_CLIENT_ID", "test")
os.environ.setdefault("REDDIT_CLIENT_SECRET", "test")
os.environ.setdefault("YOUTUBE_API_KEY", "test")
