import type {
  OvDisabledResult,
  OvMaybeDisabled,
  PaginatedResult,
} from '../../common'

export type ConsoleContextCounts = {
  files?: number
  memories?: number
  skills?: number
  total?: number
}

export type ConsoleTokenCounts = {
  embedding_input?: number
  total?: number
  vlm_input?: number
  vlm_output?: number
}

export type ConsoleTokensPerMinute = ConsoleTokenCounts & {
  window_minutes?: number
}

export type ConsoleRetrievalCounts = {
  find?: number
  search?: number
  total?: number
}

export type ConsoleDashboardSummaryResult = OvMaybeDisabled & {
  context_counts?: ConsoleContextCounts
  today_retrievals?: ConsoleRetrievalCounts
  today_tokens?: ConsoleTokenCounts
  tokens_per_minute?: ConsoleTokensPerMinute
}

export type ConsoleSeriesBucket = 'day' | '4h' | (string & {})

export type ConsoleSeriesQuery = {
  bucket?: ConsoleSeriesBucket
  end_date: string
  start_date: string
  timezone?: string | null
}

export type ConsoleDashboardSummaryQuery = {
  timezone?: string | null
}

export type ConsoleSeriesResult<TItem> = OvMaybeDisabled & {
  bucket?: string
  end_date?: string
  items?: TItem[]
  start_date?: string
}

export type ConsoleTokenSeriesItem = {
  date?: string
  embedding_input?: number
  total?: number
  vlm_input?: number
  vlm_output?: number
}

export type ConsoleTokenSeriesResult = ConsoleSeriesResult<ConsoleTokenSeriesItem>

export type ConsoleTokenRateWindow = '1h' | '6h' | '24h' | '7d'

/** Average tokens per minute within one bucket, plus its busiest minute. */
export type ConsoleTokenRateItem = ConsoleTokenCounts & {
  peak_total?: number
  start?: string
}

export type ConsoleTokenRatePeak = ConsoleTokenCounts & {
  minute?: string
}

export type ConsoleTokenRateResult = OvMaybeDisabled & {
  average_total?: number
  bucket_minutes?: number
  end?: string
  items?: ConsoleTokenRateItem[]
  peak?: ConsoleTokenRatePeak | null
  start?: string
  window?: ConsoleTokenRateWindow
}

export type ConsoleContextCommitItem = {
  add_resource?: number
  add_skill?: number
  date?: string
  hour?: number
  session_add_message?: number
  session_commit?: number
  total?: number
}

export type ConsoleContextCommitsResult = ConsoleSeriesResult<ConsoleContextCommitItem>

export type ConsoleAuditLogItem = {
  account_id?: string | null
  api_type?: string
  created_at?: string
  duration_ms?: number
  error_code?: string | null
  error_details?: Record<string, unknown> | null
  error_message?: string | null
  method?: string
  request_id?: string | null
  route?: string
  status_code?: number
  user_id?: string | null
}

export type ConsoleAuditResult = OvMaybeDisabled & PaginatedResult<ConsoleAuditLogItem> & {
  success_rate?: number
}

export type ConsoleAuditQuery = {
  api_type?: string[] | null
  page?: number
  page_size?: number
  request_id?: string | null
  status?: string[] | null
}

export type ConsoleDisabledResult = OvDisabledResult
