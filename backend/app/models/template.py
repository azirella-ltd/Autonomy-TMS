"""
Template Models
Phase 6 Sprint 4: User Experience Enhancements

Database models for game templates, distribution templates, and scenario templates.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class TemplateCategory(str, enum.Enum):
    """Template category enumeration"""
    DISTRIBUTION = "distribution"
    SCENARIO = "scenario"
    GAME = "game"
    SUPPLY_CHAIN = "supply_chain"


class TemplateIndustry(str, enum.Enum):
    """Industry vertical for templates"""
    GENERAL = "general"
    RETAIL = "retail"
    MANUFACTURING = "manufacturing"
    LOGISTICS = "logistics"
    HEALTHCARE = "healthcare"
    TECHNOLOGY = "technology"
    FOOD_BEVERAGE = "food_beverage"
    AUTOMOTIVE = "automotive"


class TemplateDifficulty(str, enum.Enum):
    """Template difficulty level"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class Template(Base):
    """
    Template model for reusable configurations.

    Supports:
    - Distribution templates (demand patterns, stochastic configs)
    - Scenario templates (complete game setups)
    - Supply chain templates (network topologies)
    """
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)

    # Categorization
    category = Column(Enum(TemplateCategory, name="template_category"), nullable=False, index=True)
    industry = Column(Enum(TemplateIndustry, name="template_industry"), default=TemplateIndustry.GENERAL, index=True)
    difficulty = Column(Enum(TemplateDifficulty, name="templatedifficulty"), default=TemplateDifficulty.BEGINNER)

    # Content
    description = Column(Text, nullable=False)
    short_description = Column(String(500))
    configuration = Column(JSON, nullable=False)  # Template-specific config
    template_metadata = Column(JSON, default={})  # Additional metadata

    # Display
    icon = Column(String(50))  # Material-UI icon name
    color = Column(String(20))  # Hex color code
    tags = Column(JSON, default=[])  # List of tag strings

    # Usage tracking
    usage_count = Column(Integer, default=0)
    is_featured = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Authorship
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    creator = relationship("User", foreign_keys=[created_by], backref="templates")

    def __repr__(self):
        return f"<Template {self.name} ({self.category})>"


class TutorialProgress(Base):
    """
    Track user progress through tutorials.
    """
    __tablename__ = "tutorial_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tutorial_id = Column(String(100), nullable=False, index=True)

    # Progress tracking
    completed = Column(Boolean, default=False)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, nullable=False)

    # State
    state = Column(JSON, default={})  # Tutorial-specific state

    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    last_accessed = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    user = relationship("User", backref="tutorial_progress")

    def __repr__(self):
        return f"<TutorialProgress user={self.user_id} tutorial={self.tutorial_id}>"


class UserPreferences(Base):
    """
    Store user preferences and settings.
    """
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    # UI Preferences
    theme = Column(String(20), default="light")  # light, dark, auto
    show_tutorials = Column(Boolean, default=True)
    show_tips = Column(Boolean, default=True)

    # Onboarding
    onboarding_completed = Column(Boolean, default=False)
    quick_start_shown = Column(Boolean, default=False)

    # Preferences
    preferences = Column(JSON, default={})  # Flexible preferences storage

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    user = relationship("User", backref="preferences")

    def __repr__(self):
        return f"<UserPreferences user={self.user_id}>"
