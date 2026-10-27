import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  formatDateRange,
  formatPercent,
  getLastDaysRange,
  getSeriesRange,
} from './format'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllEnvs()
})

describe('getLastDaysRange', () => {
  it.each([
    ['2026-03-09T04:30:00Z', 'America/New_York', '2026-03-09', '2026-02-24'],
    ['2026-11-03T04:30:00Z', 'America/New_York', '2026-11-02', '2026-10-20'],
    ['2026-03-30T22:30:00Z', 'Europe/Berlin', '2026-03-31', '2026-03-18'],
    ['2026-10-26T22:30:00Z', 'Europe/Berlin', '2026-10-26', '2026-10-13'],
    ['2026-10-05T13:30:00Z', 'Australia/Sydney', '2026-10-06', '2026-09-23'],
    ['2026-04-06T13:30:00Z', 'Australia/Sydney', '2026-04-06', '2026-03-24'],
    ['2026-10-05T13:15:00Z', 'Australia/Lord_Howe', '2026-10-06', '2026-09-23'],
    ['2026-04-06T13:15:00Z', 'Australia/Lord_Howe', '2026-04-06', '2026-03-24'],
    ['2026-06-15T16:00:00Z', 'America/New_York', '2026-06-15', '2026-06-02'],
    ['2026-03-09T04:30:00Z', 'Asia/Shanghai', '2026-03-09', '2026-02-24'],
    ['2026-03-09T04:30:00Z', 'UTC', '2026-03-09', '2026-02-24'],
    ['2026-01-03T00:30:00Z', 'UTC', '2026-01-03', '2025-12-21'],
    ['2024-03-01T00:30:00Z', 'UTC', '2024-03-01', '2024-02-17'],
  ])(
    'includes 14 calendar dates at %s in %s',
    (now, timeZone, endDate, startDate) => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date(now))

      expect(getLastDaysRange(14, timeZone)).toEqual({ endDate, startDate })
    },
  )

  it.each([
    [1, '2026-03-09'],
    [365, '2025-03-10'],
  ])(
    'includes %i calendar dates for the dashboard ranges',
    (days, startDate) => {
      vi.useFakeTimers()
      vi.setSystemTime(new Date('2026-03-09T04:30:00Z'))

      expect(getLastDaysRange(days, 'America/New_York')).toEqual({
        endDate: '2026-03-09',
        startDate,
      })
    },
  )

  it('uses the viewer timezone when no timezone is supplied', () => {
    vi.stubEnv('TZ', 'America/New_York')
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-09T04:30:00Z'))

    expect(getLastDaysRange(14)).toEqual({
      endDate: '2026-03-09',
      startDate: '2026-02-24',
    })
  })
})

describe('getSeriesRange', () => {
  it('prefers the range the server reported', () => {
    expect(
      getSeriesRange({ end_date: '2026-10-27', start_date: '2026-10-14' }, 3),
    ).toEqual({ endDate: '2026-10-27', startDate: '2026-10-14' })
  })

  it('falls back to the requested last days', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-27T12:00:00Z'))
    expect(getSeriesRange(undefined, 14)).toEqual(getLastDaysRange(14))
  })
})

describe('formatDateRange', () => {
  it('formats a localized range instead of raw date keys', () => {
    const label = formatDateRange('2026-10-14', '2026-10-27')
    expect(label).not.toContain('2026-10-14')
    expect(label).toContain('2026')
    expect(label).toContain('14')
    expect(label).toContain('27')
  })
})

describe('formatPercent', () => {
  it('formats a ratio with at most one decimal', () => {
    expect(formatPercent(0.025)).toBe('2.5%')
    expect(formatPercent(0)).toBe('0%')
    expect(formatPercent(undefined)).toBe('0%')
  })
})
