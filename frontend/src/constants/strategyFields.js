export const STRATEGY_FIELD_LABELS = {
  ts_code: '股票代码',
  name: '股票名称',
  industry: '行业',
  concept_text: '概念',
  trade_date: '交易日期',
  pct_chg: '涨跌幅',
  turnover_rate: '换手率',
  volume_ratio: '量比',
  winner_rate: '获利盘比例',
  ma5: 'MA5',
  ma20: 'MA20',
  ma60: 'MA60',
  upper_space: '上方空间',
  vol_score: '成交量稳定性得分',
  is_limit_up: '当日涨停',
  limit_up_20d: '近20日涨停记忆',
  bull_trend: '多头趋势',
  float_risk_7d: '7日解禁风险',
  final_score: '策略分',
  trend_baseline: '趋势基线',
  chip_vacuum: '筹码真空',
  kline_body: 'K线实体',
  liquidity_base: '量能活跃',
  safety_margin: '安全边际',
  top_list_3d: '近3日龙虎榜净流入',
  st_risk: 'ST风险',
  rejected: '准入结果',
  reject_reason: '未通过原因',
  is_action_triggered: '异动触发',
  expected_logic: '预期逻辑',
  ambush_add_date: '埋伏日期',
}

export const REJECT_REASON_LABELS = {
  trend: '趋势基线不足',
  chip: '筹码真空未达标',
  body: 'K线实体不足',
  liquidity: '量能活跃不足',
  margin: '安全边际不足',
  data: '历史数据不足',
  ST: 'ST风险',
}

export function getStrategyFieldLabel(key) {
  return STRATEGY_FIELD_LABELS[key] || key
}

export function getRejectReasonLabel(reason) {
  if (!reason) return ''
  return reason
    .split('|')
    .map(part => REJECT_REASON_LABELS[part] || part)
    .join('、')
}
