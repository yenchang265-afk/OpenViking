import onboarding from './zh-TW/onboarding'
import studio from './zh-TW/studio'
import vikingbot from './zh-TW/vikingbot'
import gateway from './zh-TW/gateway'
import compile from './zh-TW/compile'
import memoryPolicy from './zh-TW/user-memory-policy'
import workspace from './zh-TW/workspace'
import resources from './zh-TW/resources'
import activity from './zh-TW/activity'
import memoryTemplates from './zh-TW/memory-templates'
import dataManagement from './zh-TW/data-management'

const zhTW = {
  studio,
  onboarding,
  gateway,
  dataManagement,
  compile,
  vikingbot,
  ...workspace,
  ...resources,
  ...activity,
  settings: { ...workspace.settings, memoryPolicy, memoryTemplates },
} as const

export default zhTW
