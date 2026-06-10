const EXPORT_MODES = {
  normal: {
    filename: 'picks_breakout',
    strategyName: '阻力最小爆发模型',
    strategyVersion: '1.2',
  },
  ambush: {
    filename: 'picks_ambush',
    strategyName: '预期埋伏池',
    strategyVersion: '1.2',
  },
}

function getModeConfig(mode) {
  return EXPORT_MODES[mode] || EXPORT_MODES.normal
}

function formatNumber(value, digits = 2) {
  return value != null ? Number(value).toFixed(digits) : ''
}

function yesNo(value) {
  return value ? '是' : '否'
}

function passStatus(stock) {
  return stock.rejected ? '未通过' : '通过'
}

function escapeCSV(value) {
  const str = String(value ?? '')
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`
  }
  return str
}

export function getPicksExportFilename(ext, tradeDate, mode = 'normal') {
  const date = tradeDate || new Date().toISOString().slice(0, 10)
  return `${getModeConfig(mode).filename}_${date}.${ext}`
}

export function buildPicksExportPayload({ rows, mode = 'normal', tradeDate = '', passed = 0 }) {
  const config = getModeConfig(mode)
  return {
    export_time: new Date().toISOString(),
    trade_date: tradeDate,
    strategy_version: config.strategyVersion,
    strategy_name: config.strategyName,
    total: rows.length,
    passed,
    data: rows,
  }
}

export function buildPicksCsv({
  rows,
  mode = 'normal',
  tradeDate = '',
  getStrategyFieldLabel,
  getRejectReasonLabel,
}) {
  const baseHeaders = [
    getStrategyFieldLabel('ts_code'),
    getStrategyFieldLabel('name'),
    getStrategyFieldLabel('industry'),
    getStrategyFieldLabel('concept_text'),
    `${getStrategyFieldLabel('pct_chg')}(%)`,
    `${getStrategyFieldLabel('turnover_rate')}(%)`,
    getStrategyFieldLabel('volume_ratio'),
    `${getStrategyFieldLabel('winner_rate')}(%)`,
    getStrategyFieldLabel('final_score'),
    getStrategyFieldLabel('rejected'),
    getStrategyFieldLabel('trend_baseline'),
    getStrategyFieldLabel('chip_vacuum'),
    getStrategyFieldLabel('kline_body'),
    getStrategyFieldLabel('liquidity_base'),
    getStrategyFieldLabel('safety_margin'),
    getStrategyFieldLabel('top_list_3d'),
    getStrategyFieldLabel('st_risk'),
    getStrategyFieldLabel('reject_reason'),
    getStrategyFieldLabel('trade_date'),
  ]

  const ambushHeaders = mode === 'ambush'
    ? [
        getStrategyFieldLabel('expected_logic'),
        getStrategyFieldLabel('ambush_add_date'),
        getStrategyFieldLabel('is_action_triggered'),
      ]
    : []

  const rowsData = rows.map(stock => {
    const baseRow = [
      stock.ts_code,
      stock.name || '',
      stock.industry || '',
      stock.concept_text || '',
      formatNumber(stock.pct_chg),
      formatNumber(stock.turnover_rate),
      formatNumber(stock.volume_ratio),
      formatNumber(stock.winner_rate),
      stock.final_score != null ? stock.final_score : '',
      passStatus(stock),
      yesNo(stock.trend_baseline),
      yesNo(stock.chip_vacuum),
      yesNo(stock.kline_body),
      yesNo(stock.liquidity_base),
      yesNo(stock.safety_margin),
      yesNo(stock.top_list_3d),
      yesNo(stock.st_risk),
      stock.rejected ? getRejectReasonLabel(stock.reject_reason) : '',
      stock.trade_date || tradeDate || '',
    ]

    if (mode !== 'ambush') return baseRow
    return [
      ...baseRow,
      stock.expected_logic || '',
      stock.ambush_add_date || '',
      yesNo(stock.is_action_triggered),
    ]
  })

  return [
    [...baseHeaders, ...ambushHeaders].map(escapeCSV).join(','),
    ...rowsData.map(row => row.map(escapeCSV).join(',')),
  ].join('\n')
}
