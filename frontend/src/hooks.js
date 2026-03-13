import { useState, useEffect, useRef, useCallback } from 'react'

export function useWebSocket(url) {
  const [state, setState] = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        console.log('WebSocket connected')
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setState(data)
        } catch (e) {
          console.error('WS parse error:', e)
        }
      }

      ws.onclose = () => {
        setConnected(false)
        reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch (e) {
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [url])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [connect])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  return { state, connected, send }
}

// Fallback polling when WS unavailable
export function usePolling(url, interval = 2000) {
  const [data, setData] = useState(null)

  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const res = await fetch(url)
        if (res.ok && active) {
          setData(await res.json())
        }
      } catch (e) { /* silent */ }
    }
    poll()
    const id = setInterval(poll, interval)
    return () => { active = false; clearInterval(id) }
  }, [url, interval])

  return data
}
