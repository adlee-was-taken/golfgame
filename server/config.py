"""
Centralized configuration for Golf game server.

Configuration is loaded from (in order of precedence):
1. Environment variables
2. .env file (if exists)
3. Default values

Usage:
    from config import config
    print(config.PORT)
    print(config.card_values)
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use env vars only


def get_env(key: str, default: str = "") -> str:
    """Get environment variable with default."""
    return os.environ.get(key, default)


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    val = os.environ.get(key, "").lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def get_env_int(key: str, default: int = 0) -> int:
    """Get integer environment variable."""
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


@dataclass
class CardValues:
    """Card point values - the single source of truth."""
    ACE: int = 1
    TWO: int = -2
    THREE: int = 3
    FOUR: int = 4
    FIVE: int = 5
    SIX: int = 6
    SEVEN: int = 7
    EIGHT: int = 8
    NINE: int = 9
    TEN: int = 10
    JACK: int = 10
    QUEEN: int = 10
    KING: int = 0
    JOKER: int = -2

    # House rule modifiers
    SUPER_KINGS: int = -2       # King value when super_kings enabled
    TEN_PENNY: int = 1          # 10 value when ten_penny enabled
    LUCKY_SWING_JOKER: int = -5 # Joker value when lucky_swing enabled

    def to_dict(self) -> dict[str, int]:
        """Get card values as dictionary for game use."""
        return {
            'A': self.ACE,
            '2': self.TWO,
            '3': self.THREE,
            '4': self.FOUR,
            '5': self.FIVE,
            '6': self.SIX,
            '7': self.SEVEN,
            '8': self.EIGHT,
            '9': self.NINE,
            '10': self.TEN,
            'J': self.JACK,
            'Q': self.QUEEN,
            'K': self.KING,
            '★': self.JOKER,
        }


@dataclass
class GameDefaults:
    """Default game settings."""
    rounds: int = 9
    initial_flips: int = 2
    use_jokers: bool = False
    flip_mode: str = "never"  # "never", "always", or "endgame"


@dataclass
class ServerConfig:
    """Server configuration."""
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite:///games.db"

    # Room settings
    MAX_PLAYERS_PER_ROOM: int = 6
    ROOM_TIMEOUT_MINUTES: int = 60
    ROOM_CODE_LENGTH: int = 4

    # Security (for future auth system)
    SECRET_KEY: str = ""
    INVITE_ONLY: bool = False
    ADMIN_EMAILS: list[str] = field(default_factory=list)

    # Card values
    card_values: CardValues = field(default_factory=CardValues)

    # Game defaults
    game_defaults: GameDefaults = field(default_factory=GameDefaults)

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load configuration from environment variables."""
        admin_emails_str = get_env("ADMIN_EMAILS", "")
        admin_emails = [e.strip() for e in admin_emails_str.split(",") if e.strip()]

        return cls(
            HOST=get_env("HOST", "0.0.0.0"),
            PORT=get_env_int("PORT", 8000),
            DEBUG=get_env_bool("DEBUG", False),
            LOG_LEVEL=get_env("LOG_LEVEL", "INFO"),
            DATABASE_URL=get_env("DATABASE_URL", "sqlite:///games.db"),
            MAX_PLAYERS_PER_ROOM=get_env_int("MAX_PLAYERS_PER_ROOM", 6),
            ROOM_TIMEOUT_MINUTES=get_env_int("ROOM_TIMEOUT_MINUTES", 60),
            ROOM_CODE_LENGTH=get_env_int("ROOM_CODE_LENGTH", 4),
            SECRET_KEY=get_env("SECRET_KEY", ""),
            INVITE_ONLY=get_env_bool("INVITE_ONLY", False),
            ADMIN_EMAILS=admin_emails,
            card_values=CardValues(
                ACE=get_env_int("CARD_ACE", 1),
                TWO=get_env_int("CARD_TWO", -2),
                KING=get_env_int("CARD_KING", 0),
                JOKER=get_env_int("CARD_JOKER", -2),
                SUPER_KINGS=get_env_int("CARD_SUPER_KINGS", -2),
                TEN_PENNY=get_env_int("CARD_TEN_PENNY", 1),
                LUCKY_SWING_JOKER=get_env_int("CARD_LUCKY_SWING_JOKER", -5),
            ),
            game_defaults=GameDefaults(
                rounds=get_env_int("DEFAULT_ROUNDS", 9),
                initial_flips=get_env_int("DEFAULT_INITIAL_FLIPS", 2),
                use_jokers=get_env_bool("DEFAULT_USE_JOKERS", False),
                flip_mode=get_env("DEFAULT_FLIP_MODE", "never"),
            ),
        )


# Global config instance - loaded once at module import
config = ServerConfig.from_env()


def reload_config() -> ServerConfig:
    """Reload configuration from environment (useful for testing)."""
    global config
    config = ServerConfig.from_env()
    return config
