__all__ = ["ABCTradebot", "ABCExchangeInfo"]

import inspect
from abc import ABC, abstractmethod
from threading import Thread

from app.schemas import SignalDTO


class ABCTradebot(ABC):
    """Абстракция для трейдботов, требующая сигнатуру __init__(api_key, api_secret, ...)"""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        init = cls.__init__
        sig = inspect.signature(init)
        params = list(sig.parameters.values())

        if len(params) < 3:
            raise TypeError(
                f"{cls.__name__}.__init__ must accept at least (self, api_key, api_secret)"
            )

        if params[1].name != "api_key" or params[2].name != "api_secret":
            raise TypeError(
                f"{cls.__name__}.__init__ must have 'api_key' and 'api_secret' as the first two arguments after 'self'"
            )

    def __init__(self, api_key: str, api_secret: str, *args, **kwargs):
        raise NotImplementedError("Do not instantiate ABCTradebot directly")

    @abstractmethod
    def process_signal(self, signal: SignalDTO) -> None:
        """Обработка сигнала (открытие позиции, выставление тп и сл)."""
        pass


class ABCExchangeInfo(ABC, Thread):
    """
    Класс, который внутри себя обновляет информацию о том, как надо округлять
    цены монет и их количество в ордерах на разных биржах.
    """

    def __init__(self):
        Thread.__init__(self, daemon=True)

    @abstractmethod
    def run(self) -> None:
        pass

    @abstractmethod
    def round_price(self, symbol: str, price: float) -> float:
        pass

    @abstractmethod
    def round_quantity(self, symbol: str, quiantity: float) -> float:
        pass
