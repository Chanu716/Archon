import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { Zap, X, Terminal, ArrowRight, Bot } from 'lucide-react'

interface AnalystPanelProps {
  repoId: string
  snapshotId?: string
  onClose: () => void
}

export default function AnalystPanel({ repoId, onClose }: AnalystPanelProps) {
  const [question, setQuestion] = useState('')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  
  const [streamedRawJson, setStreamedRawJson] = useState('')
  const [parsedAnswer, setParsedAnswer] = useState('')
  const [parsedConfidence, setParsedConfidence] = useState('')
  const [parsedCitations, setParsedCitations] = useState<string[]>([])
  const [traces, setTraces] = useState<string[]>([])
  
  const [provider, setProvider] = useState<'groq' | 'gemini' | 'openrouter'>('gemini')
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [parsedAnswer])

  useEffect(() => {
    if (!streamedRawJson) return
    try {
      const fullObj = JSON.parse(streamedRawJson)
      if (fullObj.answer) setParsedAnswer(fullObj.answer)
      if (fullObj.confidence) setParsedConfidence(fullObj.confidence)
      if (fullObj.referenced_evidence_ids) setParsedCitations(fullObj.referenced_evidence_ids)
    } catch {
      const answerMatch = streamedRawJson.match(/"answer"\s*:\s*"([^]*)/)
      if (answerMatch) {
        let partialText = answerMatch[1]
        partialText = partialText.replace(/\\n/g, '\n').replace(/\\"/g, '"')
        const endQuoteIdx = partialText.lastIndexOf('","')
        if (endQuoteIdx > -1) {
          partialText = partialText.substring(0, endQuoteIdx)
        }
        setParsedAnswer(partialText)
      }
    }
  }, [streamedRawJson])

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!question.trim() || isAnalyzing) return

    setIsAnalyzing(true)
    setError(null)
    setStreamedRawJson('')
    setParsedAnswer('')
    setParsedConfidence('')
    setParsedCitations([])
    setTraces([])

    try {
      const apiBase = import.meta.env.VITE_API_BASE_URL || '/api/v1'
      const response = await fetch(`${apiBase}/repositories/${repoId}/analyst/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, provider })
      })

      if (!response.ok) {
        throw new Error(`API Error: ${response.statusText}`)
      }

      if (!response.body) throw new Error("No response body")

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      
      let done = false
      let buffer = ''

      while (!done) {
        const { value, done: doneReading } = await reader.read()
        done = doneReading
        const chunkValue = decoder.decode(value, { stream: true })
        buffer += chunkValue

        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.slice(6)
            if (dataStr === '[DONE]') {
              done = true
              break
            }
            try {
              const data = JSON.parse(dataStr)
              if (data.trace) {
                setTraces(prev => [...prev, data.trace])
              } else if (data.content) {
                setStreamedRawJson(prev => prev + data.content)
              } else if (data.error) {
                setError(data.error)
              }
            } catch {
              setStreamedRawJson(prev => prev + dataStr)
            }
          }
        }
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred during analysis')
    } finally {
      setIsAnalyzing(false)
    }
  }

  return (
    <div className="w-96 max-w-full bg-black border-l-2 border-white flex flex-col h-full overflow-hidden absolute right-0 top-0 bottom-0 z-30 shadow-pixel font-mono text-xs">
      {/* Header */}
      <div className="p-3 border-b-2 border-white flex flex-col gap-2 bg-neutral-950 flex-shrink-0">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-cyan-400" />
            <h2 className="font-pixel text-[11px] text-white">[ AI_CODE_ANALYST ]</h2>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-white p-1 border border-neutral-800 hover:border-white transition flex-shrink-0 text-xs"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Model Selector */}
        <div className="flex items-center gap-2 pt-1 border-t border-neutral-800">
          <Bot className="w-3 h-3 text-cyan-400 flex-shrink-0" />
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as any)}
            className="w-full pixel-input text-[10px] font-pixel px-2 py-1 bg-black text-cyan-400 border-neutral-700 focus:outline-none focus:border-cyan-400 cursor-pointer"
            title="Select AI Model"
          >
            <option value="gemini">GEMINI :: 3.6-FLASH (FREE / VERIFIED)</option>
            <option value="openrouter">OPENROUTER :: LLAMA-3.3-70B (VERIFIED)</option>
            <option value="groq">GROQ :: LLAMA-3.3-70B</option>
          </select>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 bg-black">
        {traces.length > 0 && (
          <div className="border border-neutral-800 bg-neutral-950 p-2.5 space-y-1 font-mono text-[11px]">
            <div className="font-pixel text-[9px] text-neutral-500 mb-1">[ REASONING_TRACE ]</div>
            {traces.map((trace, idx) => (
              <div key={idx} className="flex items-center gap-2 text-neutral-400">
                <span className="text-cyan-400 font-pixel">›</span>
                <span className="truncate">{trace.replace(/^[✓⚠️]\s*/, '')}</span>
              </div>
            ))}
          </div>
        )}
        
        {parsedAnswer ? (
          <div className="text-neutral-200 text-xs leading-relaxed space-y-3">
            <ReactMarkdown
              components={{
                a: ({ node, ...props }) => <span className="text-cyan-400 font-mono hover:underline" {...props} />,
                code: ({ node, ...props }) => <code className="bg-neutral-900 border border-neutral-800 px-1 py-0.5 text-cyan-300 font-mono text-[11px]" {...props} />,
                p: ({ node, ...props }) => <p className="mb-2" {...props} />,
              }}
            >
              {parsedAnswer}
            </ReactMarkdown>
            
            {!isAnalyzing && parsedConfidence && (
              <div className="mt-4 pt-3 border-t border-neutral-800">
                <div className="flex justify-between items-center mb-2">
                  <span className="font-pixel text-[9px] text-neutral-500">[ CONFIDENCE ]</span>
                  <span className={`text-[10px] px-1.5 py-0.5 font-pixel border ${
                    parsedConfidence === 'HIGH' ? 'border-green-500 text-green-400 bg-green-950' :
                    parsedConfidence === 'MEDIUM' ? 'border-amber-500 text-amber-400 bg-amber-950' :
                    'border-red-500 text-red-400 bg-red-950'
                  }`}>
                    {parsedConfidence}
                  </span>
                </div>
                
                {parsedCitations.length > 0 && (
                  <div className="mt-3">
                    <span className="font-pixel text-[9px] text-neutral-500 block mb-1.5">[ EVIDENCE_CITATIONS ]</span>
                    <div className="flex flex-wrap gap-1.5">
                      {parsedCitations.map(cit => (
                        <span key={cit} className="text-[10px] font-mono bg-neutral-950 text-cyan-400 px-2 py-0.5 border border-neutral-800">
                          [{cit}]
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            
            <div ref={bottomRef} />
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center opacity-60 p-6 space-y-3">
            <Bot className="w-8 h-8 text-cyan-400" />
            <p className="text-neutral-400 text-xs font-mono">
              Query the LLM analyst on structural coupling, dead code, or architecture patterns.
            </p>
          </div>
        )}

        {isAnalyzing && !parsedAnswer && (
          <div className="text-cyan-400 font-pixel text-xs animate-pulse text-center mt-6">
            [ EXECUTING_REASONING_PIPELINE… ]
          </div>
        )}

        {error && (
          <div className="p-2.5 border border-red-500 bg-red-950 text-red-400 text-xs">
            [ERROR] {error}
          </div>
        )}
      </div>

      <div className="p-3 border-t-2 border-white bg-neutral-950 flex-shrink-0">
        <form onSubmit={handleAsk} className="flex flex-col gap-2">
          <textarea
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder="> ask architecture query…"
            className="w-full pixel-input text-xs px-3 py-2 focus:outline-none resize-none h-16"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleAsk(e)
              }
            }}
          />
          <button 
            type="submit" 
            disabled={!question.trim() || isAnalyzing}
            className="pixel-btn-filled-cyan py-1.5 flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            <span>{isAnalyzing ? 'SYNTHESIZING…' : 'QUERY_ANALYST'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>
    </div>
  )
}
