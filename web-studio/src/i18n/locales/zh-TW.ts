import vikingbot from './zh-TW/vikingbot'
import gateway from './zh-TW/gateway'
import compile from './zh-TW/compile'
import memoryPolicy from './zh-TW/user-memory-policy'
import workspace from './zh-TW/workspace'
import resources from './zh-TW/resources'
import activity from './zh-TW/activity'
import memoryTemplates from './zh-TW/memory-templates'

const zhTW = {
  gateway,
  compile,
  vikingbot,
  ...workspace,
  ...resources,
  ...activity,
  settings: { ...workspace.settings, memoryPolicy, memoryTemplates },
} as const

export default zhTW
