from typing import Dict
from backend.app.strategy.base import StockStrategy
from backend.app.strategy.vacuum_strategy import VacuumStrategy

_REGISTRY: Dict[str, StockStrategy] = {}

def register_strategy(strategy: StockStrategy):
    _REGISTRY[strategy.name] = strategy

def get_strategy(name: str) -> StockStrategy | None:
    return _REGISTRY.get(name)

def get_all_strategies() -> Dict[str, StockStrategy]:
    return dict(_REGISTRY)

# Register default strategies
from backend.app.strategy.sniper_strategy import SniperStrategy

register_strategy(VacuumStrategy())
register_strategy(SniperStrategy())

