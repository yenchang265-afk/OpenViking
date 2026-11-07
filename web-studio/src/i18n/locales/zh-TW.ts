import activity from './zh-TW/activity'
import arranger from './zh-TW/arranger'
import compile from './zh-TW/compile'
import dataManagement from './zh-TW/data-management'
import gateway from './zh-TW/gateway'
import memoryTemplates from './zh-TW/memory-templates'
import onboarding from './zh-TW/onboarding'
import resources from './zh-TW/resources'
import studio from './zh-TW/studio'
import memoryPolicy from './zh-TW/user-memory-policy'
import vikingbot from './zh-TW/vikingbot'
import workspace from './zh-TW/workspace'

const zhTW = {
  arranger,
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
