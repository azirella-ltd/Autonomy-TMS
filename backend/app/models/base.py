from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy import Column, Integer

class CustomBase:
    # Generate __tablename__ automatically
    @declared_attr
    def __tablename__(cls):
        # Map model names to table names
        table_names = {
            'User': 'users',
            'Game': 'games',
            'Player': 'players',
            'Round': 'rounds',
            'PlayerAction': 'player_actions',
            'RefreshToken': 'refresh_tokens',
            'PasswordHistory': 'password_history',
            'PasswordResetToken': 'password_reset_tokens',
            'TokenBlacklist': 'token_blacklist',
            'UserSession': 'user_sessions'
        }
        return table_names.get(cls.__name__, cls.__name__.lower())

    # Common columns for all models
    id = Column(Integer, primary_key=True, index=True)

# Create the declarative base
Base = declarative_base(cls=CustomBase)

# Import all models to ensure they're registered with SQLAlchemy
# This must be done after Base is defined
from app.models.user import User, RefreshToken
from app.models.participant import ScenarioUser
from app.models.scenario import Scenario, Round, ScenarioUserAction
from app.models.auth_models import PasswordHistory, PasswordResetToken
from app.models.session import TokenBlacklist, UserSession

# Import the association table to ensure it's registered
# Note: user_games renamed to user_scenarios in Feb 2026 refactoring
from app.models.user import user_scenarios



