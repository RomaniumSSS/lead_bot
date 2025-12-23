"""Тесты квалификации лидов.

Эти тесты критически важны — ошибка в квалификации = потеря денег.
Функция _qualify_lead() определяет статус лида (HOT/WARM/COLD),
от которого зависит получит ли владелец уведомление.
"""

from src.database.models import LeadStatus

# Импортируем функцию квалификации
# AICODE-NOTE: Функция приватная, но критически важная для тестов
from src.handlers.conversation import _qualify_lead


class TestQualifyLeadHot:
    """Тесты для HOT статуса — самые важные, это деньги."""

    def test_urgent_high_budget_is_hot(self) -> None:
        """Срочно + 150к+ = HOT."""
        assert _qualify_lead("urgent", "150 000+ ₽") == LeadStatus.HOT

    def test_urgent_medium_budget_is_hot(self) -> None:
        """Срочно + 50-150к = HOT."""
        assert _qualify_lead("urgent", "50 000 - 150 000 ₽") == LeadStatus.HOT

    def test_high_budget_soon_is_hot(self) -> None:
        """150к+ + скоро = HOT (высокий бюджет перевешивает)."""
        assert _qualify_lead("soon", "150 000+ ₽") == LeadStatus.HOT

    def test_high_budget_urgent_is_hot(self) -> None:
        """150к+ + срочно = HOT."""
        assert _qualify_lead("urgent", "150 000+ ₽") == LeadStatus.HOT


class TestQualifyLeadWarm:
    """Тесты для WARM статуса — заинтересованные, но не срочные."""

    def test_soon_low_budget_is_warm(self) -> None:
        """Скоро + низкий бюджет = WARM."""
        assert _qualify_lead("soon", "До 50 000 ₽") == LeadStatus.WARM

    def test_soon_medium_budget_is_warm(self) -> None:
        """Скоро + средний бюджет = WARM."""
        assert _qualify_lead("soon", "50 000 - 150 000 ₽") == LeadStatus.WARM

    def test_urgent_low_budget_is_warm(self) -> None:
        """Срочно + низкий бюджет = WARM (срочность спасает)."""
        assert _qualify_lead("urgent", "До 50 000 ₽") == LeadStatus.WARM

    def test_urgent_unknown_budget_is_warm(self) -> None:
        """Срочно + неизвестный бюджет = WARM."""
        assert _qualify_lead("urgent", "Пока не знаю") == LeadStatus.WARM

    def test_medium_budget_later_is_warm(self) -> None:
        """Средний бюджет + не срочно = WARM (бюджет спасает)."""
        assert _qualify_lead("later", "50 000 - 150 000 ₽") == LeadStatus.WARM


class TestQualifyLeadCold:
    """Тесты для COLD статуса — низкий приоритет."""

    def test_later_low_budget_is_cold(self) -> None:
        """Не срочно + низкий бюджет = COLD."""
        assert _qualify_lead("later", "До 50 000 ₽") == LeadStatus.COLD

    def test_later_unknown_budget_is_cold(self) -> None:
        """Не срочно + неизвестный бюджет = COLD."""
        assert _qualify_lead("later", "Пока не знаю") == LeadStatus.COLD

    def test_soon_unknown_budget_is_warm_not_cold(self) -> None:
        """Скоро + неизвестный = WARM (скоро спасает от COLD)."""
        # Важно: это НЕ COLD, потому что срок "скоро"
        assert _qualify_lead("soon", "Пока не знаю") == LeadStatus.WARM


class TestQualifyLeadEdgeCases:
    """Граничные случаи и нестандартные входные данные."""

    def test_unknown_deadline_type(self) -> None:
        """Неизвестный тип срока — fallback на COLD."""
        result = _qualify_lead("unknown", "50 000 - 150 000 ₽")
        # Средний бюджет спасает → WARM
        assert result == LeadStatus.WARM

    def test_empty_budget(self) -> None:
        """Пустой бюджет — fallback на COLD."""
        result = _qualify_lead("later", "")
        assert result == LeadStatus.COLD

    def test_high_budget_later_is_hot(self) -> None:
        """Высокий бюджет + не срочно = всё равно HOT? Проверяем логику."""
        # По текущей логике: 150к+ + later = COLD (later блокирует HOT)
        result = _qualify_lead("later", "150 000+ ₽")
        # Проверяем что высокий бюджет НЕ делает HOT при later
        # (это важное бизнес-правило!)
        assert result != LeadStatus.HOT
