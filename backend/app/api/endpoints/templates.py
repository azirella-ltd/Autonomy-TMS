"""
Template API Endpoints
Phase 6 Sprint 4: User Experience Enhancements

REST API endpoints for managing templates, tutorials, and user preferences.
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.template import TemplateCategory, TemplateIndustry, TemplateDifficulty
from app.schemas.template import (
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    TemplateListResponse,
    TemplateSearchRequest,
    TutorialProgressCreate,
    TutorialProgressUpdate,
    TutorialProgressResponse,
    UserPreferencesCreate,
    UserPreferencesUpdate,
    UserPreferencesResponse,
    QuickStartRequest,
    QuickStartResponse
)
from app.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


# Template Endpoints
# ============================================================================

@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    template_data: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new template"""
    service = TemplateService(db)
    template = service.create_template(template_data, current_user.id)
    return template


@router.get("", response_model=TemplateListResponse)
def list_templates(
    query: str = Query(None, description="Search query"),
    category: TemplateCategory = Query(None, description="Filter by category"),
    industry: TemplateIndustry = Query(None, description="Filter by industry"),
    difficulty: TemplateDifficulty = Query(None, description="Filter by difficulty"),
    tags: List[str] = Query(None, description="Filter by tags"),
    is_featured: bool = Query(None, description="Filter featured templates"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    sort_by: str = Query("usage_count", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: Session = Depends(get_db)
):
    """List templates with filtering and pagination"""
    service = TemplateService(db)

    search_request = TemplateSearchRequest(
        query=query,
        category=category,
        industry=industry,
        difficulty=difficulty,
        tags=tags,
        is_featured=is_featured,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order
    )

    templates, total = service.search_templates(search_request)
    total_pages = (total + page_size - 1) // page_size

    return TemplateListResponse(
        templates=templates,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/featured", response_model=List[TemplateResponse])
def get_featured_templates(
    limit: int = Query(10, ge=1, le=50, description="Number of templates to return"),
    db: Session = Depends(get_db)
):
    """Get featured templates"""
    service = TemplateService(db)
    templates = service.get_featured_templates(limit=limit)
    return templates


@router.get("/popular", response_model=List[TemplateResponse])
def get_popular_templates(
    category: TemplateCategory = Query(None, description="Filter by category"),
    limit: int = Query(10, ge=1, le=50, description="Number of templates to return"),
    db: Session = Depends(get_db)
):
    """Get popular templates by usage count"""
    service = TemplateService(db)
    templates = service.get_popular_templates(category=category, limit=limit)
    return templates


@router.get("/industry/{industry}", response_model=List[TemplateResponse])
def get_templates_by_industry(
    industry: TemplateIndustry,
    limit: int = Query(20, ge=1, le=100, description="Number of templates to return"),
    db: Session = Depends(get_db)
):
    """Get templates for a specific industry"""
    service = TemplateService(db)
    templates = service.get_templates_by_industry(industry, limit=limit)
    return templates


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: int,
    db: Session = Depends(get_db)
):
    """Get a template by ID"""
    service = TemplateService(db)
    template = service.get_template(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {template_id} not found"
        )
    return template


@router.get("/slug/{slug}", response_model=TemplateResponse)
def get_template_by_slug(
    slug: str,
    db: Session = Depends(get_db)
):
    """Get a template by slug"""
    service = TemplateService(db)
    template = service.get_template_by_slug(slug)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with slug '{slug}' not found"
        )
    return template


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: int,
    template_data: TemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a template"""
    service = TemplateService(db)
    template = service.update_template(template_id, template_data)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {template_id} not found"
        )
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a template (soft delete)"""
    service = TemplateService(db)
    success = service.delete_template(template_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {template_id} not found"
        )


@router.post("/{template_id}/use", status_code=status.HTTP_200_OK)
def use_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Increment template usage count"""
    service = TemplateService(db)
    success = service.increment_usage(template_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {template_id} not found"
        )
    return {"message": "Template usage incremented"}


# Quick Start Wizard
# ============================================================================

@router.post("/quick-start", response_model=QuickStartResponse)
def quick_start_wizard(
    request: QuickStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get template recommendations for quick start wizard"""
    service = TemplateService(db)

    try:
        recommended, alternatives = service.get_quick_start_recommendations(request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    # Build response with next steps
    next_steps = [
        "Review the recommended template configuration",
        f"Customize game settings for {request.num_scenario_users} scenario_users",
        "Invite scenario_users or assign AI agents",
        "Start your simulation"
    ]

    if request.use_monte_carlo:
        next_steps.insert(2, "Configure Monte Carlo simulation parameters")

    return QuickStartResponse(
        recommended_template=recommended,
        alternative_templates=alternatives,
        supply_chain_config_id=recommended.configuration.get("supply_chain_config_id"),
        configuration=recommended.configuration,
        next_steps=next_steps
    )


# Tutorial Progress Endpoints
# ============================================================================

@router.post("/tutorials/progress", response_model=TutorialProgressResponse, status_code=status.HTTP_201_CREATED)
def create_tutorial_progress(
    progress_data: TutorialProgressCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start or reset tutorial progress"""
    service = TemplateService(db)
    progress = service.create_tutorial_progress(current_user.id, progress_data)
    return progress


@router.get("/tutorials/progress/{tutorial_id}", response_model=TutorialProgressResponse)
def get_tutorial_progress(
    tutorial_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get tutorial progress for current user"""
    service = TemplateService(db)
    progress = service.get_tutorial_progress(current_user.id, tutorial_id)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tutorial progress for '{tutorial_id}' not found"
        )
    return progress


@router.put("/tutorials/progress/{tutorial_id}", response_model=TutorialProgressResponse)
def update_tutorial_progress(
    tutorial_id: str,
    progress_data: TutorialProgressUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update tutorial progress"""
    service = TemplateService(db)
    progress = service.update_tutorial_progress(current_user.id, tutorial_id, progress_data)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tutorial progress for '{tutorial_id}' not found"
        )
    return progress


@router.get("/tutorials/progress", response_model=List[TutorialProgressResponse])
def get_user_tutorial_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all tutorial progress for current user"""
    service = TemplateService(db)
    progress_list = service.get_user_tutorial_progress(current_user.id)
    return progress_list


# User Preferences Endpoints
# ============================================================================

@router.get("/preferences", response_model=UserPreferencesResponse)
def get_user_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user preferences"""
    service = TemplateService(db)
    preferences = service.get_or_create_user_preferences(current_user.id)
    return preferences


@router.put("/preferences", response_model=UserPreferencesResponse)
def update_user_preferences(
    preferences_data: UserPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update user preferences"""
    service = TemplateService(db)
    preferences = service.update_user_preferences(current_user.id, preferences_data)
    return preferences
