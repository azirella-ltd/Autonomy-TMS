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
        "groupadmin": UserTypeEnum.GROUP_ADMIN,
        "groupadministrator": UserTypeEnum.GROUP_ADMIN,
        "admin": UserTypeEnum.GROUP_ADMIN,
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

    def _normalize_customer_id(self, customer_id: Optional[Any]) -> Optional[int]:
        if customer_id is None:
            return None
        if isinstance(customer_id, str):
            stripped = customer_id.strip()
            if not stripped:
                return None
            if not stripped.isdigit():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid customer id",
                )
            return int(stripped)
        if isinstance(customer_id, int):
            return customer_id
        try:
            return int(customer_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid customer id",
            )

    def _validate_customer_assignment(
        self,
        customer_id: Optional[Any],
        user_type: UserTypeEnum,
    ) -> (Optional[models.Customer], Optional[int]):
        normalized_customer_id = self._normalize_customer_id(customer_id)
        customer: Optional[models.Customer] = None
        if normalized_customer_id is not None:
            customer = self.db.query(models.Customer).filter(models.Customer.id == normalized_customer_id).first()
            if not customer:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Customer not found",
                )

        if user_type in {UserTypeEnum.USER, UserTypeEnum.GROUP_ADMIN} and customer is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A customer assignment is required for this user type",
            )

        return customer, normalized_customer_id

    def _prepare_roles_for_type(
        self,
        base_roles: Optional[List[str]],
        user_type: str,
    ) -> List[str]:
        roles = self._strip_type_roles(base_roles)
        roles.extend(self.TYPE_ROLE_MAP[user_type])
        return self._dedupe_roles(roles)

    def _is_group_admin_user(self, user: Optional[models.User]) -> bool:
        if not user or not user.customer_id:
            return False
        return self._get_user_type(user) == UserTypeEnum.GROUP_ADMIN

    def _get_user_type(self, user: models.User) -> UserTypeEnum:
        fallback = UserTypeEnum.SYSTEM_ADMIN if user.is_superuser else user.user_type
        return self._resolve_user_type(
            user_type=user.user_type,
            fallback=fallback,
            assume_superuser=user.is_superuser,
        )

    def _find_group_admins(
        self,
        customer_id: Optional[int],
        exclude_user_id: Optional[int] = None,
    ) -> List[models.User]:
        if not customer_id:
            return []
        query = self.db.query(models.User).filter(models.User.customer_id == customer_id)
        if exclude_user_id is not None:
            query = query.filter(models.User.id != exclude_user_id)
        users = query.all()
        return [user for user in users if self._is_group_admin_user(user)]

    def _find_all_group_admins(self, exclude_user_id: Optional[int] = None) -> List[models.User]:
        query = self.db.query(models.User)
        if exclude_user_id is not None:
            query = query.filter(models.User.id != exclude_user_id)
        users = query.all()
        return [user for user in users if self._is_group_admin_user(user)]

    def _cleanup_group_admin_on_delete(self, user: models.User) -> Dict[str, Any]:
        if not self._is_group_admin_user(user):
            return {
                "customer_deleted": False,
                "customer_id": user.customer_id,
                "customer_name": None,
            }

        customer = self.db.query(models.Customer).filter(models.Customer.id == user.customer_id).first()
        if not customer:
            return {
                "customer_deleted": False,
                "customer_id": user.customer_id,
                "customer_name": None,
            }

        other_admins = self._find_group_admins(customer.id, exclude_user_id=user.id)
        if not other_admins:
            customer_name = customer.name
            self.db.delete(customer)
            return {
                "customer_deleted": True,
                "customer_id": customer.id,
                "customer_name": customer_name,
            }

        if customer.admin_id == user.id:
            customer.admin_id = other_admins[0].id
            self.db.add(customer)

        return {
            "customer_deleted": False,
            "customer_id": customer.id,
            "customer_name": customer.name,
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

    def list_customer_users(
        self,
        customer_id: Optional[int],
        skip: int = 0,
        limit: Optional[int] = 100,
    ) -> List[models.User]:
        if not customer_id:
            return []

        query = (
            self.db.query(models.User)
            .filter(models.User.customer_id == customer_id)
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
            target_type = normalized_type or UserTypeEnum.GROUP_ADMIN
            users = (
                self.db.query(models.User)
                .order_by(models.User.username.asc())
                .all()
            )
            filtered = [user for user in users if self._get_user_type(user) == target_type]

            start = max(skip, 0)
            end = start + limit if limit is not None else None
            return filtered[start:end]

        if acting_type == UserTypeEnum.GROUP_ADMIN:
            if normalized_type and normalized_type != UserTypeEnum.USER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins can only view users",
                )
            return self.list_customer_users(current_user.customer_id, skip=skip, limit=limit)

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    def is_group_admin(self, user: models.User) -> bool:
        return self._is_group_admin_user(user)

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
        acting_is_group_admin = acting_type == UserTypeEnum.GROUP_ADMIN

        if not acting_is_superuser and not acting_is_group_admin:
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
                fallback=UserTypeEnum.GROUP_ADMIN,
                assume_superuser=bool(user.is_superuser),
            )

            if desired_type != UserTypeEnum.GROUP_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators can only create group admin users",
                )

            customer, normalized_customer_id = self._validate_customer_assignment(user.customer_id, desired_type)
            is_superuser_flag = False
        else:
            if not current_user or not current_user.customer_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Group admins must belong to a customer",
                )

            if user.customer_id is not None and user.customer_id != current_user.customer_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins can only assign users to their own customer",
                )

            if user.user_type and self._normalize_type(user.user_type) != UserTypeEnum.USER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins can only create users",
                )

            if user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins cannot grant system permissions",
                )

            desired_type = UserTypeEnum.USER
            customer, normalized_customer_id = self._validate_customer_assignment(current_user.customer_id, desired_type)
            is_superuser_flag = False

        db_user = models.User(
            username=user.username,
            email=user.email,
            hashed_password=hashed_password,
            full_name=user.full_name,
            is_active=True,
            is_superuser=is_superuser_flag,
            customer_id=normalized_customer_id,
            user_type=desired_type,
        )

        try:
            self.db.add(db_user)
            self.db.flush()

            if desired_type == UserTypeEnum.GROUP_ADMIN and customer and (customer.admin_id is None):
                customer.admin_id = db_user.id
                self.db.add(customer)

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
        acting_is_group_admin = acting_type == UserTypeEnum.GROUP_ADMIN
        target_type = self._get_user_type(db_user)

        is_group_admin_managing_player = (
            acting_is_group_admin
            and not acting_is_superuser
            and user_id != current_user.id
            and target_type == UserTypeEnum.USER
            and db_user.customer_id == current_user.customer_id
        )

        if (
            user_id != current_user.id
            and not acting_is_superuser
            and not is_group_admin_managing_player
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        if is_group_admin_managing_player:
            if user_update.customer_id is not None and user_update.customer_id != current_user.customer_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins cannot change a scenario_user's customer",
                )

            if user_update.user_type and self._normalize_type(user_update.user_type) != UserTypeEnum.USER:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins can only manage users",
                )

            if user_update.is_superuser is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins cannot modify system permissions",
                )

            if user_update.is_active is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Group admins cannot change activation status",
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
            if target_type != UserTypeEnum.GROUP_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators can only manage group admin users",
                )

            normalized_update_type = (
                self._normalize_type(user_update.user_type)
                if user_update.user_type is not None
                else None
            )
            if normalized_update_type and normalized_update_type != UserTypeEnum.GROUP_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators can only assign the group admin user type",
                )

            if user_update.is_superuser is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators cannot modify system permissions for group admins",
                )

            if user_update.is_active is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System administrators cannot change activation status for group admins",
                )

            if user_update.customer_id is not None:
                self._validate_customer_assignment(user_update.customer_id, UserTypeEnum.GROUP_ADMIN)

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

        previous_customer_id = db_user.customer_id
        previous_type = target_type

        proposed_customer_id = (
            user_update.customer_id
            if user_update.customer_id is not None
            else db_user.customer_id
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

        customer, normalized_customer_id = self._validate_customer_assignment(proposed_customer_id, desired_type)

        if not acting_is_superuser:
            if normalized_customer_id != previous_customer_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enough permissions to change customer",
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

        # Prevent removing the last group admin from a customer via update
        if previous_type == UserTypeEnum.GROUP_ADMIN:
            changing_customer = normalized_customer_id != previous_customer_id
            losing_admin_role = desired_type != UserTypeEnum.GROUP_ADMIN
            if changing_customer or losing_admin_role:
                other_admins = self._find_group_admins(previous_customer_id, exclude_user_id=db_user.id)
                if not other_admins:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot remove the last group admin from the customer. Assign another group admin or delete the customer first.",
                    )
                previous_customer = self.db.query(models.Customer).filter(models.Customer.id == previous_customer_id).first()
                if previous_customer and previous_customer.admin_id == db_user.id:
                    previous_customer.admin_id = other_admins[0].id
                    self.db.add(previous_customer)

        db_user.customer_id = normalized_customer_id
        db_user.user_type = desired_type
        db_user.is_superuser = desired_type == UserTypeEnum.SYSTEM_ADMIN

        if user_update.password:
            db_user.hashed_password = get_password_hash(user_update.password)

        if desired_type == UserTypeEnum.GROUP_ADMIN and customer and (customer.admin_id is None or customer.admin_id == db_user.id):
            customer.admin_id = db_user.id
            self.db.add(customer)

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
        acting_is_group_admin = acting_type == UserTypeEnum.GROUP_ADMIN
        user_type = self._get_user_type(db_user)
        is_self_delete = user_id == current_user.id

        if acting_is_superuser and not is_self_delete and user_type != UserTypeEnum.GROUP_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System administrators can only delete group admin users",
            )

        can_group_admin_delete = (
            acting_is_group_admin
            and not acting_is_superuser
            and user_id != current_user.id
            and user_type == UserTypeEnum.USER
            and db_user.customer_id == current_user.customer_id
        )

        if (
            user_id != current_user.id
            and not acting_is_superuser
            and not can_group_admin_delete
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )

        if can_group_admin_delete and replacement_admin_id is not None:
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
                        candidates = self._find_all_group_admins(exclude_user_id=db_user.id)
                        if not candidates:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail={
                                    "code": "no_group_admin_available",
                                    "message": "Cannot delete the last system administrator. Create another system administrator first.",
                                },
                            )
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "code": "replacement_required",
                                "message": "Select a group administrator to promote before deleting the last system administrator.",
                                "candidates": [
                                    {
                                        "id": candidate.id,
                                        "username": candidate.username,
                                        "email": candidate.email,
                                        "customer_id": candidate.customer_id,
                                        "customer_name": candidate.customer.name if candidate.customer else None,
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
                    if not self._is_group_admin_user(replacement_user):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Replacement user must be a group admin",
                        )

                    replacement_user.user_type = UserTypeEnum.SYSTEM_ADMIN
                    replacement_user.is_superuser = True
                    self.db.add(replacement_user)
                    promoted_user = replacement_user

            customer_cleanup = self._cleanup_group_admin_on_delete(db_user)

            if not customer_cleanup.get("customer_deleted"):
                self.db.delete(db_user)
            self.db.commit()

            response: Dict[str, Any] = {"message": "User deleted successfully"}
            response.update(customer_cleanup)
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
