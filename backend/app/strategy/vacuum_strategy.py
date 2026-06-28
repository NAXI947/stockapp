from math import sqrt
from typing import Any, Dict, List
from backend.app.strategy.base import StockStrategy, StrategyResult
from backend.app.strategy.indicators import adjusted_moving_average, as_float, has_st_risk, latest_adjustment_factor

class VacuumStrategy(StockStrategy):
    """
    阻力最小爆发模型 v1.2 (Minimum Resistance Breakout Model)
    包含全套强健容错机制的修订版
    """

    @property
    def name(self) -> str:
        return "vacuum_strategy_v1_2"

    @property
    def expected_fields(self) -> List[str]:
        return [
            'ma5', 'ma10', 'ma20', 'ma60', 'upper_space', 'vol_score',
            'is_limit_up', 'limit_up_20d', 'bull_trend',
            'final_score',
            'trend_baseline', 'chip_vacuum', 'kline_body', 
            'liquidity_base', 'safety_margin', 'top_list_3d',
            'st_risk', 'rejected', 'reject_reason'
        ]

    # ================= 强健的工具方法 =================
    
    def _get_float(self, row: Any, key: str, default: float = None) -> float | None:
        """安全获取浮点数，彻底根除 TypeError 和 Decimal 比较崩溃"""
        return as_float(row, key, default)

    def _get_latest_adj_factor(self, series: List[Dict[str, Any]], index: int) -> float | None:
        """安全获取复权因子：如果当日缺失，向前回溯寻找最近的有效值"""
        return latest_adjustment_factor(series, index)

    def _compute_adjusted_ma(self, series: List[Dict[str, Any]], index: int, window: int) -> float | None:
        """计算复权均线（带复权因子回落容错）"""
        return adjusted_moving_average(series, index, window)

    def _compute_upper_space(self, series: List[Dict[str, Any]], index: int) -> float | None:
        """计算上方空间：现价距离近250日复权最高点的百分比"""
        current_close = self._get_float(series[index], 'close')
        current_adj = self._get_latest_adj_factor(series, index)
        if current_close is None or current_close <= 0 or not current_adj:
            return None

        lookback_start = max(0, index - 249)
        adjusted_highs: List[float] = []
        for item in series[lookback_start : index + 1]:
            high = self._get_float(item, 'high')
            if high is None or high <= 0:
                continue
            adj_factor = self._get_float(item, 'adj_factor') or current_adj
            adjusted_highs.append(high * adj_factor / current_adj)

        if not adjusted_highs:
            return None

        highest_price = max(adjusted_highs)
        if highest_price <= 0:
            return None
        return round(max(highest_price / current_close - 1.0, 0.0) * 100.0, 6)

    def _compute_vol_score(self, series: List[Dict[str, Any]], index: int, window: int = 20) -> float | None:
        """计算成交量稳定性得分：综合近期量能波动率与当日偏离度，范围0-100"""
        lookback_start = max(0, index - window + 1)
        volumes = [
            self._get_float(item, 'vol')
            for item in series[lookback_start : index + 1]
        ]
        clean_volumes = [float(v) for v in volumes if v is not None and v > 0]
        if len(clean_volumes) < min(window, 10):
            return None

        mean_volume = sum(clean_volumes) / len(clean_volumes)
        if mean_volume <= 0:
            return None

        variance = sum((v - mean_volume) ** 2 for v in clean_volumes) / len(clean_volumes)
        std_volume = sqrt(variance)
        coeff_var = std_volume / mean_volume
        latest_volume = clean_volumes[-1]
        latest_deviation = abs(latest_volume - mean_volume) / mean_volume

        stability = max(0.0, 1.0 - coeff_var)
        consistency = max(0.0, 1.0 - latest_deviation)
        score = (stability * 0.7 + consistency * 0.3) * 100.0
        return round(min(max(score, 0.0), 100.0), 6)

    def _calculate_chip_vacuum_score(self, series: List[Dict[str, Any]], index: int) -> int:
        """计算筹码真空度得分（修复了提前访问未强转 float 的 Bug）"""
        current_close = self._get_float(series[index], 'close')
        if current_close is None or current_close <= 0:
            return 0
        
        current_adj = self._get_latest_adj_factor(series, index)
        if not current_adj:
            return 0
            
        upper_price = current_close * 1.10
        lookback_start = max(0, index - 59)
        total_volume = 0.0
        upper_volume = 0.0
        
        for i in range(lookback_start, index + 1):
            high = self._get_float(series[i], 'high')
            vol = self._get_float(series[i], 'vol')
            adj = self._get_float(series[i], 'adj_factor') or current_adj
            
            if high is None or vol is None or vol <= 0:
                continue
            
            total_volume += vol
            adj_high = high * adj / current_adj
            
            if adj_high >= upper_price:
                upper_volume += vol * 0.3
        
        if total_volume <= 0:
            return 0
            
        upper_ratio = upper_volume / total_volume
        if upper_ratio <= 0.05: return 15
        elif upper_ratio <= 0.15: return 12
        elif upper_ratio <= 0.30: return 8
        elif upper_ratio <= 0.50: return 4
        else: return 0

    def _check_st_risk(self, name: str | None) -> bool:
        return has_st_risk(name)

    # ================= 核心策略引擎 =================
    
    def calculate(self, series: List[Dict[str, Any]], target_index: int,
                  float_risk: int, top_list_data: List[Dict] = None,
                  stock_name: str = None, weekly_series: List[Dict[str, Any]] = None,
                  block_trade_data: List[Dict[str, Any]] = None) -> StrategyResult | None:
        
        row = series[target_index]
        close = self._get_float(row, 'close')
        
        ma5 = self._compute_adjusted_ma(series, target_index, 5)
        ma10 = self._compute_adjusted_ma(series, target_index, 10)
        ma20 = self._compute_adjusted_ma(series, target_index, 20)
        ma60 = self._compute_adjusted_ma(series, target_index, 60)
        upper_space = self._compute_upper_space(series, target_index)
        vol_score = self._compute_vol_score(series, target_index)
        
        # ========== 1. 硬性否决 ==========
        st_risk = self._check_st_risk(stock_name)
        if st_risk:
            return StrategyResult(score=0, extra_fields={
                'final_score': 0, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
                'upper_space': upper_space, 'vol_score': vol_score,
                'is_limit_up': 0, 'limit_up_20d': 0, 'bull_trend': 0,
                'winner_rate': 0, 'top_list_3d': 0,
                'trend_baseline': 0, 'chip_vacuum': 0, 'kline_body': 0, 
                'liquidity_base': 0, 'safety_margin': 0,
                'st_risk': 1, 'rejected': 1, 'reject_reason': 'ST'
            })
            
        if len(series) < 60:
            return StrategyResult(score=0, extra_fields={
                'final_score': 0, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
                'upper_space': upper_space, 'vol_score': vol_score,
                'is_limit_up': 0, 'limit_up_20d': 0, 'bull_trend': 0,
                'winner_rate': 0, 'top_list_3d': 0,
                'trend_baseline': 0, 'chip_vacuum': 0, 'kline_body': 0, 
                'liquidity_base': 0, 'safety_margin': 0,
                'st_risk': 0, 'rejected': 1, 'reject_reason': 'data'
            })
        # ========== 2. 基础评分 (满分60) ==========
        
        # 2.1 趋势基线
        trend_baseline = 1 if (ma60 and close and close > ma60) else 0
        trend_score = trend_baseline * 15
        
        # 2.2 筹码真空
        chip_vacuum_score = self._calculate_chip_vacuum_score(series, target_index)
        chip_vacuum = 1 if chip_vacuum_score >= 8 else 0
        
        # 2.3 K线实体
        kline_body_score, kline_body = 0, 0
        low = self._get_float(row, 'low')
        high = self._get_float(row, 'high')
        pct_chg = self._get_float(row, 'pct_chg')
        
        if close is not None and low is not None and high is not None:
            if high > low:
                body_ratio = (close - low) / (high - low)
                if body_ratio >= 0.7: kline_body_score = 10
                elif body_ratio >= 0.5: kline_body_score = 7
                elif body_ratio >= 0.3: kline_body_score = 4
                if body_ratio >= 0.3: kline_body = 1
            elif high == low and pct_chg and pct_chg > 0:
                kline_body_score, kline_body = 10, 1
                
        # 2.4 量能活跃度 (解耦计算，防止一损俱损)
        vr = self._get_float(row, 'volume_ratio')
        tr = self._get_float(row, 'turnover_rate')
        vr_score, tr_score = 0, 0
        
        if vr:
            if vr >= 2.0: vr_score = 5
            elif vr >= 1.5: vr_score = 4
            elif vr >= 1.0: vr_score = 2
        if tr:
            if tr >= 3.0: tr_score = 5
            elif tr >= 1.5: tr_score = 4
            elif tr >= 0.5: tr_score = 2
            
        liquidity_score = vr_score + tr_score
        liquidity_base = 1 if liquidity_score >= 4 else 0
        
        # 2.5 安全边际 (修复为区间判定，防止暴跌股得满分)
        safety_score, safety_margin = 0, 0
        if ma20 and close and ma20 > 0:
            dev = close / ma20
            if 0.95 <= dev <= 1.10: # 在均线附近震荡或刚起飞
                safety_score, safety_margin = 10, 1
            elif 0.90 <= dev <= 1.20:
                safety_score, safety_margin = 6, 1
            elif 0.85 <= dev <= 1.30:
                safety_score, safety_margin = 3, 1
                
        base_score = trend_score + chip_vacuum_score + kline_body_score + liquidity_score + safety_score
        
        # ========== 3. 爆发动能加分 (满分55) ==========
        is_limit_up = 1 if (pct_chg and pct_chg >= 9.5) else 0
        
        bull_trend = 1 if (ma5 and ma20 and ma60 and close and ma5 > ma20 > ma60 and close > ma5) else 0
        
        limit_up_20d = 0
        for i in range(max(0, target_index - 19), target_index + 1):
            history_pct = self._get_float(series[i], 'pct_chg')
            if history_pct and history_pct >= 9.5:
                limit_up_20d = 1
                break
                
        amount = self._get_float(row, 'amount')
        vol = self._get_float(row, 'vol')
        
        winner_rate = self._get_float(row, 'winner_rate')
        winner_score = 1 if (winner_rate and winner_rate >= 80) else 0
        
        top_list_3d = 0
        if top_list_data:
            try:
                recent_net = sum(float(item.get('net', 0)) for item in top_list_data if item.get('net') is not None)
                if recent_net > 0: top_list_3d = 1
            except (ValueError, TypeError):
                pass
                
        momentum_score = (
            is_limit_up * 15 + bull_trend * 10 + limit_up_20d * 10 + 
            winner_score * 5 + top_list_3d * 5
        )
        
        # ========== 4. 风险惩罚与结转 ==========
        risk_penalty = 20 if float_risk else 0
        final_score = max(base_score + momentum_score - risk_penalty, 0)
        
        # ========== 5. 拒绝判定 ==========
        reject_reasons = []
        if not trend_baseline: reject_reasons.append('trend')
        if chip_vacuum_score == 0: reject_reasons.append('chip')
        if kline_body_score == 0: reject_reasons.append('body')
        if liquidity_score == 0: reject_reasons.append('liquidity')
        if safety_score == 0: reject_reasons.append('margin')
        
        rejected = 1 if base_score < 15 else 0
        reject_reason = '|'.join(reject_reasons) if rejected else ''

        return StrategyResult(
            score=final_score, 
            extra_fields={
                'final_score': final_score, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
                'upper_space': upper_space, 'vol_score': vol_score,
                'is_limit_up': is_limit_up, 'limit_up_20d': limit_up_20d, 
                'bull_trend': bull_trend,
                'winner_rate': winner_rate, 'top_list_3d': top_list_3d,
                'trend_baseline': trend_baseline, 'chip_vacuum': chip_vacuum,
                'kline_body': kline_body, 'liquidity_base': liquidity_base,
                'safety_margin': safety_margin, 'st_risk': 0,
                'rejected': rejected, 'reject_reason': reject_reason
            }
        )
