__all__ = ["ABCScreener"]

from abc import ABC, abstractmethod
from collections.abc import Callable

from app.schemas import SignalDTO


class ABCScreener(ABC):
    """Абстракция для создания скринеров."""

    def __init__(self, callback: Callable[[SignalDTO], None], *args, **kwargs) -> None:
        """Инициализация скринера с обратным вызовом и дополнительными аргументами.

        Parameters:
            callback (Callable[[SignalDTO], None]): Функция обратного вызова для обработки сигнала.
            *args: Дополнительные позиционные аргументы.
            **kwargs: Дополнительные именованные аргументы.
        """
        self._callback = callback

    @abstractmethod
    def run(self) -> None:
        """Абстрактный метод для запуска скринера."""
        pass
