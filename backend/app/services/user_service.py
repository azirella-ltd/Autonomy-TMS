from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status
from .. import models
from ..schemas import user as user_schemas
from ..core.security import get_password_hash, verify_password
from ..models.user import UserTypeEnum


class UserService:
    """Service layer for user management."""

    TYPE_ALIASES = {
        "scenario_user": UserTypeEnum.USER,
        "scenario_users": UserTypeEnum.USER,
        "user": UserTypeEnum.USER,
        "users": UserTypeEnum.USER,
        "tenantadmin": UserTypeEnum.TENANT_ADMIN,
        "tenantadministrator": UserTypeEnum.TENANT_ADMIN,
        "admin": UserTypeEnum.TENANT_ADMIN,
        "systemadmin": UserTypeEnum.SYSTEM_ADMIN,
        "systemadministrator": UserTypeEnum.SYSTEM_ADMIN,
        "superadmin": UserTypeEnum.SYSTEM_ADMIN,
    }

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _normalize_token(self, value: Optional[Any]) -> str:
        if not value:
            return ""
        return "".join(ch for ch in str(value).lower() if ch.isalnum())

    def _normalize_type(self, user_type: Optional[Any]) -> Optional[UserTypeEnum]:
        if not user_type:
            return None
        if isinstance(user_type, UserTypeEnum):
            return user_type
        token = self._normalize_token(user_type)
        if token not in self.TYPE_ALIASES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user type specified",
            )
        return self.TYPE_ALIASES[token]

    def _resolve_user_type(
        self,
        user_type: Optional[Any],
        fallback: Optional[UserTypeEnum] = None,
        assume_superuser: bool = False,
    ) -> UserTypeEnum:
        normalized_type = self._normalize_type(user_type)
        if normalized_type:
            return normalized_type

        if assume_superuser:
            return UserTypeEnum.SYSTEM_ADMIN

        if fallback is not None:
            return fallback

        return UserTypeEnum.USER

    def _normalize_tenant_id(self, tenant_id: Optional[Any]) -> Optional[int]:
        if tenant_id is None:
            return None
        if isinstance(tenant_id, str):
            stripped = tenant_id.strip()
            if not stripped:
                return None
            if not stripped.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid tenant id",
                )
            return int(stripped)
        if isinstance(tenant_id, int):
            return tenant_id
        try:
            return int(tenant_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant id",
            )

    def _validate_tenant_assignment(
        self,
        tenant_id: Optional[Any],
        user_type: UserTypeEnum,
    ) -> (Optional[models.Tenant], Optional[int]):
        normalized_tenant_id = self._normalize_tenant_id(tenant_id)
        tenant: Optional[models.Tenant] = None
        if normalized_tenant_id is not None:
            tenant = self.db.query(models.Tenant).filter(models.Tenant.id == normalized_tenant_id).first()
            if not tenant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Tenant not found",
                )

        if user_type in {UserTypeEnum.USER, UserTypeEnum.TENANT_ADMIN} and tenant is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A tenant assignment is required for this user type",
            )

        return tenant, normalized_tenant_id

    def _prepare_roles_for_type(
        self,
        base_roles: Optional[List[str]],
        user_type: str,
    ) -> List[str]:
        roles = self._strip_type_roles(base_roles)
        roles.extend(self.TYPE_ROLE_MAP[user_type])
        return self._dedupe_roles(roles)

    def _is_tenant_admin_user(self, user: Optional[models.User]) -> bool:
        if not user or not user.tenant_id:
            return False
        return self._get_user_type(user) == UserTypeEnum.TENANT_ADMIN

    def _get_user_type(self, user: models.User) -> UserTypeEnum:
        fallback = UserTypeEnum.SYSTEM_ADMIN if user.is_superuser else user.user_type
        return self._resolve_user_type(
            user_type=user.user_type,
            fallback=fallback,
            assume_superuser=user.is_superuser,
        )

    def _find_tenant_admins(
        self,
        tenant_id: Optional[int],
        exclude_user_id: Optional[int] = None,
    ) -> List[models.User]:
        if not tenant_id:
            return []
        query = self.db.query(models.User).filter(models.User.tenant_id == tenant_id)
        if exclude_user_id is not None:
            query = query.filter(models.User.id != exclude_user_id)
        users = query.all()
        return [user for user in users if self._is_tenant_admin_user(user)]

    def _find_all_tenant_admins(self, exclude_user_id: Optional[int] = None) -> List[models.User]:
        query = self.db.query(models.User)
        if exclude_user_id is not None:
            query = query.filter(models.User.id != exclude_user_id)
        users = query.all()
        return [user for user in users if self._is_tenant_admin_user(user)]

    def _cleanup_tenant_admin_on_delete(self, user: models.User) -> Dict[str, Any]:
        if not self._is_tenant_admin_user(user):
            return {
                "tenant_deleted": False,
                "tenant_id": user.tenant_id,
                "tenant_name": None,
            }

        tenant = self.db.query(models.Tenant).filter(models.Tenant.id == user.tenant_id).first()
        if not tenant:
            return {
                "tenant_deleted": False,
                "tenant_id": user.tenant_id,
                "tenant_name": None,
            }

        other_admins = self._find_tenant_admins(tenant.id, exclude_user_id=user.id)
        if not other_admins:
            tenant_name = tenant.name
            self.db.delete(tenant)
            return {
                "tenant_deleted": True,
                "tenant_id": tenant.id,
                "tenant_name": tenant_name,
            }

        if tenant.admin_id == user.id:
            tenant.admin_id = other_admins[0].id
            self.db.add(tenant)

        return {
            "tenant_deleted": False,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_user(self, user_id: int) -> models.User:
        user = self.db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found",
            )
        return user

    def get_user_by_email(self, email: str) -> Optional[models.User]:
        return self.db.query(models.User).filter(models.User.email == email).first()

    def get_user_by_username(self, username: str) -> Optional[models.User]:
        return self.db.query(models.User).filter(models.User.username == username).first()

    def get_users(self, skip: int = 0, limit: int = 100) -> List[models.User]:
        return self.db.query(models.User).offset(skip).limit(limit).all()

    def list_tenant_users(
        self,
        tenant_id: Optional[int],
        skip: int = 0,
        limit: Optional[int] = 100,
    ) -> List[models.User]:
        if not tenant_id:
            return []

        query = (
            self.db.query(models.User)
            .filter(models.User.tenant_id == tenant_id)
            .order_by(models.User.username.asc())
        )
        users = query.all()
        scenario_users = [user for user in users if self._get_user_type(user) == UserTypeEnum.USER]

        if skip or (limit is not None and limit >= 0):
            end = skip + limit if limit is not None else None
            return scenario_users[skip:end]
        return scenario_users

    def list_accessible_users(
        self,
        current_user: models.User,
        skip: int = 0,
        limit: int = 100,
        user_type: Optional[str] = None,
    ) -> List[models.User]:
        normalized_type = self._normalize_type(user_type) if user_type else None

        acting_type = self._get_user_type(current_user)

        if acting_type == UserTypeEnum.SYSTEM_ADMIN:
            target_type = normalized_type or UserTypeEnum.TENANT_ADMIN
            users = (
                self.db.query(models.User)
                .order_by(models.User.username.asc())
                .all()
            )
            filtered = [user for user in users if self._get_user_type(user) == target_type]

            start = max(skip, 0)
            end = start + limit if limit is not None else None
            return filtered[start:end]

        if acting_type == UserTypeEnum.TENANT_ADMIN:
            if normalized_type and normalized_type != UserTypeEnum.USER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins can only view users",
                )
            return self.list_tenant_users(current_user.tenant_id, skip=skip, limit=limit)

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    def is_tenant_admin(self, user: models.User) -> bool:
        return self._is_tenant_admin_user(user)

    def get_user_type(self, user: models.User) -> UserTypeEnum:
        return self._get_user_type(user)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def create_user(
        self,
        user: user_schemas.UserCreate,
        current_user: models.User,
    ) -> models.User:
        acting_type = self._get_user_type(current_user) if current_user else None
        acting_is_superuser = acting_type == UserTypeEnum.SYSTEM_ADMIN
        acting_is_tenant_admin = acting_type == UserTypeEnum.TENANT_ADMIN

        if not acting_is_superuser and not acting_is_tenant_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        existing = self.get_user_by_email(user.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        existing = self.get_user_by_username(user.username)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )

        hashed_password = get_password_hash(user.password)

        if acting_is_superuser:
            desired_type = self._resolve_user_type(
                user_type=user.user_type,
                fallback=UserTypeEnum.TENANT_ADMIN,
                assume_superuser=bool(user.is_superuser),
            )

            if desired_type != UserTypeEnum.TENANT_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators can only create tenant admin users",
                )

            tenant, normalized_tenant_id = self._validate_tenant_assignment(user.tenant_id, desired_type)
            is_superuser_flag = False
        else:
            if not current_user or not current_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tenant admins must belong to a tenant",
                )

            if user.tenant_id is not None and user.tenant_id != current_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins can only assign users to their own tenant",
                )

            if user.user_type and self._normalize_type(user.user_type) != UserTypeEnum.USER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins can only create users",
                )

            if user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins cannot grant system permissions",
                )

            desired_type = UserTypeEnum.USER
            tenant, normalized_tenant_id = self._validate_tenant_assignment(current_user.tenant_id, desired_type)
            is_superuser_flag = False

        db_user = models.User(
            username=user.username,
            email=user.email,
            hashed_password=hashed_password,
            full_name=user.full_name,
            is_active=True,
            is_superuser=is_superuser_flag,
            tenant_id=normalized_tenant_id,
            user_type=desired_type,
            decision_level=user.decision_level,
            site_scope=user.site_scope,
            product_scope=user.product_scope,
        )

        try:
            self.db.add(db_user)
            self.db.flush()

            if desired_type == UserTypeEnum.TENANT_ADMIN and tenant and (tenant.admin_id is None):
                tenant.admin_id = db_user.id
                self.db.add(tenant)

            self.db.commit()
            self.db.refresh(db_user)
            return db_user
        except SQLAlchemyError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creating user",
            )

    def update_user(
        self,
        user_id: int,
        user_update: user_schemas.UserUpdate,
        current_user: models.User,
    ) -> models.User:
        db_user = self.get_user(user_id)
        acting_type = self._get_user_type(current_user)
        acting_is_superuser = acting_type == UserTypeEnum.SYSTEM_ADMIN
        acting_is_tenant_admin = acting_type == UserTypeEnum.TENANT_ADMIN
        target_type = self._get_user_type(db_user)

        is_tenant_admin_managing_user = (
            acting_is_tenant_admin
            and not acting_is_superuser
            and user_id != current_user.id
            and target_type == UserTypeEnum.USER
            and db_user.tenant_id == current_user.tenant_id
        )

        if (
            user_id != current_user.id
            and not acting_is_superuser
            and not is_tenant_admin_managing_user
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        if is_tenant_admin_managing_user:
            if user_update.tenant_id is not None and user_update.tenant_id != current_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins cannot change a user's tenant",
                )

            if user_update.user_type and self._normalize_type(user_update.user_type) != UserTypeEnum.USER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins can only manage users",
                )

            if user_update.is_superuser is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins cannot modify system permissions",
                )

            if user_update.is_active is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant admins cannot change activation status",
                )

            if user_update.email is not None:
                existing = self.get_user_by_email(user_update.email)
                if existing and existing.id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email already registered",
                    )
                db_user.email = user_update.email

            if user_update.username is not None:
                existing = self.get_user_by_username(user_update.username)
                if existing and existing.id != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Username already taken",
                    )
                db_user.username = user_update.username

            if user_update.full_name is not None:
                db_user.full_name = user_update.full_name

            if user_update.decision_level is not None:
                db_user.decision_level = user_update.decision_level
            if user_update.site_scope is not None:
                db_user.site_scope = user_update.site_scope
            if user_update.product_scope is not None:
                db_user.product_scope = user_update.product_scope

            if user_update.password:
                db_user.hashed_password = get_password_hash(user_update.password)

            try:
                self.db.commit()
                self.db.refresh(db_user)
                return db_user
            except SQLAlchemyError:
                self.db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Error updating user",
                )

        if acting_is_superuser and user_id != current_user.id:
            if target_type != UserTypeEnum.TENANT_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators can only manage tenant admin users",
                )

            normalized_update_type = (
                self._normalize_type(user_update.user_type)
                if user_update.user_type is not None
                else None
            )
            if normalized_update_type and normalized_update_type != UserTypeEnum.TENANT_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators can only assign the tenant admin user type",
                )

            if user_update.is_superuser is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators cannot modify system permissions for tenant admins",
                )

            if user_update.is_active is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators cannot change activation status for tenant admins",
                )

            if user_update.tenant_id is not None:
                self._validate_tenant_assignment(user_update.tenant_id, UserTypeEnum.TENANT_ADMIN)

        if user_update.email is not None:
            existing = self.get_user_by_email(user_update.email)
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered",
                )
            db_user.email = user_update.email

        if user_update.username is not None:
            existing = self.get_user_by_username(user_update.username)
            if existing and existing.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken",
                )
            db_user.username = user_update.username

        if user_update.full_name is not None:
            db_user.full_name = user_update.full_name

        if user_update.is_active is not None and acting_is_superuser:
            db_user.is_active = user_update.is_active

        previous_tenant_id = db_user.tenant_id
        previous_type = target_type

        proposed_tenant_id = (
            user_update.tenant_id
            if user_update.tenant_id is not None
            else db_user.tenant_id
        )

        desired_type = self._resolve_user_type(
            user_type=user_update.user_type,
            fallback=target_type,
            assume_superuser=bool(
                user_update.is_superuser
                if user_update.is_superuser is not None
                else db_user.is_superuser
            ),
        )

        tenant, normalized_tenant_id = self._validate_tenant_assignment(proposed_tenant_id, desired_type)

        if not acting_is_superuser:
            if normalized_tenant_id != previous_tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enough permissions to change tenant",
                )

            if desired_type != previous_type:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enough permissions to change user type",
                )

            if user_update.is_superuser is not None and user_update.is_superuser != db_user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enough permissions to change system privileges",
                )

        # Prevent removing the last tenant admin from a tenant via update
        if previous_type == UserTypeEnum.TENANT_ADMIN:
            changing_tenant = normalized_tenant_id != previous_tenant_id
            losing_admin_role = desired_type != UserTypeEnum.TENANT_ADMIN
            if changing_tenant or losing_admin_role:
                other_admins = self._find_tenant_admins(previous_tenant_id, exclude_user_id=db_user.id)
                if not other_admins:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot remove the last tenant admin from the tenant. Assign another tenant admin or delete the tenant first.",
                    )
                previous_tenant = self.db.query(models.Tenant).filter(models.Tenant.id == previous_tenant_id).first()
                if previous_tenant and previous_tenant.admin_id == db_user.id:
                    previous_tenant.admin_id = other_admins[0].id
                    self.db.add(previous_tenant)

        db_user.tenant_id = normalized_tenant_id
        db_user.user_type = desired_type
        db_user.is_superuser = desired_type == UserTypeEnum.SYSTEM_ADMIN

        if user_update.password:
            db_user.hashed_password = get_password_hash(user_update.password)

        # Scope fields — only admins can change (not self-edit)
        if acting_is_superuser or is_tenant_admin_managing_user:
            if user_update.decision_level is not None:
                db_user.decision_level = user_update.decision_level
            if user_update.site_scope is not None:
                db_user.site_scope = user_update.site_scope
            if user_update.product_scope is not None:
                db_user.product_scope = user_update.product_scope

        if desired_type == UserTypeEnum.TENANT_ADMIN and tenant and (tenant.admin_id is None or tenant.admin_id == db_user.id):
            tenant.admin_id = db_user.id
            self.db.add(tenant)

        try:
            self.db.commit()
            self.db.refresh(db_user)
            return db_user
        except SQLAlchemyError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error updating user",
            )

    def delete_user(
        self,
        user_id: int,
        current_user: models.User,
        replacement_admin_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        db_user = self.get_user(user_id)
        acting_type = self._get_user_type(current_user)
        acting_is_superuser = acting_type == UserTypeEnum.SYSTEM_ADMIN
        acting_is_tenant_admin = acting_type == UserTypeEnum.TENANT_ADMIN
        user_type = self._get_user_type(db_user)
        is_self_delete = user_id == current_user.id

        if acting_is_superuser and not is_self_delete and user_type != UserTypeEnum.TENANT_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System administrators can only delete tenant admin users",
            )

        can_tenant_admin_delete = (
            acting_is_tenant_admin
            and not acting_is_superuser
            and user_id != current_user.id
            and user_type == UserTypeEnum.USER
            and db_user.tenant_id == current_user.tenant_id
        )

        if (
            user_id != current_user.id
            and not acting_is_superuser
            and not can_tenant_admin_delete
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        if can_tenant_admin_delete and replacement_admin_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Replacement admin is not required when deleting a scenario_user",
            )

        promoted_user: Optional[models.User] = None

        try:
            if user_type == UserTypeEnum.SYSTEM_ADMIN:
                other_admins = self.db.query(models.User).filter(
                    models.User.id != db_user.id,
                    models.User.is_superuser == True,
                    models.User.is_active == True,
                ).count()

                if other_admins == 0:
                    if replacement_admin_id is None:
                        candidates = self._find_all_tenant_admins(exclude_user_id=db_user.id)
                        if not candidates:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail={
                                    "code": "no_tenant_admin_available",
                                    "message": "Cannot delete the last system administrator. Create another system administrator first.",
                                },
                            )
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "code": "replacement_required",
                                "message": "Select a tenant administrator to promote before deleting the last system administrator.",
                                "candidates": [
                                    {
                                        "id": candidate.id,
                                        "username": candidate.username,
                                        "email": candidate.email,
                                        "tenant_id": candidate.tenant_id,
                                        "tenant_name": candidate.tenant.name if candidate.tenant else None,
                                    }
                                    for candidate in candidates
                                ],
                            },
                        )

                    replacement_user = self.get_user(replacement_admin_id)
                    if replacement_user.id == db_user.id:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Replacement user must be different from the user being deleted",
                        )
                    if not self._is_tenant_admin_user(replacement_user):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Replacement user must be a tenant admin",
                        )

                    replacement_user.user_type = UserTypeEnum.SYSTEM_ADMIN
                    replacement_user.is_superuser = True
                    self.db.add(replacement_user)
                    promoted_user = replacement_user

            tenant_cleanup = self._cleanup_tenant_admin_on_delete(db_user)

            if not tenant_cleanup.get("tenant_deleted"):
                self.db.delete(db_user)
            self.db.commit()

            response: Dict[str, Any] = {"message": "User deleted successfully"}
            response.update(tenant_cleanup)
            if promoted_user:
                response["replacement_promoted"] = {
                    "id": promoted_user.id,
                    "username": promoted_user.username,
                    "email": promoted_user.email,
                }
            return response
        except HTTPException:
            self.db.rollback()
            raise
        except SQLAlchemyError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error deleting user",
            )

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
        current_user: models.User,
    ) -> Dict[str, str]:
        if user_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        db_user = self.get_user(user_id)

        if not (current_user.is_superuser and user_id != current_user.id):
            if not verify_password(current_password, db_user.hashed_password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Incorrect current password",
                )

        db_user.hashed_password = get_password_hash(new_password)

        try:
            self.db.commit()
            return {"message": "Password updated successfully"}
        except SQLAlchemyError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error updating password",
            )
