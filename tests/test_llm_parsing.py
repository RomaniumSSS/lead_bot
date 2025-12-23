"""Тесты парсинга JSON ответов от Claude.

Эти тесты критически важны — Claude возвращает JSON в разных форматах.
Сломанный парсинг = бот отвечает мусором клиенту.
"""

from src.database.models import LeadStatus

# Импортируем функцию парсинга
from src.services.llm import _parse_llm_response


class TestParseValidJson:
    """Тесты для корректного JSON от Claude."""

    def test_parse_clean_json(self) -> None:
        """Чистый JSON без обёрток."""
        response = '{"response": "Привет!", "status": "HOT", "action": "continue"}'
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["response"] == "Привет!"
        assert result["status"] == LeadStatus.HOT
        assert result["action"] == "continue"

    def test_parse_json_with_newlines(self) -> None:
        """JSON с переносами строк."""
        response = """{
            "response": "Понял вас!",
            "status": "WARM",
            "action": "send_materials"
        }"""
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["response"] == "Понял вас!"
        assert result["status"] == LeadStatus.WARM
        assert result["action"] == "send_materials"

    def test_parse_schedule_meeting_action(self) -> None:
        """Действие schedule_meeting парсится корректно."""
        response = (
            '{"response": "Давайте встретимся!", "status": "HOT", ' '"action": "schedule_meeting"}'
        )
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["action"] == "schedule_meeting"


class TestParseMarkdownWrappedJson:
    """Тесты для JSON обёрнутого в markdown."""

    def test_parse_json_in_markdown_block(self) -> None:
        """JSON в блоке ```json ... ```."""
        response = """```json
{"response": "Ок!", "status": "WARM", "action": "continue"}
```"""
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["response"] == "Ок!"
        assert result["status"] == LeadStatus.WARM

    def test_parse_json_in_plain_markdown_block(self) -> None:
        """JSON в блоке ``` ... ``` (без json)."""
        response = """```
{"response": "Тест", "status": "COLD", "action": "continue"}
```"""
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["response"] == "Тест"
        assert result["status"] == LeadStatus.COLD

    def test_parse_json_with_extra_whitespace(self) -> None:
        """JSON с пробелами вокруг."""
        response = """

   {"response": "Пробелы", "status": "HOT", "action": "continue"}

   """
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["response"] == "Пробелы"


class TestParseInvalidStatus:
    """Тесты для некорректного статуса от Claude."""

    def test_unknown_status_uses_default(self) -> None:
        """Неизвестный статус → используем default."""
        response = '{"response": "Ок", "status": "UNKNOWN", "action": "continue"}'
        result = _parse_llm_response(response, LeadStatus.WARM)

        assert result["status"] == LeadStatus.WARM  # default

    def test_empty_status_uses_default(self) -> None:
        """Пустой статус → используем default."""
        response = '{"response": "Ок", "status": "", "action": "continue"}'
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["status"] == LeadStatus.NEW  # default

    def test_lowercase_status_is_parsed(self) -> None:
        """Статус в lowercase → парсится корректно."""
        response = '{"response": "Ок", "status": "hot", "action": "continue"}'
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["status"] == LeadStatus.HOT


class TestParseInvalidAction:
    """Тесты для некорректного action от Claude."""

    def test_unknown_action_defaults_to_continue(self) -> None:
        """Неизвестный action → fallback на continue."""
        response = '{"response": "Ок", "status": "HOT", "action": "unknown_action"}'
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["action"] == "continue"

    def test_empty_action_defaults_to_continue(self) -> None:
        """Пустой action → fallback на continue."""
        response = '{"response": "Ок", "status": "HOT", "action": ""}'
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["action"] == "continue"


class TestParseNotJson:
    """Тесты когда Claude возвращает не JSON (галлюцинация)."""

    def test_plain_text_returns_as_response(self) -> None:
        """Простой текст → возвращается как response."""
        response = "Извините, я не понял ваш вопрос."
        result = _parse_llm_response(response, LeadStatus.WARM)

        assert result["response"] == response
        assert result["status"] == LeadStatus.WARM  # default
        assert result["action"] == "continue"  # default

    def test_broken_json_returns_as_response(self) -> None:
        """Сломанный JSON → возвращается как response."""
        response = '{"response": "Ок", "status": '  # Незакрытый JSON
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["response"] == response
        assert result["status"] == LeadStatus.NEW

    def test_html_returns_as_response(self) -> None:
        """HTML вместо JSON → возвращается как response."""
        response = "<html><body>Error 500</body></html>"
        result = _parse_llm_response(response, LeadStatus.NEW)

        assert result["response"] == response
