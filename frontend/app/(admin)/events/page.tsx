'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useMemo } from 'react'
import { useTranslations } from 'next-intl'
import AuthGuard from '@/components/AuthGuard'
import { useAuth } from '@/lib/auth'
import { fetchDashboardSnapshot } from '@/lib/api/automation'
import { DateRangeFilter } from '@/components/shared'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

// -----------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------

type EventLevel = 'INFO' | 'WARNING' | 'ALERT' | 'CRITICAL' | 'EMERGENCY'

interface MonitoringEvent {
  id: string
  timestamp: string
  level: EventLevel
  component: string
  message: string
  metric_id?: string
  metric_value?: number
  metric_unit?: string
}

// -----------------------------------------------------------------------
// Mock data builder (message strings resolved at render time via t())
// -----------------------------------------------------------------------

// -----------------------------------------------------------------------
// Level styles
// -----------------------------------------------------------------------

const LEVEL_STYLES: Record<EventLevel, { badge: string; dot: string; label: string }> = {
  INFO: {
    badge: 'bg-gray-100 dark:bg-gray-800 text-gray-700 border-gray-200 dark:border-gray-700',
    dot: 'bg-gray-400',
    label: 'INFO',
  },
  WARNING: {
    badge: 'bg-yellow-100 text-yellow-700 border-yellow-200',
    dot: 'bg-yellow-400',
    label: 'WARNING',
  },
  ALERT: {
    badge: 'bg-orange-100 text-orange-700 border-orange-200',
    dot: 'bg-orange-400',
    label: 'ALERT',
  },
  CRITICAL: {
    badge: 'bg-red-100 text-red-700 border-red-200',
    dot: 'bg-red-500',
    label: 'CRITICAL',
  },
  EMERGENCY: {
    badge: 'bg-red-200 text-red-900 border-red-300 animate-pulse',
    dot: 'bg-red-700 animate-pulse',
    label: 'EMERGENCY',
  },
}

const ALL_LEVELS: EventLevel[] = ['INFO', 'WARNING', 'ALERT', 'CRITICAL', 'EMERGENCY']

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo' })
}

function extractEvents(data: unknown): MonitoringEvent[] {
  if (!data || typeof data !== 'object') return []
  const obj = data as Record<string, unknown>

  // Try top-level recent_events
  if (Array.isArray(obj.recent_events)) {
    return obj.recent_events as MonitoringEvent[]
  }
  // Try status.recent_events (DashboardSnapshot shape)
  const status = obj.status as Record<string, unknown> | undefined
  if (status && Array.isArray(status.recent_events)) {
    return status.recent_events as MonitoringEvent[]
  }
  return []
}

// -----------------------------------------------------------------------
// Main page content
// -----------------------------------------------------------------------

function EventsContent() {
  const t = useTranslations('AdminEvents')
  const { token } = useAuth()

  const MOCK_EVENTS: MonitoringEvent[] = [
    {
      id: 'evt-001',
      timestamp: '2026-03-22T10:45:00Z',
      level: 'EMERGENCY',
      component: 'RuleEngine',
      message: t('mockMsg1'),
      metric_id: 'health_factor',
      metric_value: 1.42,
      metric_unit: '',
    },
    {
      id: 'evt-002',
      timestamp: '2026-03-22T10:30:00Z',
      level: 'CRITICAL',
      component: 'AaveClient',
      message: t('mockMsg2'),
      metric_id: 'health_factor',
      metric_value: 1.55,
      metric_unit: '',
    },
    {
      id: 'evt-003',
      timestamp: '2026-03-22T09:15:00Z',
      level: 'ALERT',
      component: 'ExchangeService',
      message: t('mockMsg3'),
      metric_id: 'daily_trades_used',
      metric_value: 24,
      metric_unit: t('mockUnit'),
    },
    {
      id: 'evt-004',
      timestamp: '2026-03-22T08:50:00Z',
      level: 'WARNING',
      component: 'AIJudge',
      message: t('mockMsg4'),
      metric_id: 'latency_ms',
      metric_value: 5200,
      metric_unit: 'ms',
    },
    {
      id: 'evt-005',
      timestamp: '2026-03-22T08:00:00Z',
      level: 'INFO',
      component: 'AutomationWorkflow',
      message: t('mockMsg5'),
      metric_id: 'order_usd',
      metric_value: 150,
      metric_unit: 'USD',
    },
    {
      id: 'evt-006',
      timestamp: '2026-03-22T07:30:00Z',
      level: 'INFO',
      component: 'KnowledgeService',
      message: t('mockMsg6'),
      metric_id: 'chunks_added',
      metric_value: 12,
      metric_unit: t('mockUnit'),
    },
    {
      id: 'evt-007',
      timestamp: '2026-03-21T23:00:00Z',
      level: 'WARNING',
      component: 'RuleEngine',
      message: t('mockMsg7'),
    },
    {
      id: 'evt-008',
      timestamp: '2026-03-21T18:45:00Z',
      level: 'INFO',
      component: 'AaveClient',
      message: t('mockMsg8'),
      metric_id: 'deposited_usdc',
      metric_value: 500,
      metric_unit: 'USDC',
    },
  ]

  const [events, setEvents] = useState<MonitoringEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [usingMock, setUsingMock] = useState(false)

  // Filters
  const [selectedLevels, setSelectedLevels] = useState<Set<EventLevel>>(new Set(ALL_LEVELS))
  const [selectedComponent, setSelectedComponent] = useState<string>('ALL')
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | 'all'>('all')

  // Detail modal
  const [selectedEvent, setSelectedEvent] = useState<MonitoringEvent | null>(null)

  const fetchData = async () => {
    try {
      const snapshot = await fetchDashboardSnapshot(24, token ?? undefined)
      const extracted = extractEvents(snapshot)
      if (extracted.length > 0) {
        setEvents(extracted)
        setUsingMock(false)
      } else {
        setEvents(MOCK_EVENTS)
        setUsingMock(true)
      }
      setLastUpdated(new Date())
    } catch {
      setEvents(MOCK_EVENTS)
      setUsingMock(true)
      setLastUpdated(new Date())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30_000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  // Unique component list
  const components = useMemo(() => {
    const unique = Array.from(new Set(events.map((e) => e.component))).sort()
    return ['ALL', ...unique]
  }, [events])

  // Filtered events
  const filteredEvents = useMemo(() => {
    return events
      .filter((e) => selectedLevels.has(e.level))
      .filter((e) => selectedComponent === 'ALL' || e.component === selectedComponent)
      .filter((e) => {
        if (dateRange === 'all') return true
        const ts = new Date(e.timestamp)
        return ts >= dateRange.from && ts <= dateRange.to
      })
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
  }, [events, selectedLevels, selectedComponent, dateRange])

  const toggleLevel = (level: EventLevel) => {
    setSelectedLevels((prev) => {
      const next = new Set(prev)
      if (next.has(level)) {
        next.delete(level)
      } else {
        next.add(level)
      }
      return next
    })
  }

  return (
    <>
      <title>{t('browserTitle')}</title>
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{t('pageTitle')}</h1>
          <p className="mt-1 text-sm text-gray-500">
            {t('pageSubtitle')}
          </p>
        </div>
        <div className="text-right text-xs text-gray-400">
          {lastUpdated && (
            <span>{t('lastUpdated', { time: lastUpdated.toLocaleTimeString('ja-JP') })}</span>
          )}
          {usingMock && (
            <div className="mt-1 rounded bg-yellow-50 px-2 py-1 text-yellow-600">
              {t('mockDataNotice')}
            </div>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm space-y-4">
        {/* Level checkboxes */}
        <div className="flex flex-wrap items-center gap-4">
          <span className="text-sm font-medium text-gray-700 min-w-[4rem]">{t('filterLevel')}</span>
          {ALL_LEVELS.map((level) => {
            const style = LEVEL_STYLES[level]
            return (
              <label key={level} className="flex items-center gap-1.5 cursor-pointer select-none">
                <Checkbox
                  checked={selectedLevels.has(level)}
                  onCheckedChange={() => toggleLevel(level)}
                  className="h-4 w-4"
                />
                <Badge
                  variant="outline"
                  className={`text-xs font-semibold px-2 py-0.5 ${style.badge}`}
                >
                  {style.label}
                </Badge>
              </label>
            )
          })}
        </div>

        {/* Component select + Date range */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-700">{t('filterComponent')}</span>
            <Select value={selectedComponent} onValueChange={setSelectedComponent}>
              <SelectTrigger className="h-8 w-48 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {components.map((c) => (
                  <SelectItem key={c} value={c} className="text-xs">
                    {c === 'ALL' ? t('componentAll') : c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-700">{t('filterDateRange')}</span>
            <DateRangeFilter onChange={setDateRange} presets />
          </div>
        </div>
      </div>

      {/* Results count */}
      <div className="text-sm text-gray-500">
        {loading ? t('loading') : t('resultCount', { count: filteredEvents.length })}
      </div>

      {/* Timeline */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <div className="text-center space-y-2">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 dark:border-gray-700 border-t-blue-500 mx-auto" />
            <p className="text-sm">{t('loading')}</p>
          </div>
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-gray-400">
          <p className="text-sm">{t('noResults')}</p>
        </div>
      ) : (
        <div className="relative">
          {/* Vertical timeline line */}
          <div className="absolute left-5 top-0 bottom-0 w-px bg-gray-200" />

          <div className="space-y-4">
            {filteredEvents.map((event) => {
              const style = LEVEL_STYLES[event.level]
              return (
                <div key={event.id} className="relative flex gap-4">
                  {/* Timeline dot */}
                  <div className="relative z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center">
                    <span className={`h-3 w-3 rounded-full ${style.dot}`} />
                  </div>

                  {/* Card */}
                  <div
                    className="flex-1 cursor-pointer rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 shadow-sm transition-all hover:border-gray-300 hover:shadow-md"
                    onClick={() => setSelectedEvent(event)}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge
                          variant="outline"
                          className={`text-xs font-bold px-2 py-0.5 ${style.badge}`}
                        >
                          {style.label}
                        </Badge>
                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                          {event.component}
                        </span>
                      </div>
                      <time className="text-xs text-gray-400 flex-shrink-0">
                        {formatTimestamp(event.timestamp)}
                      </time>
                    </div>
                    <p className="mt-2 text-sm text-gray-600 line-clamp-2">{event.message}</p>
                    {(event.metric_id != null || event.metric_value != null) && (
                      <div className="mt-2 flex items-center gap-1 text-xs text-gray-400">
                        {event.metric_id && <span>{event.metric_id}:</span>}
                        {event.metric_value != null && (
                          <span className="font-mono font-semibold text-gray-600">
                            {event.metric_value}
                            {event.metric_unit ? ` ${event.metric_unit}` : ''}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Detail Modal */}
      <Dialog open={selectedEvent !== null} onOpenChange={(open) => !open && setSelectedEvent(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedEvent && (
                <>
                  <Badge
                    variant="outline"
                    className={`text-xs font-bold px-2 py-0.5 ${LEVEL_STYLES[selectedEvent.level].badge}`}
                  >
                    {LEVEL_STYLES[selectedEvent.level].label}
                  </Badge>
                  <span>{t('detailTitle')}</span>
                </>
              )}
            </DialogTitle>
          </DialogHeader>

          {selectedEvent && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-[7rem_1fr] gap-y-3 gap-x-2">
                <span className="font-medium text-gray-500">{t('detailFieldId')}</span>
                <span className="font-mono text-xs text-gray-700">{selectedEvent.id}</span>

                <span className="font-medium text-gray-500">{t('detailFieldTimestamp')}</span>
                <span className="text-gray-700">{formatTimestamp(selectedEvent.timestamp)}</span>

                <span className="font-medium text-gray-500">{t('detailFieldLevel')}</span>
                <span className="text-gray-700">{selectedEvent.level}</span>

                <span className="font-medium text-gray-500">{t('detailFieldComponent')}</span>
                <span className="text-gray-700">{selectedEvent.component}</span>

                <span className="font-medium text-gray-500">{t('detailFieldMessage')}</span>
                <span className="text-gray-700 whitespace-pre-wrap">{selectedEvent.message}</span>

                {selectedEvent.metric_id && (
                  <>
                    <span className="font-medium text-gray-500">{t('detailFieldMetricId')}</span>
                    <span className="font-mono text-xs text-gray-700">{selectedEvent.metric_id}</span>
                  </>
                )}

                {selectedEvent.metric_value != null && (
                  <>
                    <span className="font-medium text-gray-500">{t('detailFieldMetricValue')}</span>
                    <span className="font-mono font-semibold text-gray-700">
                      {selectedEvent.metric_value}
                      {selectedEvent.metric_unit ? ` ${selectedEvent.metric_unit}` : ''}
                    </span>
                  </>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
    </>
  )
}

export default function EventsPage() {
  return (
    <AuthGuard adminOnly>
      <EventsContent />
    </AuthGuard>
  )
}
