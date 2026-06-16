from abc import ABC, abstractmethod
from typing import Any, Dict, List

class StrategyResult:
    def __init__(self, score: int, extra_fields: Dict[str, Any] = None):
        self.score = score
        self.extra_fields = extra_fields or {}

class StockStrategy(ABC):
    """
    Base class for all stock strategies.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique name of the strategy."""
        pass
        
    @property
    @abstractmethod
    def expected_fields(self) -> List[str]:
        """Fields this strategy expects to output to the database."""
        pass

    @abstractmethod
    def calculate(
        self,
        series: List[Dict[str, Any]],
        target_index: int,
        float_risk: int,
        top_list_data: List[Dict] = None,
        stock_name: str = None,
    ) -> StrategyResult | None:
        """
        Calculate strategy score for a specific day in the time series.
        
        Args:
            series: Historical daily data sorted by trade_date ascending.
            target_index: The index in `series` representing the day to evaluate.
            float_risk: Whether there's an upcoming float risk (1 for yes, 0 for no).
            top_list_data: Top list net buy records in recent days.
            stock_name: The stock's chinese name for ST risk checks.
            
        Returns:
            StrategyResult if successful, None if calculation cannot be performed (e.g. insufficient data).
        """
        pass
