import { describe, expect, it } from 'vitest'

import {
  STUDIO_FEATURE_OPTIONS,
  STUDIO_FEATURES,
} from '#/shared/lib/studio-service'

import { resources } from './resources'

type Catalog = { readonly [key: string]: string | Catalog }

function flatten(catalog: Catalog, prefix = ''): Map<string, string> {
  const entries = new Map<string, string>()
  for (const [key, value] of Object.entries(catalog)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (typeof value === 'string') {
      entries.set(path, value)
    } else {
      for (const [k, v] of flatten(value, path)) entries.set(k, v)
    }
  }
  return entries
}

function placeholders(value: string): string[] {
  return [...value.matchAll(/\{\{\s*([\w.]+)[^}]*\}\}/g)]
    .map((match) => match[1])
    .sort()
}

const en = flatten(resources.en as unknown as Catalog)
const zhTW = flatten(resources['zh-TW'] as unknown as Catalog)

describe('locale catalogs', () => {
  it('zh-TW defines every English key', () => {
    expect([...en.keys()].filter((key) => !zhTW.has(key))).toEqual([])
  })

  it('zh-TW has no keys English lacks', () => {
    expect([...zhTW.keys()].filter((key) => !en.has(key))).toEqual([])
  })

  it('keeps interpolation variables in sync', () => {
    const mismatched = [...en.entries()]
      .filter(([key]) => zhTW.has(key))
      .filter(
        ([key, value]) =>
          placeholders(value).join() !== placeholders(zhTW.get(key)!).join(),
      )
      .map(([key]) => key)
    expect(mismatched).toEqual([])
  })
})

describe('studio feature toggles', () => {
  it('labels and describes every toggleable feature', () => {
    const toggleable = [
      ...STUDIO_FEATURES.filter((f) => f.domain !== 'management'),
      ...STUDIO_FEATURE_OPTIONS,
    ]
    const missing = toggleable.flatMap((f) =>
      ['features', 'descriptions']
        .map((group) => `studio.featureToggles.${group}.${f.id}`)
        .filter((key) => !en.has(key)),
    )
    expect(missing).toEqual([])
  })

  it('labels features with their sidebar names', () => {
    const mismatched = [en, zhTW].flatMap((catalog) =>
      STUDIO_FEATURES.map((f) => ({
        id: f.id,
        label: catalog.get(`studio.featureToggles.features.${f.id}`),
        nav: catalog.get(`appShell.navigation.${f.id}.title`),
      })).filter(({ label, nav }) => nav !== undefined && label !== nav),
    )
    expect(mismatched).toEqual([])
  })
})
