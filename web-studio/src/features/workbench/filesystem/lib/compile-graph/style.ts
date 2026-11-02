import { ENTITY_TYPES } from './knowledge-graph'
import type { GraphKind } from './types'
import { WIKI_CATEGORIES } from './wiki'

/** Fixed palettes (never file-derived), readable on light and dark. */
const WIKI_COLORS: Record<string, string> = {
  index: '#f43f5e',
  entity: '#10b981',
  concept: '#3b82f6',
  method: '#8b5cf6',
  comparison: '#06b6d4',
  analysis: '#f59e0b',
  summary: '#ec4899',
  source: '#64748b',
  audit: '#a855f7',
  other: '#94a3b8',
}

const ENTITY_COLORS: Record<string, string> = {
  person: '#0ea5e9',
  animal: '#22c55e',
  place: '#d946ef',
  artifact: '#f59e0b',
  document: '#8b5cf6',
  organization: '#3b82f6',
  group: '#10b981',
  event: '#f43f5e',
  product: '#f97316',
  project: '#ea580c',
  system: '#06b6d4',
  service: '#0891b2',
  module: '#14b8a6',
  dataset: '#6366f1',
  standard: '#a855f7',
  other: '#94a3b8',
}

export function groupOrder(kind: GraphKind): readonly string[] {
  return kind === 'llm-wiki' ? WIKI_CATEGORIES : ENTITY_TYPES
}

export function groupColor(kind: GraphKind, group: string): string {
  const colors = kind === 'llm-wiki' ? WIKI_COLORS : ENTITY_COLORS
  return colors[group] ?? colors.other
}

/** Physics from examples/compile/graph-show, per output kind. */
export const PHYSICS = {
  'llm-wiki': { distance: 130, strength: 0.35, charge: -480, collide: 20 },
  'knowledge-graph': {
    distance: 150,
    strength: 0.42,
    charge: -610,
    collide: 25,
  },
} as const

export function nodeRadius(kind: GraphKind, degree: number): number {
  const d = Math.sqrt(Math.max(degree, 1))
  return kind === 'llm-wiki' ? 7 + d * 2 : 8 + d * 2.4
}

/** Unicode-safe short label for the canvas. */
export function shortLabel(title: string): string {
  const chars = Array.from(title)
  return chars.length > 9 ? `${chars.slice(0, 8).join('')}…` : title
}
