import { useState, useEffect, useRef, useMemo } from 'react'
import { mapToolNameToFriendlyName } from './utils/toolMappings'
import { 
  Send, 
  Terminal, 
  TrendingDown, 
  TrendingUp, 
  Activity, 
  Sparkles,
  RefreshCw,
  CheckCircle2,
  Cpu
} from 'lucide-react'

// Define Message types
interface Message {
  id: string
  sender: 'user' | 'assistant'
  text: string
  reasoning?: string
  timestamp: string
  a2uiPayload?: any
}

const formatFriendlyDate = (dateObj: Date): string => {
  const day = dateObj.getDate()
  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ]
  const month = monthNames[dateObj.getMonth()]
  
  let suffix = 'th'
  if (day === 1 || day === 21 || day === 31) suffix = 'st'
  else if (day === 2 || day === 22) suffix = 'nd'
  else if (day === 3 || day === 23) suffix = 'rd'
  
  return `${day}${suffix} ${month}`
}

const formatSpikeDate = (dateStr: string): string => {
  if (!dateStr) return '23rd May'
  
  // Check for YYYY-MM-DD
  if (dateStr.includes('-')) {
    const parts = dateStr.split('-')
    if (parts.length === 3) {
      const year = parseInt(parts[0], 10)
      const month = parseInt(parts[1], 10)
      const day = parseInt(parts[2], 10)
      try {
        const dateObj = new Date(year, month - 1, day)
        return formatFriendlyDate(dateObj)
      } catch (e) {
        return dateStr
      }
    }
  }
  
  // Check for MM/DD
  if (dateStr.includes('/')) {
    const parts = dateStr.split('/')
    if (parts.length === 2) {
      const month = parseInt(parts[0], 10)
      const day = parseInt(parts[1], 10)
      const currentYear = new Date().getFullYear()
      try {
        const dateObj = new Date(currentYear, month - 1, day)
        return formatFriendlyDate(dateObj)
      } catch (e) {
        return dateStr
      }
    }
  }
  
  return dateStr
}

export default function App() {
  // Navigation State
  const [isLoadingDashboard, setIsLoadingDashboard] = useState(true)
  const [loadingStage, setLoadingStage] = useState(0)

  const loadingStages = [
    'Connecting to BigQuery billing telemetry export...',
    'Compiling Month-to-Date spend and MoM financial trends...',
    'Generating linear projection cost forecast...',
    'Initiating Cloud Asset Inventory scan for zombie resources...',
    'Running statistical rolling average cost filters...',
    'Finalising dashboard data integration...'
  ]
  
  // Chat state
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello Dazbo! I am your FinOps AI Copilot. I have analyzed your cross-project GCP billing exports in BigQuery and scanned your operational Cloud Asset Inventory (CAI) metadata.\n\nHow can I help you optimize your Google Cloud spend today?',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ])
  const [inputText, setInputText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingReasoning, setStreamingReasoning] = useState('')
  const [streamingText, setStreamingText] = useState('')
  
  // Right Canvas State (Active Payload)
  const [activePayload, setActivePayload] = useState<any>({
    type: 'dashboard',
    data: {
      mtdSpend: 0,
      mtdChange: 0,
      forecast: 0,
      anomaliesCount: 0,
      zombieWaste: 0,
      recentSpikes: [],
      zombies: [],
      explorer: []
    }
  })

  // Persisted dashboard metrics state
  const [dashboardData, setDashboardData] = useState<any>({
    currency: 'GBP',
    mtdSpend: 0,
    mtdChange: 0,
    forecast: 0,
    anomaliesCount: 0,
    zombieWaste: 0,
    recentSpikes: [],
    zombies: [],
    explorer: []
  })

  // Table sorting states (Explorer View)
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'ascending' | 'descending' } | null>(null)
  

  const messageEndRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom of chat
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingText, streamingReasoning])

  // Agent connection status mode (local container fallback vs remote agent runtime)
  const [agentStatus, setAgentStatus] = useState<{ mode: 'local' | 'remote'; agent_runtime_id: string | null }>({
    mode: 'local',
    agent_runtime_id: null
  })

  // Fetch agent status from backend on startup
  useEffect(() => {
    const fetchAgentStatus = async () => {
      try {
        const response = await fetch('/api/status')
        if (response.ok) {
          const data = await response.json()
          setAgentStatus(data)
        }
      } catch (err) {
        console.error('Failed to fetch agent execution status:', err)
      }
    }
    fetchAgentStatus()
  }, [])

  // Fetch actual dashboard metrics from the backend on startup
  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const today = new Date()
        const clientDay = today.getDate()
        const clientMonthDays = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
        const response = await fetch(`/api/dashboard?clientDay=${clientDay}&clientMonthDays=${clientMonthDays}`)
        if (response.ok) {
          const data = await response.json()
          setDashboardData(data)
          setActivePayload({
            type: 'dashboard',
            data: data
          })
        }
      } catch (err) {
        console.error('Failed to fetch actual dashboard data on startup:', err)
      } finally {
        setIsLoadingDashboard(false)
      }
    }
    fetchDashboardData()
  }, [])

  // Cycle through loading stages during initial data load
  useEffect(() => {
    let stageInterval: any
    if (isLoadingDashboard) {
      stageInterval = setInterval(() => {
        setLoadingStage(prev => (prev < 5 ? prev + 1 : prev))
      }, 1200)
    }
    return () => clearInterval(stageInterval)
  }, [isLoadingDashboard])



  // Helper to extract text and hide the raw A2UI JSON payload block
  const getDisplayText = (text: string) => {
    // Strip complete code fences
    let clean = text.replace(/```(?:json\+a2ui|json)\s*[\s\S]*?```/g, '')
    // Also strip incomplete code fences at the very end of streaming text
    const incompleteIndex = clean.indexOf('```json')
    if (incompleteIndex !== -1) {
      clean = clean.substring(0, incompleteIndex)
    }
    const fenceIndex = clean.indexOf('```')
    if (fenceIndex !== -1 && fenceIndex >= clean.length - 12) {
      clean = clean.substring(0, fenceIndex)
    }
    return clean.trim()
  }

  // Localized date formatter aligned dynamically with the user's browser locale (e.g. dd/MM for UK, MM/dd for US)
  const formatLocalDate = (dateStr: string): string => {
    if (!dateStr) return dateStr;

    // Detect YYYY-MM-DD standard ISO format (e.g. 2026-05-19)
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr.trim())) {
      try {
        const [year, month, day] = dateStr.trim().split('-').map(Number);
        const dateObj = new Date(year, month - 1, day);
        return dateObj.toLocaleDateString(navigator.language, { day: '2-digit', month: '2-digit' }).replace(/[.-]/g, '/');
      } catch (e) {
        return dateStr;
      }
    }

    // Detect MM/DD format (e.g. 05/19 or 5/19)
    const mmDdMatch = dateStr.trim().match(/^(\d{1,2})\/(\d{1,2})$/);
    if (mmDdMatch) {
      try {
        const month = parseInt(mmDdMatch[1], 10);
        const day = parseInt(mmDdMatch[2], 10);
        if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
          const currentYear = new Date().getFullYear();
          const dateObj = new Date(currentYear, month - 1, day);
          const formatted = dateObj.toLocaleDateString(navigator.language, { day: '2-digit', month: '2-digit' });
          return formatted.replace(/[.-]/g, '/');
        }
      } catch (e) {
        return dateStr;
      }
    }

    return dateStr;
  };

  // Lightweight inline markdown formatter matching Emerald Cyber styles, supporting tables
  const renderMarkdown = (text: string) => {
    const cleanText = getDisplayText(text)

    // Escape HTML to prevent Cross-Site Scripting (XSS) vulnerabilities
    const escapedText = cleanText
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')

    const lines = escapedText.split('\n')
    let inList = false
    let inOrderedList = false
    let inCodeBlock = false
    let inTable = false
    let tableRows: string[][] = []
    let codeContent: string[] = []

    const processedLines: string[] = []

    const flushTable = () => {
      if (tableRows.length === 0) return ''
      
      const parsedRows = tableRows.filter(row => {
        const isSeparator = row.every(cell => /^[:-]*$/.test(cell.trim()));
        return !isSeparator;
      });

      if (parsedRows.length === 0) {
        tableRows = []
        return ''
      }

      const headers = parsedRows[0]
      const body = parsedRows.slice(1)

      let tableHtml = '<div class="table-container" style="overflow-x: auto; margin-top: 12px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px;">'
      tableHtml += '<table style="width: 100%; border-collapse: collapse; font-size: 13px; background: rgba(255,255,255,0.01);">'
      
      tableHtml += '<thead style="background: rgba(255,255,255,0.03); border-bottom: 1px solid rgba(255,255,255,0.08);">'
      tableHtml += '<tr>'
      headers.forEach(h => {
        tableHtml += `<th style="padding: 10px 14px; text-align: left; font-weight: 600; color: #FFFFFF; font-family: var(--font-mono);">${h.trim()}</th>`
      })
      tableHtml += '</tr>'
      tableHtml += '</thead>'

      tableHtml += '<tbody>'
      body.forEach((row, rIdx) => {
        const rowBg = rIdx % 2 === 1 ? 'rgba(255,255,255,0.015)' : 'transparent'
        tableHtml += `<tr style="background: ${rowBg}; border-bottom: 1px solid rgba(255,255,255,0.04);">`
        row.forEach(cell => {
          const content = cell.trim()
          const isNumeric = content.startsWith('£') || content.startsWith('$') || !isNaN(Number(content.replace(/[£$,%]/g, '')))
          const align = isNumeric ? 'right' : 'left'
          const style = `padding: 10px 14px; text-align: ${align}; ${isNumeric ? 'font-family: var(--font-mono); font-weight: 500;' : ''}`
          tableHtml += `<td style="${style}">${formatLocalDate(content)}</td>`
        })
        tableHtml += '</tr>'
      })
      tableHtml += '</tbody>'
      
      tableHtml += '</table>'
      tableHtml += '</div>'
      
      tableRows = []
      return tableHtml
    }

    lines.forEach((line) => {
      const trimmedLine = line.trim()

      // Handle Code Blocks: ```
      if (trimmedLine.startsWith('```')) {
        if (inCodeBlock) {
          inCodeBlock = false
          const codeText = codeContent.join('\n')
          processedLines.push(`<pre style="font-family: var(--font-mono); background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255,255,255,0.08); padding: 10px; border-radius: 6px; overflow-x: auto; margin-top: 8px; margin-bottom: 8px; font-size: 12.5px;"><code style="color: #e2e8f0; line-height: 1.4;">${codeText}</code></pre>`)
          codeContent = []
        } else {
          if (inList) { inList = false; processedLines.push('</ul>'); }
          if (inOrderedList) { inOrderedList = false; processedLines.push('</ol>'); }
          if (inTable) { inTable = false; processedLines.push(flushTable()); }
          inCodeBlock = true
        }
        return
      }

      if (inCodeBlock) {
        codeContent.push(line)
        return
      }

      // Process inline backticks and bold tags ONLY outside of code blocks
      const formattedLine = line
        .replace(/`([^`]+)`/g, '<code style="font-family: var(--font-mono); background: rgba(255, 255, 255, 0.08); padding: 2px 5px; border-radius: 4px; font-size: 0.9em; color: var(--color-primary);">$1</code>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')

      const trimmed = formattedLine.trim()

      // Handle Tables
      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        if (inList) { inList = false; processedLines.push('</ul>'); }
        if (inOrderedList) { inOrderedList = false; processedLines.push('</ol>'); }
        inTable = true
        const cells = formattedLine.split('|').slice(1, -1)
        tableRows.push(cells)
        return
      } else if (inTable) {
        inTable = false
        processedLines.push(flushTable())
      }

      // Handle Bullet Lists
      if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('+ ')) {
        if (inOrderedList) { inOrderedList = false; processedLines.push('</ol>'); }
        const bulletContent = trimmed.replace(/^[\s]*[*-+]\s+/, '')
        let prefix = ''
        if (!inList) {
          inList = true
          prefix = '<ul style="margin-left: 20px; margin-top: 6px; margin-bottom: 6px; list-style-type: disc;">'
        }
        processedLines.push(`${prefix}<li style="margin-bottom: 4px; line-height: 1.5;">${bulletContent}</li>`)
        return
      } 

      // Handle Ordered Lists
      const orderedMatch = trimmed.match(/^(\d+)\.\s+(.*)$/)
      if (orderedMatch) {
        if (inList) { inList = false; processedLines.push('</ul>'); }
        const listContent = orderedMatch[2]
        let prefix = ''
        if (!inOrderedList) {
          inOrderedList = true
          prefix = '<ol style="margin-left: 20px; margin-top: 6px; margin-bottom: 6px; list-style-type: decimal;">'
        }
        processedLines.push(`${prefix}<li style="margin-bottom: 4px; line-height: 1.5;">${listContent}</li>`)
        return
      }

      // Close open lists if we hit standard paragraphs/headings
      if (inList) {
        inList = false
        processedLines.push('</ul>')
      }
      if (inOrderedList) {
        inOrderedList = false
        processedLines.push('</ol>')
      }

      // Handle Headings
      if (trimmed.startsWith('# ')) {
        processedLines.push(`<h1 style="font-size: 18px; font-weight: 800; margin-top: 18px; margin-bottom: 8px; color: #FFFFFF;">${trimmed.replace(/^#\s+/, '')}</h1>`)
        return
      }
      if (trimmed.startsWith('## ')) {
        processedLines.push(`<h2 style="font-size: 15px; font-weight: 700; margin-top: 16px; margin-bottom: 8px; color: #FFFFFF; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 4px;">${trimmed.replace(/^##\s+/, '')}</h2>`)
        return
      }
      if (trimmed.startsWith('### ')) {
        processedLines.push(`<h3 style="font-size: 14px; font-weight: 700; margin-top: 14px; margin-bottom: 6px; color: var(--color-primary);">${trimmed.replace(/^###\s+/, '')}</h3>`)
        return
      }
      if (trimmed.startsWith('#### ')) {
        processedLines.push(`<h4 style="font-size: 12.5px; font-weight: 700; margin-top: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">${trimmed.replace(/^####\s+/, '')}</h4>`)
        return
      }

      processedLines.push(formattedLine ? `<p style="margin-bottom: 8px;">${formattedLine}</p>` : '')
    })

    if (inList) {
      processedLines.push('</ul>')
    }
    if (inOrderedList) {
      processedLines.push('</ol>')
    }
    if (inTable) {
      processedLines.push(flushTable())
    }
    if (inCodeBlock) {
      const codeText = codeContent.join('\n')
      processedLines.push(`<pre style="font-family: var(--font-mono); background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(255,255,255,0.08); padding: 10px; border-radius: 6px; overflow-x: auto; margin-top: 8px; margin-bottom: 8px; font-size: 12.5px;"><code style="color: #e2e8f0; line-height: 1.4;">${codeText}</code></pre>`)
    }

    return (
      <div 
        dangerouslySetInnerHTML={{ __html: processedLines.filter(l => l !== '').join('\n') }} 
        style={{ lineHeight: '1.6', fontSize: '14px', color: 'var(--color-text)' }}
      />
    )
  }

  // SSE Chat stream handle
  const handleSendMessage = async (textToSend: string) => {
    if (!textToSend.trim() || isStreaming) return

    const userMsg: Message = {
      id: Math.random().toString(),
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    setMessages((prev: Message[]) => [...prev, userMsg])
    setInputText('')
    setIsStreaming(true)
    setStreamingReasoning('')
    setStreamingText('')

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ message: textToSend })
      })

      if (!response.ok) {
        throw new Error('Failed to connect to agent backend service.')
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) throw new Error('No readable stream reader available.')

      let accumulatedReasoning = ''
      let accumulatedText = ''
      let buffer = ''

      let doneReading = false
      while (!doneReading) {
        const { value, done } = await reader.read()
        if (done) {
          doneReading = true
          break
        }

        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk

        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.trim()) continue
          if (line.startsWith(': heartbeat')) {
            continue
          }
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6))
              if (data.reasoning) {
                accumulatedReasoning += data.reasoning
                setStreamingReasoning(accumulatedReasoning)
              }
              if (data.text) {
                accumulatedText += data.text
                setStreamingText(accumulatedText)
              }
            } catch (e) {
              console.error('Error parsing SSE payload', e)
            }
          }
        }
      }

      setIsStreaming(false)

      // Parse final text for A2UI dynamic payload blocks
      let parsedPayload: any = null
      // Look for ```json+a2ui ... ``` or ```json ... ``` code fences
      const match = accumulatedText.match(/```(?:json\+a2ui|json)\s*([\s\S]*?)```/)
      if (match && match[1]) {
        try {
          parsedPayload = JSON.parse(match[1].trim())
        } catch (e) {
          console.error('Failed to parse embedded A2UI JSON payload:', e)
        }
      }

      // If A2UI payload is successfully extracted, update workspace canvas
      if (parsedPayload && parsedPayload.type) {
        setActivePayload(parsedPayload)
      }

      // Append final assistant message to chat thread
      const assistantMsg: Message = {
        id: Math.random().toString(),
        sender: 'assistant',
        text: accumulatedText || "I've processed your request. Please view the updated Canvas on the right.",
        reasoning: accumulatedReasoning,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        a2uiPayload: parsedPayload
      }
      setMessages((prev: Message[]) => [...prev, assistantMsg])
      setStreamingReasoning('')
      setStreamingText('')

    } catch (err) {
      console.error(err)
      setIsStreaming(false)
      setMessages((prev: Message[]) => [...prev, {
        id: Math.random().toString(),
        sender: 'assistant',
        text: 'Sorry, I encountered an issue connecting to the FastAPI backend. Please check that the server is active on port 8000.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }])
    }
  }


  // Table Sort logic
  const requestSort = (key: string) => {
    let direction: 'ascending' | 'descending' = 'ascending'
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'ascending') {
      direction = 'descending'
    }
    setSortConfig({ key, direction })
  }

  const getSortedData = (data: any) => {
    if (!Array.isArray(data)) return []
    if (!sortConfig) return data
    return [...data].sort((a, b) => {
      if (a[sortConfig.key] < b[sortConfig.key]) {
        return sortConfig.direction === 'ascending' ? -1 : 1
      }
      if (a[sortConfig.key] > b[sortConfig.key]) {
        return sortConfig.direction === 'ascending' ? 1 : -1
      }
      return 0
    })
  }

  // Compiled dashboard render data (restores persisted metrics or uses active canvas payload)
  const dashboardRenderData = (activePayload.type === 'dashboard' && activePayload.data && !Array.isArray(activePayload.data)) 
    ? activePayload.data 
    : dashboardData;

  const currencySymbol = (() => {
    const cur = activePayload?.data?.currency || dashboardData?.currency || 'GBP';
    if (cur === 'GBP') return '£';
    if (cur === 'USD') return '$';
    if (cur === 'EUR') return '€';
    return cur + ' ';
  })();

  // Dynamic SVG Chart Path Calculators
  const rawRecentSpikes = dashboardRenderData?.recentSpikes || []
  const hasSpikes = rawRecentSpikes.length > 1
  const topServices: string[] = dashboardRenderData?.topServices || 
    (hasSpikes 
      ? Object.keys(rawRecentSpikes[0]).filter(k => {
          if (k === 'date') return false;
          const val = rawRecentSpikes[0][k];
          return typeof val === 'number' || (!isNaN(parseFloat(val)) && isFinite(parseFloat(val)));
        })
      : ['Cloud Run', 'Gemini API', 'Vertex AI'])

  // Fill in missing chronological dates to ensure a continuous daily visual spread (e.g. 30 bars for 30 days)
  const recentSpikes = useMemo(() => {
    if (rawRecentSpikes.length <= 1) return rawRecentSpikes;
    
    // Auto-detect format structure (YYYY-MM-DD or MM/DD)
    const isIsoFormat = rawRecentSpikes.some((d: any) => d.date && d.date.includes('-'));
    const currentYear = new Date().getFullYear();
    
    const parsedSpikes = rawRecentSpikes.map((d: any) => {
      let dateObj: Date;
      if (isIsoFormat) {
        const [y, m, day] = d.date.split('-').map(Number);
        dateObj = new Date(y, m - 1, day);
      } else {
        const [m, day] = d.date.split('/').map(Number);
        dateObj = new Date(currentYear, m - 1, day);
      }
      return { dateObj, original: d };
    });
    
    // Sort chronologically
    parsedSpikes.sort((a: any, b: any) => a.dateObj.getTime() - b.dateObj.getTime());
    
    const start = new Date(parsedSpikes[0].dateObj);
    const end = new Date(parsedSpikes[parsedSpikes.length - 1].dateObj);
    
    // Gather all service telemetry keys to pre-populate empty/zero cost days safely
    const serviceKeys = new Set<string>(topServices);
    rawRecentSpikes.forEach((d: any) => {
      Object.keys(d).forEach(k => {
        if (k !== 'date') serviceKeys.add(k);
      });
    });
    
    const filled: any[] = [];
    const cur = new Date(start);
    while (cur <= end) {
      let dateStr = '';
      if (isIsoFormat) {
        const y = cur.getFullYear();
        const m = String(cur.getMonth() + 1).padStart(2, '0');
        const d = String(cur.getDate()).padStart(2, '0');
        dateStr = `${y}-${m}-${d}`;
      } else {
        const m = String(cur.getMonth() + 1).padStart(2, '0');
        const d = String(cur.getDate()).padStart(2, '0');
        dateStr = `${m}/${d}`;
      }
      
      const existing = parsedSpikes.find((p: any) => 
        p.dateObj.getFullYear() === cur.getFullYear() &&
        p.dateObj.getMonth() === cur.getMonth() &&
        p.dateObj.getDate() === cur.getDate()
      );
      if (existing) {
        filled.push(existing.original);
      } else {
        const newEntry: any = { date: dateStr };
        serviceKeys.forEach(k => {
          newEntry[k] = 0.0;
        });
        filled.push(newEntry);
      }
      cur.setDate(cur.getDate() + 1);
    }
    return filled;
  }, [rawRecentSpikes, topServices]);

  // Get raw max value of the daily stacked total to set Y headroom
  const rawMaxY = hasSpikes 
    ? Math.max(...recentSpikes.map((d: any) => {
        const total = topServices.reduce((sum, k) => {
          const val = typeof d[k] === 'number' ? d[k] : parseFloat(d[k]);
          return sum + (isNaN(val) ? 0 : val)
        }, 0)
        return Math.max(total, 0.1)
      }), 0.5) 
    : 10;
  // Scale with 15% headroom for premium, TradingView-style financial graphing
  const maxY = rawMaxY * 1.15;

  const getCumulativeVal = (d: any, series: string) => {
    const idx = topServices.indexOf(series)
    if (idx === -1) return 0
    let sum = 0
    for (let j = 0; j <= idx; j++) {
      const val = typeof d[topServices[j]] === 'number' ? d[topServices[j]] : parseFloat(d[topServices[j]]);
      sum += isNaN(val) ? 0 : val
    }
    return sum
  }

  const getPath = (series: string) => {
    if (!hasSpikes) return ''
    return recentSpikes.map((d: any, i: number) => {
      const x = (i / (recentSpikes.length - 1)) * 645 + 45
      const val = getCumulativeVal(d, series)
      const y = 200 - (val / maxY) * 185
      return `${i === 0 ? 'M' : 'L'}${x},${y}`
    }).join(' ')
  }

  const getAreaPath = (series: string) => {
    if (!hasSpikes) return ''
    const idx = topServices.indexOf(series)
    if (idx === -1) return ''
    
    const points: string[] = []
    // Go forward along the current curve
    recentSpikes.forEach((d: any, i: number) => {
      const x = (i / (recentSpikes.length - 1)) * 645 + 45
      const val = getCumulativeVal(d, series)
      const y = 200 - (val / maxY) * 185
      points.push(`${i === 0 ? 'M' : 'L'}${x},${y}`)
    })
    
    // Go backward along the previous curve
    for (let i = recentSpikes.length - 1; i >= 0; i--) {
      const d = recentSpikes[i]
      const x = (i / (recentSpikes.length - 1)) * 645 + 45
      let prevVal = 0
      if (idx > 0) {
        prevVal = getCumulativeVal(d, topServices[idx - 1])
      }
      const y = 200 - (prevVal / maxY) * 185
      points.push(`L${x},${y}`)
    }
    
    points.push('Z')
    return points.join(' ')
  }

  // Find the day with the maximum total cost to place a pulsing spike dot
  let maxIdx = -1
  let maxVal = -1
  if (hasSpikes) {
    recentSpikes.forEach((d: any, i: number) => {
      const total = topServices.reduce((sum, k) => sum + (d[k] || 0), 0)
      if (total > maxVal) {
        maxVal = total
        maxIdx = i
      }
    })
  }

  const maxDotX = hasSpikes && maxIdx !== -1 ? (maxIdx / (recentSpikes.length - 1)) * 645 + 45 : 335
  const maxDotY = hasSpikes && maxIdx !== -1 ? 200 - (maxVal / maxY) * 185 : 80
  const maxColor = 'var(--color-error)'

  // Compiled dynamic sample questions using real-time spike telemetry
  const sampleQuestions = useMemo(() => {
    let spikeDateText = '23rd May'
    const isSpikeQuestionDisabled = isLoadingDashboard
    if (hasSpikes && maxIdx !== -1) {
      const peakDateStr = recentSpikes[maxIdx]?.date
      if (peakDateStr) {
        spikeDateText = formatSpikeDate(peakDateStr)
      }
    }
    return [
      { label: 'Scan Zombie Resources', text: 'Run a Cloud Asset Inventory scan across all projects to detect zombie resources and unattached persistent disks.' },
      { label: 'Show Top Cost Drivers', text: 'Query our BigQuery billing export to show the top 3 services driving our spend this month.' },
      { 
        label: isLoadingDashboard ? 'Resolving Spikes...' : 'Analyze Cost Spikes', 
        text: `Why did our production costs spike on ${spikeDateText}? Cross-reference billing records with CAI config changes.`,
        disabled: isSpikeQuestionDisabled
      },
      { label: 'Run Cost Forecast', text: 'Run a 3-month cost forecast and explain any projected anomalies.' },
      { label: 'Compare Best Practices', text: 'Compare our current architecture against GCP best practices for storage and compute savings.' },
      { label: 'Last 30 Days', text: 'Show the utilisation over the last 30 days, showing most costly services.' }
    ]
  }, [recentSpikes, hasSpikes, maxIdx, isLoadingDashboard])

  // Dynamic date X-axis interval thinner to prevent label crowding
  const dateStep = (() => {
    const len = recentSpikes.length;
    if (len <= 10) return 1;
    if (len <= 20) return 2;
    if (len <= 40) return 4;
    return Math.ceil(len / 8);
  })();

  const shouldShowLabel = (i: number) => {
    const len = recentSpikes.length;
    if (i === 0 || i === len - 1 || i === maxIdx) return true;
    if (i % dateStep !== 0) return false;
    const minDistance = Math.max(Math.floor(dateStep * 0.7), 1);
    if (i < minDistance) return false;
    if (len - 1 - i < minDistance) return false;
    if (maxIdx !== -1 && Math.abs(i - maxIdx) < minDistance) return false;
    return true;
  };

  // Self-Healing Resource Formatters (handles raw CAI keys and joins dynamically)
  const getResourceId = (z: any) => {
    return z.id || z.name || Math.random().toString();
  };

  const getShortName = (z: any) => {
    const rawName = z.service || z.sku || z.displayName || z.name || z.resourceName || z.resource_name || z.id || '';
    if (rawName.includes('/')) {
      return rawName.split('/').pop() || rawName;
    }
    return rawName || 'GCP Project spend';
  };

  const getResourceType = (z: any) => {
    const rawType = z.type || z.assetType || z.resourceType || z.resource_type || '';
    if (!rawType) {
      if (z.service) return 'GCP Service';
      return 'Active Project Cost';
    }
    if (rawType.includes('Disk') || rawType.includes('disk')) return 'Persistent Disk';
    if (rawType.includes('Address') || rawType.includes('address') || rawType.includes('IP') || rawType.includes('ip')) return 'Static IP Address';
    if (rawType.includes('/')) return rawType.split('/').pop() || rawType;
    return rawType;
  };

  const getResourceStatus = (z: any) => {
    const rawStatus = z.status || z.state || '';
    if (!rawStatus) return 'ACTIVE'; // Smart fallback for general spend
    if (rawStatus === 'READY') return 'UNATTACHED';
    if (rawStatus === 'RESERVED') return 'UNASSIGNED';
    return rawStatus.toUpperCase();
  };

  const getResourceSize = (z: any) => {
    if (z.size) return z.size;
    if (z.additionalAttributes?.size) return z.additionalAttributes.size;
    const type = getResourceType(z);
    if (type.includes('IP') || type.includes('Address')) return 'N/A';
    return 'Unknown';
  };

  const getProjectName = (z: any) => {
    const rawProject = z.project || z.projectId || z.project_id || 'Unknown';
    if (rawProject.startsWith('projects/')) {
      return rawProject.substring(9);
    }
    return rawProject;
  };

  // Compile the live list of optimization recommendations
  const recommendationsData = 
    activePayload.type === 'recommendations' && Array.isArray(activePayload.data) 
      ? activePayload.data 
      : (dashboardData?.zombies || []);

  // Compile the live list of explorer rows
  const explorerData = 
    activePayload.type === 'explorer' && Array.isArray(activePayload.data) 
      ? activePayload.data 
      : (dashboardData?.explorer || []);

  // Dynamically check if at least one row has a non-empty project ID
  const showProjectColumn = explorerData.some((row: any) => row.project && row.project.trim() !== '');

  return (
    <div className="app-shell">
      {/* LEFT COLUMN: CHAT COPILOT */}
      <aside className="chat-panel">
        <header className="panel-header">
          <div className="panel-title" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '2px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <Sparkles size={20} className="text-glow-emerald" style={{ filter: 'drop-shadow(0 0 4px rgba(0, 245, 155, 0.4))' }} />
              <span style={{ fontSize: '18px', fontWeight: '700', color: '#FFFFFF', letterSpacing: '0.02em', textShadow: '0 0 10px rgba(255, 255, 255, 0.1)' }}>FinSavant</span>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '2px 6px',
                borderRadius: '4px',
                fontSize: '9px',
                fontFamily: 'var(--font-mono)',
                fontWeight: 'bold',
                letterSpacing: '0.05em',
                background: agentStatus.mode === 'remote' ? 'rgba(0, 245, 155, 0.08)' : 'rgba(245, 158, 11, 0.08)',
                border: agentStatus.mode === 'remote' ? '1px solid rgba(0, 245, 155, 0.25)' : '1px solid rgba(245, 158, 11, 0.25)',
                color: agentStatus.mode === 'remote' ? '#00F59B' : '#F59E0B',
                boxShadow: agentStatus.mode === 'remote' ? '0 0 8px rgba(0, 245, 155, 0.05)' : '0 0 8px rgba(245, 158, 11, 0.05)',
                marginLeft: '4px'
              }}
              title={agentStatus.mode === 'remote' ? `Connected to Remote Vertex Agent Runtime:\n${agentStatus.agent_runtime_id}` : "Running agent locally in container fallback"}
              >
                <Cpu size={10} />
                <span>{agentStatus.mode === 'remote' ? 'VERTEX RUNTIME' : 'IN-CONTAINER FALLBACK'}</span>
              </div>
            </div>
            <div style={{ 
              fontSize: '12px', 
              fontFamily: 'var(--font-sans)', 
              color: 'var(--color-text-secondary)',
              lineHeight: '1.4',
              marginTop: '1px',
              marginLeft: '28px',
              letterSpacing: '0.01em',
              fontWeight: 'normal'
            }}>
              <a 
                href="https://dazbo.co.uk" 
                target="_blank" 
                rel="noopener noreferrer"
                style={{
                  color: 'var(--color-primary)',
                  textDecoration: 'none',
                  fontWeight: '600',
                  transition: 'all 0.25s ease',
                  borderBottom: '1px dashed rgba(0, 245, 155, 0.3)',
                  cursor: 'pointer'
                }}
                title="Visit Dazbo's Portfolio"
              >
                Dazbo's
              </a>
              <span> Google Cloud FinOps Intelligence</span>
            </div>
          </div>
          <div className="status-pill">
            <span className="status-dot pulse"></span>
            <span>Live</span>
          </div>
        </header>

        {/* Message History Thread */}
        <div className="message-list">
          {messages.map(msg => (
            <div key={msg.id} className={`message-bubble ${msg.sender}`}>
              {msg.reasoning && (
                <details className="reasoning-details" style={{ margin: '8px 0 12px 0' }}>
                  <summary className="reasoning-summary" style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    cursor: 'pointer',
                    color: 'var(--color-text-muted)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    fontWeight: 500,
                    padding: '4px 10px',
                    borderRadius: '6px',
                    background: 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid rgba(255, 255, 255, 0.05)',
                    width: 'fit-content',
                    userSelect: 'none'
                  }}>
                    <Terminal size={12} style={{ color: 'var(--color-primary)' }} />
                    <span>View agent workflow logs ({msg.reasoning.split('\n').filter(Boolean).length} steps)</span>
                  </summary>
                  <div className="reasoning-steps-list" style={{
                    marginTop: '8px',
                    paddingLeft: '12px',
                    borderLeft: '2px solid rgba(99, 102, 241, 0.2)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '11px',
                    color: 'var(--color-text-muted)'
                  }}>
                    {msg.reasoning.split('\n').map((line, idx) => (
                      line && (
                        <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ color: 'var(--color-primary)' }}>&gt;</span>
                          <span>{line}</span>
                        </div>
                      )
                    ))}
                  </div>
                </details>
              )}
              <div className="message-content">
                {msg.sender === 'assistant' ? renderMarkdown(msg.text) : <div style={{ whiteSpace: 'pre-line' }}>{msg.text}</div>}
              </div>
            </div>
          ))}
          
          {/* Active Streaming Response */}
          {isStreaming && (
            <div className="message-bubble assistant" style={{ width: '100%' }}>
              {/* Progress/Reasoning Block */}
              {(streamingReasoning || !streamingText) && (
                <div className="reasoning-block-compact" style={{
                  background: 'rgba(255, 255, 255, 0.01)',
                  border: '1px solid rgba(255, 255, 255, 0.03)',
                  borderRadius: '8px',
                  padding: '10px 14px',
                  margin: '8px 0 12px 0',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '12px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  color: 'var(--color-text-secondary)',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
                  minWidth: '280px',
                  maxWidth: '100%',
                  backdropFilter: 'blur(4px)',
                  WebkitBackdropFilter: 'blur(4px)'
                }}>
                  {(() => {
                    const lines = streamingReasoning.split('\n').map(l => l.trim()).filter(Boolean);
                    if (lines.length === 0) {
                      return (
                        <>
                          <span className="status-dot pulse" style={{ width: '8px', height: '8px', backgroundColor: 'var(--color-primary)', borderRadius: '50%' }}></span>
                          <span style={{ color: 'var(--color-text-muted)' }}>Copilot is spawning agent workspace workflow...</span>
                        </>
                      );
                    }
                    
                    const lastLine = lines[lines.length - 1];
                    
                    let icon = <Activity size={14} className="spin-slow" style={{ color: 'var(--color-primary)' }} />;
                    let statusText = lastLine;
                    let isCompleted = false;
                    
                    if (lastLine.includes("⚙️ Tool Call: Invoking")) {
                      const toolName = lastLine.replace("⚙️ Tool Call: Invoking", "").replace("...", "").trim();
                      icon = <Cpu size={14} className="pulse-fast" style={{ color: '#818cf8' }} />;
                      statusText = `Executing: ${mapToolNameToFriendlyName(toolName)}...`;
                    } else if (lastLine.includes("✅ Tool Complete:")) {
                      const toolName = lastLine.replace("✅ Tool Complete:", "").replace("response received", "").trim();
                      icon = <Activity size={14} className="spin-slow" style={{ color: 'var(--color-primary)' }} />;
                      statusText = `Completed: ${mapToolNameToFriendlyName(toolName)}. Analysing results...`;
                      isCompleted = false;
                    } else if (lastLine.includes("Step 1:")) {
                      icon = <Sparkles size={14} style={{ color: '#fbbf24' }} />;
                      statusText = "Initialising billing context...";
                    } else if (lastLine.includes("Step 2:")) {
                      icon = <Sparkles size={14} style={{ color: '#fbbf24' }} />;
                      statusText = "Connected. Analysing cost telemetry...";
                    } else if (lastLine.includes("response received")) {
                      icon = <CheckCircle2 size={14} style={{ color: '#34d399' }} />;
                      statusText = lastLine;
                      isCompleted = true;
                    }
                    
                    return (
                      <>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '20px', height: '20px' }}>
                          {isCompleted ? icon : (
                            <div className="dynamic-tool-spinner" style={{ display: 'flex', position: 'relative', width: '16px', height: '16px' }}>
                              <span className="dot pulse" style={{ position: 'absolute', width: '100%', height: '100%', borderRadius: '50%', border: '2px solid var(--color-primary)', borderTopColor: 'transparent', animation: 'spin 1.0s linear infinite' }}></span>
                              <div style={{ margin: 'auto', display: 'flex' }}>
                                {icon}
                              </div>
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontWeight: 500, fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            {lastLine.includes("✅ Tool Complete:") ? 'Analysing Results' : (isCompleted ? 'Finished step' : 'Active Operation')}
                          </span>
                          <span style={{ fontSize: '12px', color: 'var(--color-text-primary)' }}>{statusText}</span>
                        </div>
                      </>
                    );
                  })()}
                </div>
              )}

              {/* Streaming Markdown response */}
              {streamingText && <div className="message-content" style={{ marginTop: '8px' }}>{renderMarkdown(streamingText)}</div>}
            </div>
          )}
          <div ref={messageEndRef} />
        </div>

        {/* Chat Starters */}
        {!isStreaming && (
          <div className="starter-grid">
            {sampleQuestions.map((q: any, idx) => (
              <button 
                key={idx} 
                className={`starter-chip ${q.disabled ? 'disabled' : ''}`}
                onClick={() => !q.disabled && handleSendMessage(q.text)}
                disabled={q.disabled}
                style={q.disabled ? { opacity: 0.5, cursor: 'not-allowed' } : {}}
              >
                {q.label}
              </button>
            ))}
          </div>
        )}

        {/* Chat Input Footer */}
        <footer className="input-area">
          <div className="input-container" style={{ marginBottom: '8px' }}>
            <input 
              type="text" 
              className="chat-input"
              placeholder="Ask about your GCP costs, anomalies, or zombie assets..."
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSendMessage(inputText)}
              disabled={isStreaming}
            />
            <button 
              className="btn-submit"
              onClick={() => handleSendMessage(inputText)}
              disabled={isStreaming}
            >
              <Send size={16} />
            </button>
          </div>
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            color: 'var(--color-text-muted)',
            marginTop: '4px'
          }}>
            <span>POWERED BY </span>
            <a 
              href="https://dazbo.co.uk" 
              target="_blank" 
              rel="noopener noreferrer"
              style={{
                color: 'var(--color-primary)',
                textDecoration: 'none',
                marginLeft: '4px',
                fontWeight: 'bold',
                textShadow: '0 0 6px rgba(0, 245, 155, 0.2)'
              }}
              title="Visit Dazbo's Portfolio"
            >
              DAZBO.CO.UK
            </a>
          </div>
        </footer>
      </aside>

      {/* RIGHT COLUMN: WORKSPACE CANVAS */}
      <main className="canvas-panel" style={{ overflowY: 'auto', height: '100vh', paddingBottom: '40px', position: 'relative' }}>
        {isStreaming && !isLoadingDashboard && (streamingText.includes('```json+a2ui') || streamingText.includes('```json')) && (
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(8, 11, 13, 0.75)',
            backdropFilter: 'blur(3px)',
            WebkitBackdropFilter: 'blur(3px)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '20px',
            zIndex: 50,
            borderRadius: '12px',
            animation: 'fade-in 0.25s ease-in-out'
          }}>
            <div style={{ position: 'relative', width: '60px', height: '60px' }}>
              {/* Spinning glowing ring */}
              <div style={{
                position: 'absolute',
                top: 0, left: 0, right: 0, bottom: 0,
                borderRadius: '50%',
                border: '3px solid rgba(0, 245, 155, 0.05)',
                borderTopColor: 'var(--color-primary)',
                animation: 'spin 1s linear infinite'
              }}></div>
              {/* Pulsing indicator */}
              <div style={{
                position: 'absolute',
                top: '18px', left: '18px', right: '18px', bottom: '18px',
                borderRadius: '50%',
                backgroundColor: 'rgba(0, 245, 155, 0.1)',
                border: '1px solid var(--color-primary)',
                boxShadow: '0 0 10px rgba(0, 245, 155, 0.4)',
                animation: 'pulse-glow 1.2s infinite ease-in-out'
              }}></div>
            </div>
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '6px'
            }}>
              <span style={{
                fontSize: '12px',
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-primary)',
                letterSpacing: '0.15em',
                textTransform: 'uppercase',
                fontWeight: 'bold',
                textShadow: '0 0 8px rgba(0, 245, 155, 0.3)'
              }}>
                Syncing Telemetry
              </span>
              <span style={{
                fontSize: '11px',
                fontFamily: 'var(--font-sans)',
                color: 'var(--color-text-secondary)',
              }}>
                FinSavant is calculating new canvas telemetry...
              </span>
            </div>
            {/* Scanning beam effect */}
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '4px',
              background: 'linear-gradient(to right, transparent, rgba(0, 245, 155, 0.8), transparent)',
              boxShadow: '0 0 12px var(--color-primary)',
              animation: 'scan-vertical 3s linear infinite',
              pointerEvents: 'none'
            }}></div>
          </div>
        )}
        {/* Navigation / Environment status */}
        <div className="flex-between" style={{ marginBottom: '24px', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={16} style={{ color: 'var(--color-primary)', marginRight: '6px' }} />
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: '700', fontSize: '16px', color: '#FFFFFF', letterSpacing: '0.02em' }}>
              Unified FinOps Telemetry Dashboard
            </span>
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--color-text-muted)', marginLeft: '24px', whiteSpace: 'nowrap' }}>
            DATASET: standard_export_bq_prd
          </div>
        </div>

        {isLoadingDashboard ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '70%', gap: '20px' }}>
            <div style={{ position: 'relative', width: '80px', height: '80px' }}>
              {/* Spinning charcoal ring */}
              <div style={{
                position: 'absolute',
                top: 0, left: 0, right: 0, bottom: 0,
                borderRadius: '50%',
                border: '4px solid rgba(255,255,255,0.05)',
                borderTopColor: 'var(--color-primary)',
                animation: 'spin 1.2s linear infinite'
              }}></div>
              {/* Counter-spinning teal ring */}
              <div style={{
                position: 'absolute',
                top: '8px', left: '8px', right: '8px', bottom: '8px',
                borderRadius: '50%',
                border: '2px dashed rgba(0, 229, 255, 0.2)',
                borderBottomColor: 'var(--color-tertiary)',
                animation: 'spin 2s linear infinite reverse'
              }}></div>
              {/* Inner glowing green dot */}
              <div style={{
                position: 'absolute',
                top: '24px', left: '24px', right: '24px', bottom: '24px',
                borderRadius: '50%',
                backgroundColor: 'var(--color-primary)',
                boxShadow: '0 0 15px var(--color-primary)',
                animation: 'pulse-glow 1.5s infinite ease-in-out'
              }}></div>
            </div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              backgroundColor: 'rgba(0, 245, 155, 0.04)',
              border: '1px solid rgba(0, 245, 155, 0.1)',
              borderRadius: '8px',
              padding: '12px 20px',
              maxWidth: '380px'
            }}>
              <Terminal size={14} className="text-glow-emerald" style={{ color: 'var(--color-primary)', flexShrink: 0 }} />
              <span style={{
                fontSize: '13px',
                color: 'var(--color-text-secondary)',
                fontFamily: 'var(--font-mono)',
                textAlign: 'left',
                lineHeight: '1.4'
              }}>
                {loadingStages[loadingStage]}
              </span>
            </div>
          </div>
        ) : (
          <>
            {dashboardRenderData && (
              <div>
                {/* KPI Metrics row */}
                <div className="kpi-grid">
                  <div 
                    className="kpi-card"
                    onClick={() => {
                      document.getElementById('cost-explorer-card')?.scrollIntoView({ behavior: 'smooth' });
                    }}
                    title="Click to view Cost Explorer"
                  >
                    <div className="kpi-label">Month-to-Date Spend</div>
                    <div className="kpi-value">{currencySymbol}{Number(dashboardRenderData.mtdSpend ?? 0).toLocaleString()}</div>
                    <div className="kpi-trend down">
                      <TrendingDown size={14} style={{ marginRight: '4px', verticalAlign: 'middle', display: 'inline' }} />
                      {Number(dashboardRenderData.mtdChange ?? 0)}% vs last month
                    </div>
                  </div>
                  
                  <div 
                    className="kpi-card"
                    onClick={() => {
                      handleSendMessage("Run a 3-month cost forecast and explain any projected anomalies.");
                    }}
                    title="Click to have Copilot run a cost forecast"
                  >
                    <div className="kpi-label">Forecasted Spend</div>
                    <div className="kpi-value">{currencySymbol}{Number(dashboardRenderData.forecast ?? 0).toLocaleString()}</div>
                    <div style={{ color: 'var(--color-text-muted)', fontSize: '12px' }}>{dashboardRenderData.forecastLabel || 'Projected end-of-month'}</div>
                  </div>

                  <div 
                    className="kpi-card anomaly" 
                    style={{ borderColor: 'rgba(239, 68, 68, 0.2)' }}
                    onClick={() => {
                      handleSendMessage("Identify and analyze the recent cost anomalies and explain what caused them.");
                    }}
                    title="Click to have Copilot analyze active anomalies"
                  >
                    <div className="kpi-label" style={{ color: 'var(--color-error)' }}>Active Anomalies</div>
                    <div className="kpi-value text-glow-red">{Number(dashboardRenderData.anomaliesCount ?? 0)}</div>
                    <div className="kpi-trend up" style={{ color: 'var(--color-error)' }}>
                      <TrendingUp size={14} style={{ marginRight: '4px', verticalAlign: 'middle', display: 'inline' }} />
                      Requires Review
                    </div>
                  </div>

                  <div 
                    className="kpi-card"
                    onClick={() => {
                      document.getElementById('zombie-assets-card')?.scrollIntoView({ behavior: 'smooth' });
                    }}
                    title="Click to view Zombie Assets Finder"
                  >
                    <div className="kpi-label">Zombie Assets Waste</div>
                    <div className="kpi-value text-glow-teal">{currencySymbol}{Number(dashboardRenderData.zombieWaste ?? 0).toLocaleString()}</div>
                    <div style={{ color: 'var(--color-tertiary)', fontSize: '12px' }}>Potential immediate saving</div>
                  </div>
                </div>

                {/* Glowing Stacked Area Cost Chart (Pure dynamic vector SVG) */}
                <div className="chart-card">
                  <div className="chart-header">
                    <div className="chart-title">Daily Cost Trend by Top Services</div>
                    <div className="chart-legend" style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'flex-end' }}>
                      {topServices.map((serviceName: string, idx: number) => {
                        const colors = ['var(--color-primary)', 'var(--color-tertiary)', '#FFFFFF', '#FFB300', '#E040FB'];
                        const color = colors[idx % colors.length];
                        return (
                          <div key={serviceName} className="legend-item" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span className="legend-color" style={{ backgroundColor: color, display: 'inline-block', width: '10px', height: '10px', borderRadius: '2px' }}></span>
                            {serviceName}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Vector graph */}
                  <div style={{ position: 'relative', height: '260px', width: '100%', padding: '0 5px' }}>
                    <svg viewBox="0 0 700 220" width="100%" height="100%" style={{ overflow: 'visible' }}>
                      {/* Rotated Y-Axis Label */}
                      <text 
                        x="8" 
                        y="120" 
                        fill="var(--color-text-secondary)" 
                        fontFamily="var(--font-mono)" 
                        fontSize="9" 
                        fontWeight="600" 
                        letterSpacing="0.05em" 
                        transform="rotate(-90, 8, 120)" 
                        textAnchor="middle"
                      >
                        Daily cost
                      </text>

                      {/* Grid Lines & Dynamic Y-Axis Labels */}
                      {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
                        const y = 200 - ratio * 185;
                        const labelVal = ratio * maxY;
                        const labelStr = labelVal >= 1000 
                          ? `${currencySymbol}${(labelVal / 1000).toFixed(1)}k`
                          : `${currencySymbol}${labelVal.toFixed(2)}`;
                        return (
                          <g key={ratio} opacity="0.8">
                            <line 
                              x1="50" 
                              y1={y} 
                              x2="690" 
                              y2={y} 
                              stroke="rgba(255,255,255,0.06)" 
                              strokeDasharray={ratio === 0 ? "none" : "3 3"} 
                            />
                            <text 
                              x="43" 
                              y={y + 3} 
                              fill="var(--color-text-muted)" 
                              fontFamily="var(--font-mono)" 
                              fontSize="9" 
                              textAnchor="end"
                            >
                              {labelStr}
                            </text>
                          </g>
                        );
                      })}

                      {/* Dynamic Services curves & areas (Renders in reverse order for stacked area overlap in background) */}
                      {hasSpikes && [...topServices].reverse().map((serviceName: string) => {
                        const idx = topServices.indexOf(serviceName);
                        const colors = ['var(--color-primary)', 'var(--color-tertiary)', '#FFFFFF', '#FFB300', '#E040FB'];
                        const glowColors = ['rgba(0, 245, 155, 0.25)', 'rgba(0, 229, 255, 0.25)', 'rgba(255, 255, 255, 0.2)', 'rgba(255, 179, 0, 0.25)', 'rgba(224, 64, 251, 0.25)'];
                        const color = colors[idx % colors.length];
                        const glow = glowColors[idx % glowColors.length];
                        return (
                          <g key={serviceName}>
                            <path 
                              d={getAreaPath(serviceName)} 
                              fill={glow.replace('0.25', '0.03')} 
                            />
                            <path 
                              d={getPath(serviceName)} 
                              fill="none" 
                              stroke={color} 
                              strokeWidth="2" 
                              style={{ filter: `drop-shadow(0 0 6px ${glow})` }}
                            />
                          </g>
                        );
                      })}

                      {/* Daily Stacked Cost Bars (Renders in front of area curves to keep colors vibrant) */}
                      {hasSpikes && recentSpikes.map((d: any, i: number) => {
                        const x = (i / (recentSpikes.length - 1)) * 645 + 45;
                        const barWidth = Math.max(645 / recentSpikes.length * 0.4, 4);
                        let currentY = 200;
                        return topServices.map((serviceName: string, serviceIdx: number) => {
                          const colors = ['var(--color-primary)', 'var(--color-tertiary)', '#FFFFFF', '#FFB300', '#E040FB'];
                          const color = colors[serviceIdx % colors.length];
                          const val = d[serviceName] || 0;
                          if (val <= 0) return null;
                          const barHeight = (val / maxY) * 185;
                          const y = currentY - barHeight;
                          currentY = y;
                          return (
                            <rect 
                              key={`${i}-${serviceName}`}
                              x={x - barWidth / 2}
                              y={y}
                              width={barWidth}
                              height={barHeight}
                              fill={color}
                              opacity="0.45"
                              rx="1"
                            />
                          );
                        });
                      })}

                      {/* Pulsing indicator node on the Spike Day */}
                      {hasSpikes && maxIdx !== -1 && (
                        <>
                          <circle cx={maxDotX} cy={maxDotY} r="5" fill={maxColor} style={{ filter: `drop-shadow(0 0 8px ${maxColor})` }} />
                          <circle cx={maxDotX} cy={maxDotY} r="9" fill="none" stroke={maxColor} strokeWidth="1" opacity="0.6" />
                        </>
                      )}

                      {/* X Axis Labels */}
                      {hasSpikes ? (
                        recentSpikes.map((d: any, i: number) => {
                          if (!shouldShowLabel(i)) return null
                          const x = (i / (recentSpikes.length - 1)) * 645 + 45
                          const isMax = i === maxIdx
                          return (
                            <text 
                              key={i} 
                              x={x} 
                              y="218" 
                              fill={isMax ? 'var(--color-error)' : 'var(--color-text-muted)'} 
                              fontFamily="var(--font-mono)" 
                              fontSize="10"
                              textAnchor="middle"
                              fontWeight={isMax ? '600' : 'normal'}
                            >
                              {formatLocalDate(d.date)}
                            </text>
                          )
                        })
                      ) : (
                        <>
                          <text x="45" y="218" fill="var(--color-text-muted)" fontFamily="var(--font-mono)" fontSize="10">No Data</text>
                          <text x="690" y="218" fill="var(--color-text-muted)" fontFamily="var(--font-mono)" fontSize="10" textAnchor="end">No Data</text>
                        </>
                      )}
                    </svg>
                  </div>
                </div>

                {/* GCP Zombie Assets & Waste Finder */}
                <div id="zombie-assets-card" className="table-card" style={{ scrollMarginTop: '20px', marginTop: '24px' }}>
                  <div className="table-header flex-between">
                    <div>
                      <div className="table-title">GCP Zombie Assets & Waste Finder</div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                        Operational infrastructure scanner identifying orphans using metadata joins between CAI and BigQuery billing tables.
                      </div>
                    </div>
                    <span className="status-pill" style={{ color: 'var(--color-tertiary)', background: 'rgba(0, 229, 255, 0.08)', borderColor: 'rgba(0, 229, 255, 0.2)' }}>
                      {recommendationsData.length} Assets Found
                    </span>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '16px' }}>
                    {recommendationsData.length === 0 ? (
                      <div style={{ 
                        display: 'flex', 
                        flexDirection: 'column', 
                        alignItems: 'center', 
                        justifyContent: 'center', 
                        padding: '40px 20px', 
                        background: 'rgba(255,255,255,0.01)', 
                        borderRadius: '8px', 
                        border: '1px dashed rgba(255,255,255,0.08)',
                        textAlign: 'center'
                      }}>
                        <CheckCircle2 size={36} className="text-glow-emerald" style={{ color: 'var(--color-primary)', marginBottom: '12px' }} />
                        <h4 style={{ fontSize: '15px', fontWeight: '700', color: '#FFFFFF', marginBottom: '6px' }}>Your GCP Footprint is Clean!</h4>
                        <p style={{ fontSize: '12px', color: 'var(--color-text-secondary)', maxWidth: '450px', lineHeight: '1.5' }}>
                          No zombie assets (unattached persistent disks or idle static IP addresses) were detected. Your infrastructure footprint is fully optimised.
                        </p>
                      </div>
                    ) : (
                      recommendationsData.map((zombie: any) => {
                        const zId = getResourceId(zombie);
                        const zName = getShortName(zombie);
                        const zType = getResourceType(zombie);
                        const zProj = getProjectName(zombie);

                        return (
                          <div 
                            key={zId} 
                            style={{ 
                              display: 'flex', 
                              justifyContent: 'space-between', 
                              alignItems: 'center', 
                              background: 'rgba(255, 255, 255, 0.01)', 
                              padding: '16px 20px', 
                              borderRadius: '8px', 
                              border: '1px solid rgba(255,255,255,0.03)',
                              transition: 'all 0.3s ease'
                            }}
                          >
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                                <span style={{ 
                                  fontSize: '10px', 
                                  fontWeight: '700', 
                                  background: 'rgba(0, 245, 155, 0.08)', 
                                  color: 'var(--color-primary)',
                                  padding: '2px 6px', 
                                  borderRadius: '4px',
                                  fontFamily: 'var(--font-mono)'
                                }}>
                                  {getResourceStatus(zombie)}
                                </span>
                                <div style={{ fontWeight: '700', color: '#FFFFFF', fontSize: '14px' }}>{zName}</div>
                              </div>
                              <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                                <div>Type: <span style={{ color: '#FFFFFF' }}>{zType}</span></div>
                                <div>Size: <span style={{ color: '#FFFFFF' }}>{getResourceSize(zombie)}</span></div>
                                <div>Project: <span style={{ color: 'var(--color-tertiary)', fontFamily: 'var(--font-mono)' }}>{zProj}</span></div>
                              </div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                              <div style={{ textAlign: 'right' }}>
                                <div style={{ color: 'var(--color-primary)', fontWeight: '700', fontSize: '16px', fontFamily: 'var(--font-mono)' }}>
                                  {currencySymbol}{Number(zombie.cost ?? 0).toFixed(2)}/mo
                                </div>
                                <div style={{ fontSize: '10px', color: 'var(--color-text-muted)' }}>Immediate Saving</div>
                              </div>

                              <button 
                                className="btn-action" 
                                style={{ 
                                  borderColor: 'var(--color-primary)', 
                                  color: 'var(--color-primary)',
                                  backgroundColor: 'rgba(0, 245, 155, 0.04)',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '6px',
                                  padding: '6px 12px',
                                  borderRadius: '6px',
                                  cursor: 'pointer',
                                  transition: 'all 0.2s ease',
                                  fontSize: '12px'
                                }}
                                onClick={() => {
                                  let prompt = `Give me cost optimisation recommendations for the ${zType} "${zName}" in project "${zProj}". `;
                                  prompt += `Please cross-reference with official GCP architectural guidelines and cost best practices using our Developer Knowledge base.`;
                                  handleSendMessage(prompt);
                                }}
                              >
                                <Sparkles size={12} />
                                <span>Get Recommendations</span>
                              </button>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* GCP Cross-Project Cost Explorer */}
                <div id="cost-explorer-card" className="table-card" style={{ scrollMarginTop: '20px', marginTop: '24px' }}>
                  <div className="table-header flex-between">
                    <div>
                      <div className="table-title">GCP Cross-Project Billing Explorer</div>
                      <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                        Interactive pivot table retrieved directly from standard BigQuery export tables. Click headers to sort.
                      </div>
                    </div>
                    <button 
                      className="btn-action"
                      style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
                      onClick={() => handleSendMessage("Show my top 3 cost drivers")}
                    >
                      <RefreshCw size={12} />
                      Refresh from BQ
                    </button>
                  </div>
                  
                  <table className="cyber-table" style={{ marginTop: '16px' }}>
                    <thead>
                      <tr>
                        {showProjectColumn && <th onClick={() => requestSort('project')} style={{ cursor: 'pointer' }}>GCP Project ID</th>}
                        <th onClick={() => requestSort('service')} style={{ cursor: 'pointer' }}>GCP Service</th>
                        <th onClick={() => requestSort('cost')} style={{ cursor: 'pointer', textAlign: 'right' }}>Cost (MTD)</th>
                        <th onClick={() => requestSort('change')} style={{ cursor: 'pointer', textAlign: 'right' }}>Change (MoM)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {getSortedData(explorerData).map((row, idx) => (
                        <tr key={idx}>
                          {showProjectColumn && <td style={{ fontFamily: 'var(--font-mono)', color: '#FFFFFF' }}>{row.project}</td>}
                          <td>{row.service}</td>
                          <td style={{ fontFamily: 'var(--font-mono)', textAlign: 'right', fontWeight: '600' }} className="text-glow-teal">
                            {currencySymbol}{Number(row.cost ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                          <td style={{ textAlign: 'right', fontWeight: '600' }} className={Number(row.change ?? 0) > 0 ? 'text-glow-red' : 'text-glow-emerald'}>
                            {Number(row.change ?? 0) > 0 ? '+' : ''}{Number(row.change ?? 0)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Embedded CSS animation class for spins */}
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
