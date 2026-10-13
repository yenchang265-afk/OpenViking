import discordIcon from './brand-icons/discord.svg?url'
import dingtalkIcon from './brand-icons/dingtalk.svg?url'
import slackIcon from './brand-icons/slack.svg?url'
import telegramIcon from './brand-icons/telegram.svg?url'

// DingTalk: Ant Design Icons (MIT);
// Slack, Discord, Telegram: Simple Icons (CC0).
const icons: Record<string, string> = {
  slack: slackIcon,
  dingtalk: dingtalkIcon,
  discord: discordIcon,
  telegram: telegramIcon,
}

export function PlatformIcon({ platform }: { platform: string }) {
  const icon = icons[platform.toLowerCase()]
  if (!icon) return null
  const mask = `url("${icon}") center / contain no-repeat`

  return (
    <span
      className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted/50 text-muted-foreground"
      aria-hidden="true"
    >
      <span className="size-5 bg-current" style={{ mask, WebkitMask: mask }} />
    </span>
  )
}
