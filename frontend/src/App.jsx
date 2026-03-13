import { useState, useEffect, useCallback } from 'react'
import { useWebSocket, usePolling } from './hooks.js'

const WS_URL = `ws://${window.location.hostname}:8000/ws`
const API_URL = `http://${window.location.hostname}:8000`

const fmt = (n, d = 2) => {
  if (n == null) return '—'
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
}
const pf = (p) => p >= 1000 ? fmt(p, 2) : p >= 1 ? fmt(p, 4) : fmt(p, 6)

function Badge({ children, color }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 6px', borderRadius: 3, fontSize: 9,
      fontWeight: 600, letterSpacing: '.03em',
      background: `${color}18`, color, border: `1px solid ${color}30`,
    }}>{children}</span>
  )
}

function LiveDot() {
  return <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#00E676', boxShadow: '0 0 6px #00E676', animation: 'pulse 2s ease-in-out infinite' }} />
}

function OrderRow({ order }) {
  const colors = { '66%': '#EF9F27', '44%': '#D4537E', '10%': '#E24B4A' }
  const c = colors[order.level] || '#888'
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '50px 1fr 70px 70px', padding: '3px 0', fontSize: 10, alignItems: 'center', opacity: order.status === 'cancelled' ? 0.25 : order.status === 'filled' ? 1 : 0.5 }}>
      <Badge color={c}>{order.level}</Badge>
      <span style={{ color: 'rgba(255,255,255,.5)' }}>${pf(order.price)}</span>
      <span style={{ textAlign: 'right', color: 'rgba(255,255,255,.35)' }}>${fmt(order.capital, 0)}</span>
      <span style={{ textAlign: 'right' }}>
        {order.status === 'filled' ? <Badge color="#00E676">FILLED</Badge> :
         order.status === 'cancelled' ? <Badge color="#E24B4A">CANCEL</Badge> :
         <Badge color="rgba(255,255,255,.25)">LIMIT</Badge>}
      </span>
    </div>
  )
}

export default function App() {
  const { state: wsState, connected, send } = useWebSocket(WS_URL)
  const pollState = usePolling(`${API_URL}/api/state`, 3000)
  const [tab, setTab] = useState('trades')
  const [expandedTrade, setExpandedTrade] = useState(null)

  const state = wsState || pollState

  const demoMode = state?.demo_mode ?? true
  const pairs = state?.pairs || []
  const prices = state?.prices || {}
  const posData = state?.positions || {}
  const sentData = state?.sentiment || {}
  const activeTrades = posData.active_trades || []
  const closedTrades = posData.closed_trades || []
  const alerts = posData.alerts || []
  const realizedPnl = posData.realized_pnl || 0
  const gateMode = sentData.gate_mode || 'neutral'
  const aggSentiment = sentData.aggregate_sentiment || 0
  const gateColor = gateMode === 'bullish' ? '#00E676' : gateMode === 'bearish' ? '#FF3D71' : '#FFB547'

  // Calculate unrealized P&L
  let unrealizedPnl = 0
  for (const trade of activeTrades) {
    const filled = (trade.orders || []).filter(o => o.status === 'filled')
    if (filled.length === 0) continue
    const cp = prices[trade.symbol] || 0
    const totalUnits = filled.reduce((s, o) => s + o.units, 0)
    const totalCap = filled.reduce((s, o) => s + o.capital, 0)
    unrealizedPnl += cp * totalUnits - totalCap
  }
  const totalPnl = unrealizedPnl + realizedPnl
  const pendingOrders = activeTrades.reduce((s, t) => s + (t.orders || []).filter(o => o.status === 'pending').length, 0)
  const filledOrders = activeTrades.reduce((s, t) => s + (t.orders || []).filter(o => o.status === 'filled').length, 0)

  const toggleDemo = () => send({ type: 'toggle_demo' })
  const setGate = (mode) => send({ type: 'set_gate', mode })

  return (
    <div style={{ minHeight: '100vh' }}>
      {/* HEADER */}
      <div style={{ padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 26, height: 26, borderRadius: 5, background: 'linear-gradient(135deg,#00E676,#448AFF)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, color: '#08090C' }}>S</div>
          <div>
            <span style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>SENTINEL</span>
            <span style={{ fontSize: 8, color: 'rgba(255,255,255,.25)', marginLeft: 8, letterSpacing: '.08em' }}>TRADE ENGINE</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={toggleDemo} style={{
            padding: '4px 12px', borderRadius: 4, border: 'none', cursor: 'pointer',
            fontSize: 9, fontWeight: 700, letterSpacing: '.06em', fontFamily: 'inherit',
            background: demoMode ? 'rgba(255,181,71,.15)' : 'rgba(0,230,118,.15)',
            color: demoMode ? '#FFB547' : '#00E676',
          }}>
            {demoMode ? '◈ DEMO' : '● LIVE'}
          </button>
          <div style={{ display: 'flex', background: 'rgba(255,255,255,.03)', borderRadius: 3, padding: 1 }}>
            {['bullish', 'neutral', 'bearish'].map(m => (
              <button key={m} onClick={() => setGate(m)} style={{
                padding: '3px 8px', fontSize: 8, fontWeight: 600, borderRadius: 2,
                border: 'none', cursor: 'pointer', textTransform: 'uppercase',
                fontFamily: 'inherit', letterSpacing: '.05em',
                background: gateMode === m ? (m === 'bullish' ? '#00E676' : m === 'bearish' ? '#FF3D71' : '#FFB547') : 'transparent',
                color: gateMode === m ? '#08090C' : 'rgba(255,255,255,.25)',
              }}>{m}</button>
            ))}
          </div>
          {connected ? <LiveDot /> : <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#FF3D71', display: 'inline-block' }} />}
        </div>
      </div>

      {/* P&L STRIP */}
      <div style={{ padding: '8px 14px', borderBottom: '1px solid rgba(255,255,255,.04)', display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: 8, background: 'rgba(255,255,255,.01)' }}>
        {[
          { label: 'TOTAL P&L', value: `${totalPnl >= 0 ? '+' : ''}$${fmt(totalPnl)}`, color: totalPnl >= 0 ? '#00E676' : '#FF3D71', big: true },
          { label: 'UNREALIZED', value: `${unrealizedPnl >= 0 ? '+' : ''}$${fmt(unrealizedPnl)}`, color: unrealizedPnl >= 0 ? '#00E676' : '#FF3D71' },
          { label: 'REALIZED', value: `${realizedPnl >= 0 ? '+' : ''}$${fmt(realizedPnl)}`, color: realizedPnl >= 0 ? '#00E676' : '#FF3D71' },
          { label: 'ACTIVE', value: activeTrades.length, color: '#448AFF' },
          { label: 'FILLED/LIMIT', value: `${filledOrders}/${pendingOrders}`, color: '#FFB547' },
          { label: 'SENTIMENT', value: `${aggSentiment > 0 ? '+' : ''}${(aggSentiment * 100).toFixed(0)}%`, color: aggSentiment > 0.2 ? '#00E676' : aggSentiment < -0.2 ? '#FF3D71' : '#FFB547' },
          { label: 'GATE', value: gateMode.toUpperCase(), color: gateColor },
        ].map((m, i) => (
          <div key={i} style={{ background: 'rgba(255,255,255,.02)', borderRadius: 5, padding: '6px 8px', border: '1px solid rgba(255,255,255,.03)' }}>
            <div style={{ fontSize: 7, color: 'rgba(255,255,255,.2)', letterSpacing: '.1em', marginBottom: 2 }}>{m.label}</div>
            <div style={{ fontSize: m.big ? 16 : 13, fontWeight: 700, color: m.color }}>{m.value}</div>
          </div>
        ))}
      </div>

      {/* DEMO BANNER */}
      {demoMode && (
        <div style={{ padding: '5px 14px', background: 'rgba(255,181,71,.06)', borderBottom: '1px solid rgba(255,181,71,.15)', display: 'flex', alignItems: 'center', gap: 8, fontSize: 9, color: '#FFB547' }}>
          <span style={{ fontWeight: 700 }}>◈ DEMO</span>
          <span style={{ color: 'rgba(255,181,71,.6)' }}>Passive price tracking — simulated fills, no real capital</span>
        </div>
      )}

      {/* MAIN LAYOUT */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px' }}>
        {/* LEFT */}
        <div style={{ borderRight: '1px solid rgba(255,255,255,.04)' }}>
          <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,.04)', background: 'rgba(255,255,255,.01)' }}>
            {[
              { id: 'trades', label: 'Active trades', count: activeTrades.length },
              { id: 'pairs', label: 'All pairs', count: pairs.length },
              { id: 'history', label: 'Closed P&L', count: closedTrades.length },
            ].map(t => (
              <button key={t.id} onClick={() => setTab(t.id)} style={{
                padding: '8px 14px', fontSize: 9, fontWeight: 600, border: 'none', cursor: 'pointer',
                fontFamily: 'inherit', letterSpacing: '.04em', background: 'transparent',
                color: tab === t.id ? '#fff' : 'rgba(255,255,255,.25)',
                borderBottom: tab === t.id ? '2px solid #448AFF' : '2px solid transparent',
              }}>
                {t.label} <span style={{ color: 'rgba(255,255,255,.15)', marginLeft: 4 }}>{t.count}</span>
              </button>
            ))}
          </div>

          {/* ACTIVE TRADES */}
          {tab === 'trades' && (
            <div style={{ maxHeight: 450, overflowY: 'auto' }}>
              {activeTrades.length === 0 && <div style={{ padding: 30, textAlign: 'center', color: 'rgba(255,255,255,.15)' }}>No active trades</div>}
              {activeTrades.map(trade => {
                const filled = (trade.orders || []).filter(o => o.status === 'filled')
                const cp = prices[trade.symbol] || 0
                const totalUnits = filled.reduce((s, o) => s + o.units, 0)
                const totalCap = filled.reduce((s, o) => s + o.capital, 0)
                const uPnl = filled.length > 0 ? cp * totalUnits - totalCap : 0
                const uPnlPct = totalCap > 0 ? (uPnl / totalCap) * 100 : 0
                const expanded = expandedTrade === trade.trade_id
                const tpDist = trade.tp_price && cp ? ((trade.tp_price - cp) / cp * 100) : null

                return (
                  <div key={trade.trade_id} style={{ borderBottom: '1px solid rgba(255,255,255,.04)' }}>
                    <div onClick={() => setExpandedTrade(expanded ? null : trade.trade_id)}
                      style={{ padding: '10px 14px', cursor: 'pointer' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {trade.demo && <Badge color="#FFB547">DEMO</Badge>}
                          <span style={{ fontWeight: 700, color: '#fff', fontSize: 12 }}>{trade.symbol.replace('USDT', '')}</span>
                          <Badge color={trade.signal_type?.includes('L') ? '#00E676' : '#FF3D71'}>{trade.signal_type}</Badge>
                          <Badge color={filled.length === 3 ? '#00E676' : filled.length > 0 ? '#FFB547' : 'rgba(255,255,255,.2)'}>
                            {filled.length}/3
                          </Badge>
                        </div>
                        <span style={{ fontSize: 14, fontWeight: 700, color: uPnl >= 0 ? '#00E676' : '#FF3D71' }}>
                          {uPnl >= 0 ? '+' : ''}{fmt(uPnl)} <span style={{ fontSize: 10, opacity: .6 }}>({uPnlPct >= 0 ? '+' : ''}{uPnlPct.toFixed(1)}%)</span>
                        </span>
                      </div>

                      {trade.tp_price && filled.length > 0 && (
                        <div style={{ marginBottom: 4 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                            <span style={{ fontSize: 8, color: 'rgba(255,255,255,.2)' }}>AVG ${pf(trade.avg_entry)} → TP ${pf(trade.tp_price)}</span>
                            <span style={{ fontSize: 8, color: tpDist <= 2 ? '#00E676' : 'rgba(255,255,255,.3)' }}>
                              {tpDist > 0 ? `${tpDist.toFixed(1)}% to TP` : 'TP REACHED'}
                            </span>
                          </div>
                          <div style={{ height: 3, background: 'rgba(255,255,255,.04)', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{
                              height: '100%', borderRadius: 2,
                              width: `${Math.min(100, Math.max(0, (1 - (tpDist || 0) / 20) * 100))}%`,
                              background: `linear-gradient(90deg, #448AFF, ${tpDist <= 5 ? '#00E676' : '#448AFF'})`,
                            }} />
                          </div>
                        </div>
                      )}

                      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                        {(trade.orders || []).map((o, i) => (
                          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                            <div style={{ width: 5, height: 5, borderRadius: '50%', background: o.status === 'filled' ? '#00E676' : o.status === 'cancelled' ? '#E24B4A' : 'rgba(255,255,255,.1)' }} />
                            <span style={{ fontSize: 8, color: o.status === 'filled' ? 'rgba(255,255,255,.4)' : 'rgba(255,255,255,.12)' }}>{o.level}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {expanded && (
                      <div style={{ padding: '0 14px 12px', animation: 'slideIn .2s ease-out' }}>
                        <div style={{ background: 'rgba(255,255,255,.02)', borderRadius: 5, padding: '8px 10px', border: '1px solid rgba(255,255,255,.03)' }}>
                          <div style={{ fontSize: 8, color: 'rgba(255,255,255,.2)', letterSpacing: '.08em', marginBottom: 6 }}>LIMIT ORDERS</div>
                          {(trade.orders || []).map((o, i) => <OrderRow key={i} order={o} />)}
                          <div style={{ borderTop: '1px solid rgba(255,255,255,.04)', marginTop: 6, paddingTop: 6 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                              <span style={{ color: 'rgba(255,255,255,.3)' }}>Avg entry</span>
                              <span style={{ fontWeight: 700, color: '#448AFF' }}>{trade.avg_entry ? `$${pf(trade.avg_entry)}` : '—'}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginTop: 2 }}>
                              <span style={{ color: 'rgba(255,255,255,.3)' }}>TP (+20%)</span>
                              <span style={{ fontWeight: 700, color: '#00E676' }}>{trade.tp_price ? `$${pf(trade.tp_price)}` : '—'}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginTop: 2 }}>
                              <span style={{ color: 'rgba(255,255,255,.3)' }}>Current</span>
                              <span style={{ fontWeight: 700, color: '#fff' }}>${pf(cp)}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* ALL PAIRS */}
          {tab === 'pairs' && (
            <div style={{ maxHeight: 450, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                <thead>
                  <tr style={{ background: 'rgba(255,255,255,.02)' }}>
                    {['Pair', 'Price', '24h', 'Signal', 'Gate'].map((h, i) => (
                      <th key={i} style={{ padding: '6px 10px', textAlign: i === 0 ? 'left' : 'right', fontSize: 7, color: 'rgba(255,255,255,.18)', fontWeight: 600, letterSpacing: '.1em', borderBottom: '1px solid rgba(255,255,255,.04)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pairs.map(p => {
                    const isL = p.signal?.includes('L'), isS = p.signal?.includes('S')
                    const blocked = (gateMode === 'bullish' && isS) || (gateMode === 'bearish' && isL)
                    return (
                      <tr key={p.symbol} style={{ borderBottom: '1px solid rgba(255,255,255,.02)' }}>
                        <td style={{ padding: '7px 10px', fontWeight: 700, color: '#fff' }}>{p.symbol.replace('USDT', '')}<span style={{ color: 'rgba(255,255,255,.15)', fontSize: 9 }}>/USDT</span></td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 600, color: '#fff' }}>${pf(p.price)}</td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 600, color: p.change_24h >= 0 ? '#00E676' : '#FF3D71' }}>{p.change_24h >= 0 ? '+' : ''}{p.change_24h?.toFixed(2)}%</td>
                        <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                          {p.signal ? <Badge color={isL ? '#00E676' : '#FF3D71'}>{p.signal}</Badge> : <span style={{ color: 'rgba(255,255,255,.1)' }}>—</span>}
                        </td>
                        <td style={{ padding: '7px 10px', textAlign: 'right' }}>
                          {p.signal ? <Badge color={blocked ? '#FF3D71' : '#00E676'}>{blocked ? 'BLOCKED' : 'PASS'}</Badge> : <span style={{ color: 'rgba(255,255,255,.08)' }}>—</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* CLOSED P&L */}
          {tab === 'history' && (
            <div style={{ maxHeight: 450, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                <thead>
                  <tr style={{ background: 'rgba(255,255,255,.02)' }}>
                    {['Pair', 'Signal', 'Capital', 'P&L', 'ROI'].map((h, i) => (
                      <th key={i} style={{ padding: '6px 10px', textAlign: i === 0 ? 'left' : 'right', fontSize: 7, color: 'rgba(255,255,255,.18)', fontWeight: 600, letterSpacing: '.1em', borderBottom: '1px solid rgba(255,255,255,.04)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.map((t, i) => {
                    const roi = t.total_cap_used ? (t.realized_pnl / t.total_cap_used * 100) : 0
                    return (
                      <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,.02)' }}>
                        <td style={{ padding: '7px 10px', fontWeight: 700, color: '#fff' }}>{t.symbol?.replace('USDT', '')}</td>
                        <td style={{ padding: '7px 10px', textAlign: 'right' }}><Badge color="#448AFF">{t.signal_type}</Badge></td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', color: 'rgba(255,255,255,.4)' }}>${fmt(t.total_cap_used, 0)}</td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 700, color: t.realized_pnl >= 0 ? '#00E676' : '#FF3D71' }}>
                          {t.realized_pnl >= 0 ? '+' : ''}${fmt(t.realized_pnl)}
                        </td>
                        <td style={{ padding: '7px 10px', textAlign: 'right', color: roi >= 0 ? '#00E676' : '#FF3D71' }}>{roi >= 0 ? '+' : ''}{roi.toFixed(1)}%</td>
                      </tr>
                    )
                  })}
                </tbody>
                {closedTrades.length > 0 && (
                  <tfoot>
                    <tr style={{ background: 'rgba(255,255,255,.02)', borderTop: '1px solid rgba(255,255,255,.06)' }}>
                      <td colSpan={3} style={{ padding: '8px 10px', fontWeight: 700, color: 'rgba(255,255,255,.4)' }}>TOTAL REALIZED</td>
                      <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 700, fontSize: 13, color: realizedPnl >= 0 ? '#00E676' : '#FF3D71' }}>
                        {realizedPnl >= 0 ? '+' : ''}${fmt(realizedPnl)}
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          )}
        </div>

        {/* RIGHT: ALERTS */}
        <div>
          <div style={{ padding: '7px 12px', borderBottom: '1px solid rgba(255,255,255,.04)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,.01)' }}>
            <span style={{ fontSize: 8, fontWeight: 600, color: 'rgba(255,255,255,.3)', letterSpacing: '.08em' }}>ALERTS + TELEGRAM</span>
            <Badge color="#00E676">LIVE</Badge>
          </div>
          <div style={{ maxHeight: 480, overflowY: 'auto' }}>
            {alerts.map((a, i) => {
              const colors = { fill: '#00E676', gate: '#FF3D71', signal: '#448AFF', tp: '#00E676', sentiment: '#FFB547' }
              const c = colors[a.type] || '#448AFF'
              const ago = Math.round((Date.now() / 1000 - a.time))
              const agoStr = ago < 60 ? `${ago}s` : ago < 3600 ? `${Math.round(ago / 60)}m` : `${Math.round(ago / 3600)}h`
              return (
                <div key={a.id || i} style={{ padding: '6px 12px', borderBottom: '1px solid rgba(255,255,255,.02)', animation: i === 0 ? 'slideIn .3s ease-out' : 'none' }}>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'flex-start' }}>
                    <div style={{ width: 4, height: 4, borderRadius: '50%', marginTop: 5, flexShrink: 0, background: c, boxShadow: `0 0 4px ${c}` }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: '#fff' }}>{a.symbol?.replace('USDT', '')}</span>
                          <Badge color={c}>{a.type?.toUpperCase()}</Badge>
                        </div>
                        <span style={{ fontSize: 7, color: 'rgba(255,255,255,.15)' }}>{agoStr}</span>
                      </div>
                      <p style={{ fontSize: 9, color: 'rgba(255,255,255,.35)', margin: 0, lineHeight: 1.4 }}>{a.message}</p>
                    </div>
                  </div>
                </div>
              )
            })}
            {alerts.length === 0 && <div style={{ padding: 30, textAlign: 'center', color: 'rgba(255,255,255,.1)', fontSize: 10 }}>Waiting for signals...</div>}
          </div>
        </div>
      </div>

      {/* STATUS BAR */}
      <div style={{ padding: '5px 14px', borderTop: '1px solid rgba(255,255,255,.04)', display: 'flex', justifyContent: 'space-between', fontSize: 8, color: 'rgba(255,255,255,.15)', background: 'rgba(255,255,255,.01)' }}>
        <div style={{ display: 'flex', gap: 14 }}>
          <span>WS {connected ? <span style={{ color: '#00E676' }}>●</span> : <span style={{ color: '#FF3D71' }}>●</span>}</span>
          <span>Binance <span style={{ color: '#00E676' }}>●</span></span>
          <span>Telegram <span style={{ color: '#00E676' }}>●</span></span>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <span>Mode: <span style={{ color: demoMode ? '#FFB547' : '#00E676', fontWeight: 600 }}>{demoMode ? 'DEMO' : 'LIVE'}</span></span>
          <span>Gate: <span style={{ color: gateColor, fontWeight: 600 }}>{gateMode.toUpperCase()}</span></span>
        </div>
      </div>
    </div>
  )
}
