from typing import Any, Dict, List
from backend.app.strategy.base import StockStrategy, StrategyResult
from backend.app.strategy.chaos import CHAOS_REJECTION_THRESHOLD, compute_chaos_score
from backend.app.strategy.indicators import adjusted_moving_average, as_float, has_st_risk, latest_adjustment_factor

class SniperStrategy(StockStrategy):
    """
    极简狙击手独立策略 v1.0 (Minimalist Sniper Strategy)
    """

    @property
    def name(self) -> str:
        return "sniper_strategy_v1"

    @property
    def expected_fields(self) -> List[str]:
        return [
            'sniper_score', 'sniper_rejected', 'sniper_reject_reason',
            'chaos_index_val', 'score_chaos',
            's_holder_score', 's_chip_vacuum_score', 's_ma_state_score',
            's_safety_margin_score', 's_macd_weekly_score',
            's_low_volume_score', 's_golden_pit_score', 's_ignition_score',
            's_top_list_score', 's_news_score',
            's_base_total', 's_dynamic_total'
        ]

    def _get_float(self, row: Any, key: str, default: float = None) -> float | None:
        return as_float(row, key, default)

    def _get_latest_adj_factor(self, series: List[Dict[str, Any]], index: int) -> float | None:
        return latest_adjustment_factor(series, index)

    def _compute_adjusted_ma(self, series: List[Dict[str, Any]], index: int, window: int) -> float | None:
        return adjusted_moving_average(series, index, window)

    def _calculate_weekly_macd(self, weekly_series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        计算周线 MACD 指标 (DIF, DEA, Hist)
        """
        if not weekly_series:
            return []
        
        # Extract closing prices
        closes = []
        for item in weekly_series:
            c = self._get_float(item, 'close')
            closes.append(c if c is not None else 0.0)
            
        n_weeks = len(closes)
        if n_weeks < 26:
            return []
            
        # EMA helper
        def get_ema(data: List[float], period: int) -> List[float]:
            ema = [0.0] * len(data)
            if not data:
                return ema
            ema[0] = data[0]
            multiplier = 2.0 / (period + 1)
            for i in range(1, len(data)):
                ema[i] = data[i] * multiplier + ema[i-1] * (1.0 - multiplier)
            return ema

        ema12 = get_ema(closes, 12)
        ema26 = get_ema(closes, 26)
        
        dif = [ema12[i] - ema26[i] for i in range(n_weeks)]
        dea = get_ema(dif, 9)
        hist = [2 * (dif[i] - dea[i]) for i in range(n_weeks)]
        
        result = []
        for i in range(n_weeks):
            result.append({
                'trade_date': weekly_series[i]['trade_date'],
                'dif': dif[i],
                'dea': dea[i],
                'hist': hist[i]
            })
        return result

    def _check_st_risk(self, name: str | None) -> bool:
        return has_st_risk(name)

    def _compute_chaos_score(
        self,
        series: List[Dict[str, Any]],
        target_index: int,
        window: int = 20,
    ) -> tuple[float | None, int]:
        """计算量价无序度；需要 20 个摩擦观测和第 20 日前收盘，共 21 行。"""
        result = compute_chaos_score(series, target_index, window)
        return result.value, result.score

    def calculate(
        self,
        series: List[Dict[str, Any]],
        target_index: int,
        float_risk: int,
        top_list_data: List[Dict] = None,
        stock_name: str = None,
        weekly_series: List[Dict[str, Any]] = None,
        block_trade_data: List[Dict[str, Any]] = None,
    ) -> StrategyResult | None:
        row = series[target_index]
        trade_date = row['trade_date']
        close = self._get_float(row, 'close')
        open_p = self._get_float(row, 'open')
        high = self._get_float(row, 'high')
        low = self._get_float(row, 'low')
        pct_chg = self._get_float(row, 'pct_chg')
        turnover_rate = self._get_float(row, 'turnover_rate', 0.0)
        volume_ratio = self._get_float(row, 'volume_ratio', 0.0)
        chaos_index_val, score_chaos = self._compute_chaos_score(series, target_index)

        # MAs
        ma5 = self._compute_adjusted_ma(series, target_index, 5)
        ma10 = self._compute_adjusted_ma(series, target_index, 10)
        ma20 = self._compute_adjusted_ma(series, target_index, 20)
        ma60 = self._compute_adjusted_ma(series, target_index, 60)

        # 🛑 1. 一票否决检查
        rejected = 0
        reject_reason = ""

        # ST Check
        if self._check_st_risk(stock_name):
            rejected = 1
            reject_reason = "ST"

        # 均线死叉向下且加速发散（破位）
        # MA5 < MA10 < MA20 < MA60 且 MA5 偏离 MA20 > 5% (i.e. MA5 / MA20 < 0.95)
        if not rejected and ma5 and ma10 and ma20 and ma60:
            if ma5 < ma10 < ma20 < ma60 and (ma5 / ma20) < 0.95:
                rejected = 1
                reject_reason = "MA_BREAK"

        # MACD周线高位死叉且绿柱放大
        # We need weekly series and need to align it with target trade_date
        weekly_macd = []
        if not rejected and weekly_series:
            # Filter weekly series up to target trade_date
            sub_weekly = [w for w in weekly_series if w['trade_date'] <= trade_date]
            weekly_macd = self._calculate_weekly_macd(sub_weekly)
            if len(weekly_macd) >= 2:
                latest_w = weekly_macd[-1]
                prev_w = weekly_macd[-2]
                # High-level dead cross: DIF > 0, DIF < DEA, and previous hist was positive or hist is becoming more negative (green column enlarging)
                if latest_w['dif'] > 0 and latest_w['dif'] < latest_w['dea'] and latest_w['hist'] < 0:
                    if latest_w['hist'] < prev_w['hist']: # More negative (green column enlarging)
                        rejected = 1
                        reject_reason = "WEEKLY_MACD_DEAD"

        # 量价无序度达到最高风险档：散户博弈剧烈，触发原 HOLDER_SURGE 拒绝码。
        if not rejected and chaos_index_val is not None and chaos_index_val >= CHAOS_REJECTION_THRESHOLD:
            rejected = 1
            reject_reason = "HOLDER_SURGE"

        # 🧱 2. 静态底座评分 (60分)
        
        # 2.1 主力控盘度（量价无序度，15分）
        # s_holder_score 暂作兼容别名，值与 score_chaos 保持一致。
        s_holder_score = score_chaos

        # 2.2 上方筹码真空度 (10分)
        s_chip_vacuum_score = 0
        if close and close > 0:
            current_adj = self._get_latest_adj_factor(series, target_index)
            if current_adj:
                upper_price = close * 1.10
                lookback_start = max(0, target_index - 59)
                total_volume = 0.0
                upper_volume = 0.0
                for i in range(lookback_start, target_index + 1):
                    h_val = self._get_float(series[i], 'high')
                    vol_val = self._get_float(series[i], 'vol')
                    adj_val = self._get_float(series[i], 'adj_factor') or current_adj
                    if h_val is None or vol_val is None or vol_val <= 0:
                        continue
                    total_volume += vol_val
                    adj_high = h_val * adj_val / current_adj
                    if adj_high >= upper_price:
                        upper_volume += vol_val * 0.3
                if total_volume > 0:
                    upper_ratio = upper_volume / total_volume
                    if upper_ratio <= 0.05:
                        s_chip_vacuum_score = 10
                    elif upper_ratio <= 0.15:
                        s_chip_vacuum_score = 7
                    elif upper_ratio <= 0.30:
                        s_chip_vacuum_score = 4
                    else:
                        s_chip_vacuum_score = 0

        # 2.3 均线状态 (10分)
        s_ma_state_score = 0
        if ma5 and ma10 and ma20 and ma60:
            mas = [ma5, ma10, ma20, ma60]
            max_ma = max(mas)
            min_ma = min(mas)
            # 粘合度
            if min_ma > 0 and (max_ma - min_ma) / min_ma <= 0.03:
                s_ma_state_score = 10
            elif ma5 > ma10 > ma20 > ma60:
                s_ma_state_score = 7
            elif close > ma20 and ma20 > ma60:
                s_ma_state_score = 4

        # 2.4 安全边际(MA20偏离) (10分)
        s_safety_margin_score = 0
        if ma20 and close and ma20 > 0:
            dev = close / ma20
            if 0.95 <= dev <= 1.10:
                s_safety_margin_score = 10
            elif 0.90 <= dev <= 1.20:
                s_safety_margin_score = 6
            elif dev < 0.85 or dev > 1.30:
                s_safety_margin_score = 0
            else:
                s_safety_margin_score = 3

        # 2.5 MACD周线 (15分)
        s_macd_weekly_score = 5 # Default zero-axis hybrid/no-data fallback
        if weekly_macd:
            latest_w = weekly_macd[-1]
            prev_w = weekly_macd[-2] if len(weekly_macd) >= 2 else None
            dif = latest_w.get('dif', 0.0)
            dea = latest_w.get('dea', 0.0)
            hist = latest_w.get('hist', 0.0)
            prev_hist = prev_w.get('hist', 0.0) if prev_w else 0.0
            
            # Gold cross at zero axis
            is_gold_cross = False
            if prev_w and prev_w.get('dif', 0.0) <= prev_w.get('dea', 0.0) and dif > dea:
                is_gold_cross = True
            
            if is_gold_cross and abs(dif) <= 0.2:
                s_macd_weekly_score = 15
            elif hist > 0 and hist > prev_hist:
                s_macd_weekly_score = 10
            elif abs(dif) <= 0.1 and abs(dea) <= 0.1:
                s_macd_weekly_score = 5
            else:
                s_macd_weekly_score = 0

        # 🔫 3. 动态信号评分 (40分)
        
        # 3.1 极致地量 (8分)
        s_low_volume_score = 0
        if turnover_rate > 0:
            if turnover_rate < 1.5:
                s_low_volume_score = 8
            else:
                # Check if volume is 50% of 20-day average volume
                lookback_start = max(0, target_index - 19)
                vols = [self._get_float(series[i], 'vol', 0.0) for i in range(lookback_start, target_index + 1)]
                clean_vols = [v for v in vols if v > 0]
                if len(clean_vols) >= 5:
                    avg_vol = sum(clean_vols) / len(clean_vols)
                    today_vol = vols[-1]
                    if today_vol > 0 and avg_vol > 0 and today_vol <= 0.5 * avg_vol:
                        s_low_volume_score = 4

        # 3.2 黄金坑/骗线 (10分)
        s_golden_pit_score = 0
        # Check if in previous 1-3 days we broke below MA20 or MA60, and today we rebound with positive day and volume > yesterday
        if target_index >= 3:
            ma20_yesterday = self._compute_adjusted_ma(series, target_index - 1, 20)
            ma60_yesterday = self._compute_adjusted_ma(series, target_index - 1, 60)
            
            broke_support = False
            for offset in range(1, 4):
                idx = target_index - offset
                c_val = self._get_float(series[idx], 'close')
                l_val = self._get_float(series[idx], 'low')
                m20 = self._compute_adjusted_ma(series, idx, 20)
                m60 = self._compute_adjusted_ma(series, idx, 60)
                if c_val and l_val:
                    if (m20 and (c_val < m20 or l_val < m20)) or (m60 and (c_val < m60 or l_val < m60)):
                        broke_support = True
                        break
            
            today_vol = self._get_float(row, 'vol', 0.0)
            yesterday_vol = self._get_float(series[target_index - 1], 'vol', 0.0)
            
            if broke_support and close and open_p and close > open_p:
                if ma20 and close > ma20 and today_vol > yesterday_vol:
                    s_golden_pit_score = 10

        # 3.3 放量点火首阳 (10分)
        s_ignition_score = 0
        if close and open_p and high and low and high > low:
            body_ratio = (close - open_p) / (high - low)
            upper_shadow = (high - max(close, open_p)) / (high - low)
            
            if volume_ratio > 2.0 and close > open_p and body_ratio >= 0.6:
                s_ignition_score = 10
            elif volume_ratio > 1.5 and upper_shadow >= 0.5:
                s_ignition_score = 5

        # 3.4 龙虎榜/大宗 (7分)
        s_top_list_score = 0
        # Check Top List
        top_list_score = 0
        if top_list_data:
            # We filter top list to within last 3 days of target date
            for item in top_list_data:
                item_date = item.get('trade_date', '')
                if item_date and item_date <= trade_date:
                    # Parse days diff if possible (assuming sorted/recent)
                    net_val = self._get_float(item, 'net', 0.0)
                    reason_str = str(item.get('reason', '')).upper()
                    if net_val > 0:
                        if "机构" in reason_str or "机构专用" in reason_str:
                            top_list_score = max(top_list_score, 7)
                        else:
                            top_list_score = max(top_list_score, 4)
                            
        # Check Block Trade
        block_score = 0
        if block_trade_data:
            today_blocks = [b for b in block_trade_data if b.get('trade_date', '') == trade_date]
            for b in today_blocks:
                premium = self._get_float(b, 'premium', 0.0)
                if premium > 0:
                    block_score = 4
                    break
        
        s_top_list_score = max(top_list_score, block_score)

        # 3.5 消息面共振 (5分)
        s_news_score = 0

        # Sum up
        s_base_total = score_chaos + s_chip_vacuum_score + s_ma_state_score + s_safety_margin_score + s_macd_weekly_score
        s_dynamic_total = s_low_volume_score + s_golden_pit_score + s_ignition_score + s_top_list_score + s_news_score
        
        sniper_score = s_base_total + s_dynamic_total if not rejected else 0

        extra_fields = {
            'sniper_score': sniper_score,
            'sniper_rejected': rejected,
            'sniper_reject_reason': reject_reason,
            'chaos_index_val': chaos_index_val,
            'score_chaos': score_chaos,
            's_holder_score': s_holder_score,
            's_chip_vacuum_score': s_chip_vacuum_score,
            's_ma_state_score': s_ma_state_score,
            's_safety_margin_score': s_safety_margin_score,
            's_macd_weekly_score': s_macd_weekly_score,
            's_low_volume_score': s_low_volume_score,
            's_golden_pit_score': s_golden_pit_score,
            's_ignition_score': s_ignition_score,
            's_top_list_score': s_top_list_score,
            's_news_score': s_news_score,
            's_base_total': s_base_total,
            's_dynamic_total': s_dynamic_total,
            'final_score': sniper_score # For compatibility with backend queries expecting final_score
        }

        return StrategyResult(score=sniper_score, extra_fields=extra_fields)
