import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import models  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.schemas import user as user_schemas  # noqa: E402
from app.services.user_service import UserService  # noqa: E402
from app.models.user import UserTypeEnum  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    models.Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=engine)
        engine.dispose()


def create_user(
    session,
    *,
    username,
    email,
    password="StrongPass1!",
    user_type=UserTypeEnum.USER,
    customer_id=None,
    is_superuser=False,
):
    user = models.User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        full_name=None,
        is_active=True,
        is_superuser=is_superuser,
        user_type=user_type,
        customer_id=customer_id,
    )
    session.add(user)
    session.flush()
    return user


def create_customer_with_admin(session, name, username, email):
    admin_user = create_user(
        session,
        username=username,
        email=email,
        user_type=UserTypeEnum.TENANT_ADMIN,
    )
    customer = models.Customer(
        name=name,
        description=None,
        logo=None,
        admin_id=admin_user.id,
    )
    session.add(customer)
    session.flush()
    admin_user.customer_id = customer.id
    session.commit()
    session.refresh(admin_user)
    session.refresh(customer)
    return customer, admin_user


def create_scenario_user(session, customer, username, email):
    scenario_user = create_user(
        session,
        username=username,
        email=email,
        user_type=UserTypeEnum.USER,
        customer_id=customer.id,
    )
    session.commit()
    session.refresh(scenario_user)
    return scenario_user


def test_tenant_admin_lists_only_scenario_users_in_their_customer(db_session):
    customer_a, admin_a = create_customer_with_admin(db_session, "Customer A", "admin_a", "admin_a@example.com")
    customer_b, _ = create_customer_with_admin(db_session, "Customer B", "admin_b", "admin_b@example.com")

    scenario_user_a1 = create_scenario_user(db_session, customer_a, "scenario_user_a1", "scenario_user_a1@example.com")
    scenario_user_a2 = create_scenario_user(db_session, customer_a, "scenario_user_a2", "scenario_user_a2@example.com")
    create_scenario_user(db_session, customer_b, "scenario_user_b1", "scenario_user_b1@example.com")

    service = UserService(db_session)
    scenario_users = service.list_accessible_users(current_user=admin_a, limit=10)

    assert {scenario_user.id for scenario_user in scenario_users} == {scenario_user_a1.id, scenario_user_a2.id}
    assert all(scenario_user.customer_id == customer_a.id for scenario_user in scenario_users)


def test_tenant_admin_create_scenario_user_defaults_to_customer_and_type(db_session):
    customer, admin = create_customer_with_admin(db_session, "Customer A", "admin", "admin@example.com")
    service = UserService(db_session)

    new_scenario_user = service.create_user(
        user_schemas.UserCreate(
            username="new_scenario_user",
            email="new_scenario_user@example.com",
            password="SecurePass1!",
        ),
        admin,
    )

    assert new_scenario_user.customer_id == customer.id
    assert service.get_user_type(new_scenario_user) == UserTypeEnum.USER
    assert new_scenario_user.is_superuser is False


def test_tenant_admin_cannot_create_non_scenario_user(db_session):
    _, admin = create_customer_with_admin(db_session, "Customer A", "admin", "admin@example.com")
    service = UserService(db_session)

    with pytest.raises(HTTPException) as exc:
        service.create_user(
            user_schemas.UserCreate(
                username="bad_user",
                email="bad_user@example.com",
                password="SecurePass1!",
                user_type=UserTypeEnum.TENANT_ADMIN,
            ),
            admin,
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_tenant_admin_updates_scenario_user_in_customer(db_session):
    customer, admin = create_customer_with_admin(db_session, "Customer A", "admin", "admin@example.com")
    scenario_user = create_scenario_user(db_session, customer, "scenario_user", "scenario_user@example.com")
    service = UserService(db_session)

    updated = service.update_user(
        scenario_user.id,
        user_schemas.UserUpdate(email="updated@example.com"),
        admin,
    )

    assert updated.email == "updated@example.com"


def test_tenant_admin_cannot_update_scenario_user_in_other_customer(db_session):
    _, admin = create_customer_with_admin(db_session, "Customer A", "admin", "admin@example.com")
    other_customer, _ = create_customer_with_admin(db_session, "Customer B", "other_admin", "other_admin@example.com")
    other_scenario_user = create_scenario_user(db_session, other_customer, "scenario_user_b", "scenario_user_b@example.com")
    service = UserService(db_session)

    with pytest.raises(HTTPException) as exc:
        service.update_user(
            other_scenario_user.id,
            user_schemas.UserUpdate(email="updated@example.com"),
            admin,
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_tenant_admin_deletes_scenario_user_in_customer(db_session):
    customer, admin = create_customer_with_admin(db_session, "Customer A", "admin", "admin@example.com")
    scenario_user = create_scenario_user(db_session, customer, "scenario_user", "scenario_user@example.com")
    service = UserService(db_session)

    response = service.delete_user(scenario_user.id, admin)

    assert response["message"] == "User deleted successfully"
    assert db_session.get(models.User, scenario_user.id) is None


def test_tenant_admin_cannot_delete_scenario_user_in_other_customer(db_session):
    _, admin = create_customer_with_admin(db_session, "Customer A", "admin", "admin@example.com")
    other_customer, _ = create_customer_with_admin(db_session, "Customer B", "other_admin", "other_admin@example.com")
    other_scenario_user = create_scenario_user(db_session, other_customer, "scenario_user_b", "scenario_user_b@example.com")
    service = UserService(db_session)

    with pytest.raises(HTTPException) as exc:
        service.delete_user(other_scenario_user.id, admin)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
