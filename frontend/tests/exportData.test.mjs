import assert from 'node:assert/strict'

import {
  buildPicksCsv,
  buildPicksExportPayload,
  getPicksExportFilename,
} from '../src/utils/picksExport.js'

const rows = [
  {
    ts_code: '000001.SZ',
    name: '平安银行',
    industry: '银行',
    concept_text: '金融,权重',
    pct_chg: 1.234,
    turnover_rate: 2.345,
    volume_ratio: 1.8,
    winner_rate: 66.789,
    final_score: 98,
    rejected: 0,
    trend_baseline: 1,
    chip_vacuum: 1,
    kline_body: 0,
    liquidity_base: 1,
    safety_margin: 0,
    top_list_3d: 1,
    st_risk: 0,
    reject_reason: '',
    trade_date: '20260527',
    expected_logic: '低位放量',
    ambush_add_date: '20260520',
    is_action_triggered: true,
  },
]

const labels = {
  ts_code: '代码',
  name: '名称',
  industry: '行业',
  concept_text: '概念',
  pct_chg: '涨跌幅',
  turnover_rate: '换手率',
  volume_ratio: '量比',
  winner_rate: '胜率',
  final_score: '策略分',
  rejected: '准入',
  trend_baseline: '趋势基线',
  chip_vacuum: '筹码真空',
  kline_body: 'K线实体',
  liquidity_base: '量能活跃',
  safety_margin: '安全边际',
  top_list_3d: '三日榜',
  st_risk: 'ST风险',
  reject_reason: '未通过原因',
  trade_date: '交易日',
  expected_logic: '预期逻辑',
  ambush_add_date: '埋伏日期',
  is_action_triggered: '异动触发',
}

function label(key) {
  return labels[key] || key
}

function rejectLabel(reason) {
  return reason || ''
}

assert.equal(getPicksExportFilename('json', '20260527', 'normal'), 'picks_breakout_20260527.json')
assert.equal(getPicksExportFilename('csv', '20260527', 'ambush'), 'picks_ambush_20260527.csv')

const breakoutPayload = buildPicksExportPayload({
  rows,
  mode: 'normal',
  tradeDate: '20260527',
  passed: 1,
})
assert.equal(breakoutPayload.strategy_name, '阻力最小爆发模型')
assert.equal(breakoutPayload.total, 1)
assert.equal(breakoutPayload.passed, 1)

const ambushPayload = buildPicksExportPayload({
  rows,
  mode: 'ambush',
  tradeDate: '20260527',
  passed: 1,
})
assert.equal(ambushPayload.strategy_name, '预期埋伏池')
assert.equal(ambushPayload.data[0].expected_logic, '低位放量')

const csv = buildPicksCsv({
  rows,
  mode: 'ambush',
  tradeDate: '20260527',
  getStrategyFieldLabel: label,
  getRejectReasonLabel: rejectLabel,
})
assert.match(csv, /^代码,名称,行业/)
assert.match(csv, /"金融,权重"/)
assert.match(csv, /低位放量/)
assert.match(csv, /是/)
