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
    group_id=None,
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
        group_id=group_id,
    )
    session.add(user)
    session.flush()
    return user


def create_group_with_admin(session, name, username, email):
    admin_user = create_user(
        session,
        username=username,
        email=email,
        user_type=UserTypeEnum.GROUP_ADMIN,
    )
    group = models.Group(
        name=name,
        description=None,
        logo=None,
        admin_id=admin_user.id,
    )
    session.add(group)
    session.flush()
    admin_user.group_id = group.id
    session.commit()
    session.refresh(admin_user)
    session.refresh(group)
    return group, admin_user


def create_player(session, group, username, email):
    player = create_user(
        session,
        username=username,
        email=email,
        user_type=UserTypeEnum.USER,
        group_id=group.id,
    )
    session.commit()
    session.refresh(player)
    return player


def test_group_admin_lists_only_players_in_their_group(db_session):
    group_a, admin_a = create_group_with_admin(db_session, "Group A", "admin_a", "admin_a@example.com")
    group_b, _ = create_group_with_admin(db_session, "Group B", "admin_b", "admin_b@example.com")

    player_a1 = create_player(db_session, group_a, "player_a1", "player_a1@example.com")
    player_a2 = create_player(db_session, group_a, "player_a2", "player_a2@example.com")
    create_player(db_session, group_b, "player_b1", "player_b1@example.com")

    service = UserService(db_session)
    players = service.list_accessible_users(current_user=admin_a, limit=10)

    assert {player.id for player in players} == {player_a1.id, player_a2.id}
    assert all(player.group_id == group_a.id for player in players)


def test_group_admin_create_player_defaults_to_group_and_type(db_session):
    group, admin = create_group_with_admin(db_session, "Group A", "admin", "admin@example.com")
    service = UserService(db_session)

    new_player = service.create_user(
        user_schemas.UserCreate(
            username="new_player",
            email="new_player@example.com",
            password="SecurePass1!",
        ),
        admin,
    )

    assert new_player.group_id == group.id
    assert service.get_user_type(new_player) == UserTypeEnum.USER
    assert new_player.is_superuser is False


def test_group_admin_cannot_create_non_player(db_session):
    _, admin = create_group_with_admin(db_session, "Group A", "admin", "admin@example.com")
    service = UserService(db_session)

    with pytest.raises(HTTPException) as exc:
        service.create_user(
            user_schemas.UserCreate(
                username="bad_user",
                email="bad_user@example.com",
                password="SecurePass1!",
                user_type=UserTypeEnum.GROUP_ADMIN,
            ),
            admin,
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_group_admin_updates_player_in_group(db_session):
    group, admin = create_group_with_admin(db_session, "Group A", "admin", "admin@example.com")
    player = create_player(db_session, group, "player", "player@example.com")
    service = UserService(db_session)

    updated = service.update_user(
        player.id,
        user_schemas.UserUpdate(email="updated@example.com"),
        admin,
    )

    assert updated.email == "updated@example.com"


def test_group_admin_cannot_update_player_in_other_group(db_session):
    _, admin = create_group_with_admin(db_session, "Group A", "admin", "admin@example.com")
    other_group, _ = create_group_with_admin(db_session, "Group B", "other_admin", "other_admin@example.com")
    other_player = create_player(db_session, other_group, "player_b", "player_b@example.com")
    service = UserService(db_session)

    with pytest.raises(HTTPException) as exc:
        service.update_user(
            other_player.id,
            user_schemas.UserUpdate(email="updated@example.com"),
            admin,
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_group_admin_deletes_player_in_group(db_session):
    group, admin = create_group_with_admin(db_session, "Group A", "admin", "admin@example.com")
    player = create_player(db_session, group, "player", "player@example.com")
    service = UserService(db_session)

    response = service.delete_user(player.id, admin)

    assert response["message"] == "User deleted successfully"
    assert db_session.get(models.User, player.id) is None


def test_group_admin_cannot_delete_player_in_other_group(db_session):
    _, admin = create_group_with_admin(db_session, "Group A", "admin", "admin@example.com")
    other_group, _ = create_group_with_admin(db_session, "Group B", "other_admin", "other_admin@example.com")
    other_player = create_player(db_session, other_group, "player_b", "player_b@example.com")
    service = UserService(db_session)

    with pytest.raises(HTTPException) as exc:
        service.delete_user(other_player.id, admin)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
