import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { TOKEN_COLORS } from '../-constants/dashboard'
import type {
  HomeT,
  TokenRateItem,
  TokenTrendPayload,
} from '../-types/dashboard'
import { formatNumber, formatTpmTime } from '../-lib/format'

const PEAK_COLOR = 'var(--foreground)'

const SERIES = [
  {
    key: 'vlm_input',
    color: TOKEN_COLORS.input,
    label: 'todayTokens.vlmInput',
  },
  {
    key: 'vlm_output',
    color: TOKEN_COLORS.output,
    label: 'todayTokens.vlmOutput',
  },
  {
    key: 'embedding_input',
    color: TOKEN_COLORS.embedding,
    label: 'todayTokens.embeddingInput',
  },
  {
    key: 'bot_input',
    color: TOKEN_COLORS.botInput,
    label: 'todayTokens.botInput',
  },
  {
    key: 'bot_output',
    color: TOKEN_COLORS.botOutput,
    label: 'todayTokens.botOutput',
  },
  { key: 'rerank', color: TOKEN_COLORS.rerank, label: 'tpmTrend.rerank' },
] as const

export function TpmTrendChart({
  bucketMinutes,
  items,
  t,
}: {
  bucketMinutes: number
  items: Array<Required<TokenRateItem>>
  t: HomeT
}) {
  // One-minute buckets already plot every minute; wider buckets average, so
  // their busiest minute is drawn separately to keep peaks visible.
  const showPeakLine = bucketMinutes > 1
  const withDate = bucketMinutes >= 60
  return (
    <>
      <div className="h-72 min-h-72 min-w-0 w-full">
        <ResponsiveContainer
          width="100%"
          height="100%"
          initialDimension={{ width: 720, height: 288 }}
          minWidth={1}
          minHeight={1}
        >
          <ComposedChart
            data={items}
            margin={{ bottom: 0, left: 0, right: 12, top: 8 }}
          >
            <CartesianGrid
              stroke="currentColor"
              strokeOpacity={0.05}
              vertical={false}
            />
            <XAxis
              axisLine={false}
              className="text-muted-foreground"
              dataKey="start"
              minTickGap={24}
              tick={{ fill: 'currentColor', fontSize: 12 }}
              tickFormatter={(value) => formatTpmTime(String(value), withDate)}
              tickLine={false}
            />
            <YAxis
              axisLine={false}
              className="text-muted-foreground"
              tick={{ fill: 'currentColor', fontSize: 12 }}
              tickFormatter={(value) => formatNumber(Number(value))}
              tickLine={false}
              width="auto"
            />
            <Tooltip
              cursor={{ stroke: 'currentColor', strokeOpacity: 0.12 }}
              content={<TpmTrendTooltip t={t} withDate={withDate} />}
            />
            {SERIES.map((series) => (
              <Area
                key={series.key}
                dataKey={series.key}
                fill={series.color}
                fillOpacity={0.08}
                isAnimationActive={false}
                name={series.key}
                stackId="tpm"
                stroke={series.color}
                strokeWidth={1.5}
                type="monotone"
              />
            ))}
            {showPeakLine ? (
              <Line
                dataKey="peak_total"
                dot={false}
                isAnimationActive={false}
                name="peak_total"
                stroke={PEAK_COLOR}
                strokeDasharray="4 3"
                strokeOpacity={0.6}
                strokeWidth={1.5}
                type="monotone"
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
        {SERIES.map((series) => (
          <LegendMark
            key={series.key}
            color={series.color}
            label={t(series.label)}
          />
        ))}
        {showPeakLine ? (
          <LegendMark
            color={PEAK_COLOR}
            dashed
            label={t('tpmTrend.peakLine')}
          />
        ) : null}
      </div>
    </>
  )
}

function LegendMark({
  color,
  dashed,
  label,
}: {
  color: string
  dashed?: boolean
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={
          dashed ? 'h-0 w-4 border-t-2 border-dashed' : 'size-2.5 rounded-full'
        }
        style={dashed ? { borderColor: color } : { backgroundColor: color }}
      />
      <span>{label}</span>
    </span>
  )
}

function TpmTrendTooltip({
  active,
  label,
  payload,
  t,
  withDate,
}: {
  active?: boolean
  label?: string | number
  payload?: TokenTrendPayload[]
  t: HomeT
  withDate: boolean
}) {
  if (!active || !payload?.length) return null

  const labelForKey = (key: string | undefined) =>
    key === 'peak_total'
      ? t('tpmTrend.peakLine')
      : t(SERIES.find((series) => series.key === key)?.label ?? key ?? '')

  return (
    <div className="min-w-56 rounded-xl border border-border/70 bg-popover/95 px-3.5 py-3 text-xs text-popover-foreground shadow-2xl shadow-black/10 ring-1 ring-foreground/5 backdrop-blur-md dark:shadow-black/35">
      <div className="font-medium tabular-nums text-foreground">
        {formatTpmTime(String(label ?? ''), withDate)}
      </div>
      <div className="mt-3 space-y-2 border-t border-border/70 pt-3">
        {payload.map((item) => (
          <div
            key={item.dataKey ?? item.name}
            className="grid grid-cols-[auto_1fr_auto] items-center gap-2"
          >
            <span
              className="size-2 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="min-w-0 truncate text-muted-foreground">
              {labelForKey(item.dataKey ?? item.name)}
            </span>
            <span className="font-medium tabular-nums text-foreground">
              {formatNumber(item.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
