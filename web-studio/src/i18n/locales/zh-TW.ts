import vikingbot from './zh-TW/vikingbot'
import compile from './zh-TW/compile'
import memoryPolicy from './zh-TW/user-memory-policy'
import workspace from './zh-TW/workspace'
import resources from './zh-TW/resources'
import activity from './zh-TW/activity'

const zhTW = {
  compile,
  vikingbot,
  ...workspace,
  ...resources,
  ...activity,
  settings: { ...workspace.settings, memoryPolicy },
} as const

export default zhTW
