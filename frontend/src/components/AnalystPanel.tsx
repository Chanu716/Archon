import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

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
  
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom of answer
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [parsedAnswer])

  // Try to extract fields from partial JSON
  useEffect(() => {
    if (!streamedRawJson) return
    
    // Very naive partial JSON extraction for smooth UX while streaming
    // A robust app would use a streaming JSON parser (e.g., partial-json)
    try {
      // Attempt full parse first
      const fullObj = JSON.parse(streamedRawJson)
      if (fullObj.answer) setParsedAnswer(fullObj.answer)
      if (fullObj.confidence) setParsedConfidence(fullObj.confidence)
      if (fullObj.referenced_evidence_ids) setParsedCitations(fullObj.referenced_evidence_ids)
    } catch (e) {
      // If partial, try regex extraction for answer
      const answerMatch = streamedRawJson.match(/"answer"\s*:\s*"([^]*)/)
      if (answerMatch) {
        // Strip out trailing incomplete JSON bits if any
        let partialText = answerMatch[1]
        
        // Remove trailing quotes and slashes if it looks cut off
        partialText = partialText.replace(/\\n/g, '\n').replace(/\\"/g, '"')
        
        // Very rough cutoff fix for display
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
      const response = await fetch(`http://localhost:8000/api/v1/repositories/${repoId}/analyst/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
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
        if (value) {
          const chunk = decoder.decode(value, { stream: true })
          const lines = chunk.split('\n')
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.substring(6)
              if (dataStr.trim() === '[DONE]') {
                done = true
                break
              }
              try {
                const dataObj = JSON.parse(dataStr)
                if (dataObj.error) {
                  setError(dataObj.error)
                  break
                }
                if (dataObj.trace) {
                  setTraces(prev => [...prev, dataObj.trace])
                }
                if (dataObj.content) {
                  buffer += dataObj.content
                  setStreamedRawJson(buffer)
                }
              } catch (err) {
                console.error("Failed to parse SSE data chunk", dataStr)
              }
            }
          }
        }
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setIsAnalyzing(false)
    }
  }

  return (
    <div className="w-96 bg-gray-950 border-l border-gray-700 flex flex-col h-full overflow-hidden absolute right-0 z-30 shadow-2xl">
      <div className="p-4 border-b border-gray-800 flex justify-between items-center bg-gray-900">
        <h2 className="text-white font-bold text-sm flex items-center gap-2">
          <span className="text-blue-500">⚡</span> Archon Analyst
        </h2>
        <button onClick={onClose} className="text-gray-500 hover:text-white flex-shrink-0 text-lg leading-none">✕</button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {traces.length > 0 && (
          <div className="bg-gray-900 border border-gray-800 rounded p-2 text-xs font-mono text-gray-500 mb-4 space-y-1">
            {traces.map((trace, idx) => (
              <div key={idx} className="flex gap-2">
                <span>{trace.startsWith('✓') ? '✓' : trace.startsWith('⚠️') ? '⚠️' : '·'}</span>
                <span className="text-gray-400">{trace.replace(/^[✓⚠️]\s*/, '')}</span>
              </div>
            ))}
          </div>
        )}
        
        {parsedAnswer ? (
          <div className="text-gray-300 text-sm leading-relaxed">
            <ReactMarkdown
              components={{
                a: ({ node, ...props }) => <span className="text-blue-400 font-mono cursor-pointer hover:underline" {...props} />
              }}
            >
              {parsedAnswer}
            </ReactMarkdown>
            
            {/* Confidence & Citations when done streaming */}
            {!isAnalyzing && parsedConfidence && (
              <div className="mt-6 pt-4 border-t border-gray-800">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs text-gray-500 uppercase font-semibold">Evidence Confidence</span>
                  <span className={`text-xs px-2 py-0.5 rounded font-mono ${
                    parsedConfidence === 'HIGH' ? 'bg-green-900/40 text-green-400' :
                    parsedConfidence === 'MEDIUM' ? 'bg-yellow-900/40 text-yellow-400' :
                    'bg-orange-900/40 text-orange-400'
                  }`}>
                    {parsedConfidence}
                  </span>
                </div>
                
                {parsedCitations.length > 0 && (
                  <div className="mt-4">
                    <span className="text-xs text-gray-500 uppercase font-semibold block mb-2">Referenced Evidence</span>
                    <div className="flex flex-wrap gap-2">
                      {parsedCitations.map(cit => (
                        <span key={cit} className="text-xs font-mono bg-gray-800 text-gray-400 px-2 py-1 rounded border border-gray-700">
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
          <div className="h-full flex flex-col items-center justify-center text-center opacity-60">
            <div className="text-4xl mb-4">🤖</div>
            <p className="text-gray-400 text-sm max-w-xs">Ask me anything about this repository's structure, history, metrics, or semantics.</p>
          </div>
        )}

        {isAnalyzing && !parsedAnswer && (
          <div className="text-blue-400 text-sm animate-pulse text-center mt-8">
            Retrieving evidence...
          </div>
        )}

        {error && (
          <div className="p-3 bg-red-900/30 border border-red-800/50 rounded text-red-400 text-xs">
            {error}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-gray-800 bg-gray-900">
        <form onSubmit={handleAsk} className="flex flex-col gap-2">
          <textarea
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder="e.g. How does authentication work?"
            className="w-full bg-gray-950 border border-gray-700 text-gray-200 text-sm rounded px-3 py-2 focus:outline-none focus:border-blue-500 placeholder-gray-600 resize-none h-20"
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
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors self-end w-full"
          >
            {isAnalyzing ? 'Analyzing...' : 'Ask Analyst'}
          </button>
        </form>
      </div>
    </div>
  )
}
