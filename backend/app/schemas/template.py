"""
Template Schemas
Phase 6 Sprint 4: User Experience Enhancements

Pydantic schemas for template data validation and serialization.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator

from app.models.template import TemplateCategory, TemplateIndustry, TemplateDifficulty


# Template Schemas
# ============================================================================

class TemplateBase(BaseModel):
    """Base template schema"""
    name: str = Field(..., min_length=1, max_length=255)
    category: TemplateCategory
    industry: TemplateIndustry = TemplateIndustry.GENERAL
    difficulty: TemplateDifficulty = TemplateDifficulty.BEGINNER
    description: str = Field(..., min_length=10)
    short_description: Optional[str] = Field(None, max_length=500)
    configuration: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    tags: List[str] = Field(default_factory=list)
    is_featured: bool = False
    is_active: bool = True


class TemplateCreate(TemplateBase):
    """Schema for creating a template"""
    pass

    @validator('configuration')
    def validate_configuration(cls, v, values):
        """Validate configuration based on category"""
        category = values.get('category')

        if category == TemplateCategory.DISTRIBUTION:
            # Must have distribution_type and parameters
            if 'distribution_type' not in v:
                raise ValueError('Distribution templates must have distribution_type')
            if 'parameters' not in v:
                raise ValueError('Distribution templates must have parameters')

        elif category == TemplateCategory.SCENARIO:
            # Must have scenario configuration
            if 'supply_chain_config_id' not in v and 'supply_chain_config' not in v:
                raise ValueError('Scenario templates must reference a supply chain config')

        return v


class TemplateUpdate(BaseModel):
    """Schema for updating a template"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[TemplateCategory] = None
    industry: Optional[TemplateIndustry] = None
    difficulty: Optional[TemplateDifficulty] = None
    description: Optional[str] = Field(None, min_length=10)
    short_description: Optional[str] = Field(None, max_length=500)
    configuration: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=20)
    tags: Optional[List[str]] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None


class TemplateResponse(TemplateBase):
    """Schema for template response"""
    id: int
    slug: str
    usage_count: int
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    """Schema for paginated template list"""
    templates: List[TemplateResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# Tutorial Progress Schemas
# ============================================================================

class TutorialProgressBase(BaseModel):
    """Base tutorial progress schema"""
    tutorial_id: str = Field(..., min_length=1, max_length=100)
    current_step: int = Field(default=0, ge=0)
    total_steps: int = Field(..., gt=0)
    state: Dict[str, Any] = Field(default_factory=dict)


class TutorialProgressCreate(TutorialProgressBase):
    """Schema for creating tutorial progress"""
    pass


class TutorialProgressUpdate(BaseModel):
    """Schema for updating tutorial progress"""
    current_step: Optional[int] = Field(None, ge=0)
    completed: Optional[bool] = None
    state: Optional[Dict[str, Any]] = None


class TutorialProgressResponse(TutorialProgressBase):
    """Schema for tutorial progress response"""
    id: int
    user_id: int
    completed: bool
    started_at: datetime
    completed_at: Optional[datetime]
    last_accessed: datetime

    class Config:
        from_attributes = True


# User Preferences Schemas
# ============================================================================

class UserPreferencesBase(BaseModel):
    """Base user preferences schema"""
    theme: str = Field(default="light", pattern="^(light|dark|auto)$")
    show_tutorials: bool = True
    show_tips: bool = True
    onboarding_completed: bool = False
    quick_start_shown: bool = False
    preferences: Dict[str, Any] = Field(default_factory=dict)


class UserPreferencesCreate(UserPreferencesBase):
    """Schema for creating user preferences"""
    pass


class UserPreferencesUpdate(BaseModel):
    """Schema for updating user preferences"""
    theme: Optional[str] = Field(None, pattern="^(light|dark|auto)$")
    show_tutorials: Optional[bool] = None
    show_tips: Optional[bool] = None
    onboarding_completed: Optional[bool] = None
    quick_start_shown: Optional[bool] = None
    preferences: Optional[Dict[str, Any]] = None


class UserPreferencesResponse(UserPreferencesBase):
    """Schema for user preferences response"""
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Quick Start Wizard Schemas
# ============================================================================

class QuickStartRequest(BaseModel):
    """Schema for quick start wizard request"""
    industry: TemplateIndustry = TemplateIndustry.GENERAL
    difficulty: TemplateDifficulty = TemplateDifficulty.BEGINNER
    features: List[str] = Field(default_factory=list)  # Desired features
    use_monte_carlo: bool = False
    num_scenario_users: int = Field(default=4, ge=1, le=10)


class QuickStartResponse(BaseModel):
    """Schema for quick start wizard response"""
    recommended_template: TemplateResponse
    alternative_templates: List[TemplateResponse]
    supply_chain_config_id: Optional[int]
    configuration: Dict[str, Any]
    next_steps: List[str]


# Template Search Schemas
# ============================================================================

class TemplateSearchRequest(BaseModel):
    """Schema for template search request"""
    query: Optional[str] = Field(None, max_length=255)
    category: Optional[TemplateCategory] = None
    industry: Optional[TemplateIndustry] = None
    difficulty: Optional[TemplateDifficulty] = None
    tags: Optional[List[str]] = None
    is_featured: Optional[bool] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str = Field(default="usage_count", pattern="^(usage_count|created_at|name)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
