"""
Template Service
Phase 6 Sprint 4: User Experience Enhancements

Business logic for managing templates, tutorials, and user preferences.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc, asc
from slugify import slugify

from app.models.template import (
    Template,
    TutorialProgress,
    UserPreferences,
    TemplateCategory,
    TemplateIndustry,
    TemplateDifficulty
)
from app.schemas.template import (
    TemplateCreate,
    TemplateUpdate,
    TemplateSearchRequest,
    TutorialProgressCreate,
    TutorialProgressUpdate,
    UserPreferencesCreate,
    UserPreferencesUpdate,
    QuickStartRequest
)


class TemplateService:
    """Service for managing templates"""

    def __init__(self, db: Session):
        self.db = db

    # Template CRUD
    # ========================================================================

    def create_template(self, template_data: TemplateCreate, created_by: int) -> Template:
        """Create a new template"""
        # Generate slug from name
        slug = slugify(template_data.name)

        # Ensure slug is unique
        counter = 1
        original_slug = slug
        while self.db.query(Template).filter(Template.slug == slug).first():
            slug = f"{original_slug}-{counter}"
            counter += 1

        template = Template(
            **template_data.model_dump(),
            slug=slug,
            created_by=created_by
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def get_template(self, template_id: int) -> Optional[Template]:
        """Get template by ID"""
        return self.db.query(Template).filter(Template.id == template_id).first()

    def get_template_by_slug(self, slug: str) -> Optional[Template]:
        """Get template by slug"""
        return self.db.query(Template).filter(Template.slug == slug).first()

    def update_template(self, template_id: int, template_data: TemplateUpdate) -> Optional[Template]:
        """Update an existing template"""
        template = self.get_template(template_id)
        if not template:
            return None

        update_data = template_data.model_dump(exclude_unset=True)

        # If name is being updated, regenerate slug
        if 'name' in update_data:
            new_slug = slugify(update_data['name'])
            # Ensure slug is unique (excluding current template)
            counter = 1
            original_slug = new_slug
            while self.db.query(Template).filter(
                Template.slug == new_slug,
                Template.id != template_id
            ).first():
                new_slug = f"{original_slug}-{counter}"
                counter += 1
            update_data['slug'] = new_slug

        for key, value in update_data.items():
            setattr(template, key, value)

        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: int) -> bool:
        """Delete a template (soft delete by setting is_active=False)"""
        template = self.get_template(template_id)
        if not template:
            return False

        template.is_active = False
        self.db.commit()
        return True

    def increment_usage(self, template_id: int) -> bool:
        """Increment template usage count"""
        template = self.get_template(template_id)
        if not template:
            return False

        template.usage_count += 1
        self.db.commit()
        return True

    # Template Search & Filtering
    # ========================================================================

    def search_templates(self, search_request: TemplateSearchRequest) -> Tuple[List[Template], int]:
        """Search and filter templates with pagination"""
        query = self.db.query(Template).filter(Template.is_active == True)

        # Apply filters
        if search_request.query:
            search_term = f"%{search_request.query}%"
            query = query.filter(
                or_(
                    Template.name.ilike(search_term),
                    Template.description.ilike(search_term),
                    Template.short_description.ilike(search_term)
                )
            )

        if search_request.category:
            query = query.filter(Template.category == search_request.category)

        if search_request.industry:
            query = query.filter(Template.industry == search_request.industry)

        if search_request.difficulty:
            query = query.filter(Template.difficulty == search_request.difficulty)

        if search_request.tags:
            # Filter by tags (templates must have at least one matching tag)
            for tag in search_request.tags:
                query = query.filter(Template.tags.contains([tag]))

        if search_request.is_featured is not None:
            query = query.filter(Template.is_featured == search_request.is_featured)

        # Get total count before pagination
        total = query.count()

        # Apply sorting
        sort_column = getattr(Template, search_request.sort_by)
        if search_request.sort_order == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))

        # Apply pagination
        offset = (search_request.page - 1) * search_request.page_size
        templates = query.offset(offset).limit(search_request.page_size).all()

        return templates, total

    def get_featured_templates(self, limit: int = 10) -> List[Template]:
        """Get featured templates"""
        return self.db.query(Template).filter(
            Template.is_featured == True,
            Template.is_active == True
        ).order_by(desc(Template.usage_count)).limit(limit).all()

    def get_popular_templates(self, category: Optional[TemplateCategory] = None, limit: int = 10) -> List[Template]:
        """Get popular templates by usage count"""
        query = self.db.query(Template).filter(Template.is_active == True)

        if category:
            query = query.filter(Template.category == category)

        return query.order_by(desc(Template.usage_count)).limit(limit).all()

    def get_templates_by_industry(self, industry: TemplateIndustry, limit: int = 20) -> List[Template]:
        """Get templates for a specific industry"""
        return self.db.query(Template).filter(
            Template.industry == industry,
            Template.is_active == True
        ).order_by(desc(Template.usage_count)).limit(limit).all()

    # Quick Start Wizard
    # ========================================================================

    def get_quick_start_recommendations(self, request: QuickStartRequest) -> Tuple[Template, List[Template]]:
        """Get template recommendations for quick start wizard"""
        # Build query based on preferences
        query = self.db.query(Template).filter(
            Template.is_active == True,
            Template.category.in_([TemplateCategory.SCENARIO, TemplateCategory.GAME])
        )

        # Filter by industry
        if request.industry != TemplateIndustry.GENERAL:
            query = query.filter(Template.industry == request.industry)

        # Filter by difficulty
        query = query.filter(Template.difficulty == request.difficulty)

        # Sort by usage count (most popular first)
        query = query.order_by(desc(Template.usage_count))

        # Get top recommendations
        templates = query.limit(5).all()

        if not templates:
            # Fallback to general templates
            templates = self.db.query(Template).filter(
                Template.is_active == True,
                Template.category.in_([TemplateCategory.SCENARIO, TemplateCategory.GAME]),
                Template.industry == TemplateIndustry.GENERAL
            ).order_by(desc(Template.usage_count)).limit(5).all()

        if not templates:
            raise ValueError("No suitable templates found")

        # Return top recommendation and alternatives
        recommended = templates[0]
        alternatives = templates[1:] if len(templates) > 1 else []

        return recommended, alternatives

    # Tutorial Progress
    # ========================================================================

    def create_tutorial_progress(self, user_id: int, progress_data: TutorialProgressCreate) -> TutorialProgress:
        """Create or reset tutorial progress"""
        # Check if progress already exists
        existing = self.db.query(TutorialProgress).filter(
            TutorialProgress.user_id == user_id,
            TutorialProgress.tutorial_id == progress_data.tutorial_id
        ).first()

        if existing:
            # Reset existing progress
            existing.current_step = 0
            existing.completed = False
            existing.state = {}
            existing.started_at = datetime.utcnow()
            existing.completed_at = None
            existing.last_accessed = datetime.utcnow()
            self.db.commit()
            self.db.refresh(existing)
            return existing

        # Create new progress
        progress = TutorialProgress(
            user_id=user_id,
            **progress_data.model_dump()
        )
        self.db.add(progress)
        self.db.commit()
        self.db.refresh(progress)
        return progress

    def get_tutorial_progress(self, user_id: int, tutorial_id: str) -> Optional[TutorialProgress]:
        """Get tutorial progress for a user"""
        return self.db.query(TutorialProgress).filter(
            TutorialProgress.user_id == user_id,
            TutorialProgress.tutorial_id == tutorial_id
        ).first()

    def update_tutorial_progress(
        self,
        user_id: int,
        tutorial_id: str,
        progress_data: TutorialProgressUpdate
    ) -> Optional[TutorialProgress]:
        """Update tutorial progress"""
        progress = self.get_tutorial_progress(user_id, tutorial_id)
        if not progress:
            return None

        update_data = progress_data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(progress, key, value)

        # Mark as completed if specified
        if progress_data.completed and not progress.completed:
            progress.completed = True
            progress.completed_at = datetime.utcnow()

        progress.last_accessed = datetime.utcnow()

        self.db.commit()
        self.db.refresh(progress)
        return progress

    def get_user_tutorial_progress(self, user_id: int) -> List[TutorialProgress]:
        """Get all tutorial progress for a user"""
        return self.db.query(TutorialProgress).filter(
            TutorialProgress.user_id == user_id
        ).all()

    # User Preferences
    # ========================================================================

    def get_user_preferences(self, user_id: int) -> Optional[UserPreferences]:
        """Get user preferences"""
        return self.db.query(UserPreferences).filter(
            UserPreferences.user_id == user_id
        ).first()

    def create_user_preferences(self, user_id: int, preferences_data: UserPreferencesCreate) -> UserPreferences:
        """Create user preferences"""
        preferences = UserPreferences(
            user_id=user_id,
            **preferences_data.model_dump()
        )
        self.db.add(preferences)
        self.db.commit()
        self.db.refresh(preferences)
        return preferences

    def update_user_preferences(
        self,
        user_id: int,
        preferences_data: UserPreferencesUpdate
    ) -> Optional[UserPreferences]:
        """Update user preferences"""
        preferences = self.get_user_preferences(user_id)
        if not preferences:
            # Create if doesn't exist
            preferences = self.create_user_preferences(
                user_id,
                UserPreferencesCreate(**preferences_data.model_dump(exclude_unset=True))
            )
            return preferences

        update_data = preferences_data.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            setattr(preferences, key, value)

        self.db.commit()
        self.db.refresh(preferences)
        return preferences

    def get_or_create_user_preferences(self, user_id: int) -> UserPreferences:
        """Get user preferences or create with defaults"""
        preferences = self.get_user_preferences(user_id)
        if not preferences:
            preferences = self.create_user_preferences(
                user_id,
                UserPreferencesCreate()
            )
        return preferences
