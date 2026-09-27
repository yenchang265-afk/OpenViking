// Accepts Telegram user IDs or @usernames separated by commas or whitespace.
// The server validates and normalizes each entry.
export function parseAllowList(text: string) {
  return [...new Set(text.split(/[\s,]+/).filter(Boolean))]
}

export function allowedUsers(settings?: Record<string, unknown>) {
  const value = settings?.allow_from
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

export function formatAllowList(users: string[]) {
  return users.map((user) => (/^\d+$/.test(user) ? user : `@${user}`))
}
