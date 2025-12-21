"""Тесты для моделей БД."""

import pytest
from tortoise.exceptions import IntegrityError

from src.database.models import Lead, LeadStatus


@pytest.mark.asyncio
async def test_create_lead(test_telegram_id: int, test_username: str) -> None:
    """Тест создания лида."""
    lead = await Lead.create(
        telegram_id=test_telegram_id,
        username=test_username,
        first_name="Test",
        last_name="User",
        status=LeadStatus.NEW,
    )

    assert lead.id is not None
    assert lead.telegram_id == test_telegram_id
    assert lead.username == test_username
    assert lead.status == LeadStatus.NEW
    assert lead.created_at is not None
    assert lead.updated_at is not None


@pytest.mark.asyncio
async def test_lead_unique_telegram_id(test_telegram_id: int) -> None:
    """Тест уникальности telegram_id."""
    # Создаём первого лида
    await Lead.create(
        telegram_id=test_telegram_id,
        username="user1",
        first_name="First",
    )

    # Попытка создать второго лида с тем же telegram_id должна упасть
    with pytest.raises(IntegrityError):
        await Lead.create(
            telegram_id=test_telegram_id,
            username="user2",
            first_name="Second",
        )


@pytest.mark.asyncio
async def test_get_or_create_lead(test_telegram_id: int) -> None:
    """Тест get_or_create для лида."""
    # Первый раз - создание
    lead1, created1 = await Lead.get_or_create(
        telegram_id=test_telegram_id,
        defaults={
            "username": "test_user",
            "first_name": "Test",
        },
    )
    assert created1 is True
    assert lead1.telegram_id == test_telegram_id

    # Второй раз - получение существующего
    lead2, created2 = await Lead.get_or_create(
        telegram_id=test_telegram_id,
        defaults={
            "username": "another_user",
            "first_name": "Another",
        },
    )
    assert created2 is False
    assert lead2.id == lead1.id
    assert lead2.username == "test_user"  # Не изменился


@pytest.mark.asyncio
async def test_update_lead_status(test_telegram_id: int) -> None:
    """Тест обновления статуса лида."""
    lead = await Lead.create(
        telegram_id=test_telegram_id,
        username="test_user",
        status=LeadStatus.NEW,
    )

    # Обновляем статус
    lead.status = LeadStatus.HOT
    await lead.save()

    # Проверяем, что изменения сохранились
    updated_lead = await Lead.get(telegram_id=test_telegram_id)
    assert updated_lead.status == LeadStatus.HOT


@pytest.mark.asyncio
async def test_filter_leads_by_status() -> None:
    """Тест фильтрации лидов по статусу."""
    # Создаём лидов с разными статусами
    await Lead.create(telegram_id=111, username="hot1", status=LeadStatus.HOT)
    await Lead.create(telegram_id=222, username="hot2", status=LeadStatus.HOT)
    await Lead.create(telegram_id=333, username="warm1", status=LeadStatus.WARM)
    await Lead.create(telegram_id=444, username="cold1", status=LeadStatus.COLD)

    # Фильтруем горячих лидов
    hot_leads = await Lead.filter(status=LeadStatus.HOT).all()
    assert len(hot_leads) == 2

    # Фильтруем тёплых
    warm_leads = await Lead.filter(status=LeadStatus.WARM).all()
    assert len(warm_leads) == 1

    # Фильтруем холодных
    cold_leads = await Lead.filter(status=LeadStatus.COLD).all()
    assert len(cold_leads) == 1


@pytest.mark.asyncio
async def test_lead_count() -> None:
    """Тест подсчёта лидов."""
    # Создаём несколько лидов
    for i in range(5):
        await Lead.create(
            telegram_id=1000 + i,
            username=f"user{i}",
            status=LeadStatus.NEW,
        )

    # Проверяем количество
    count = await Lead.all().count()
    assert count == 5
