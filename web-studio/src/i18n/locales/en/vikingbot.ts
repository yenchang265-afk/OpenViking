export default {
  operationFailed:
    'The operation could not be completed. Please retry. Details:',
  viewSetup: 'View configuration',
  chooseBotChannel: 'Choose a platform for your bot.',
  searchBots: 'Search bots or runtime users',
  botCount: '{{count}} bots',
  noMatchingBots: 'No bots match your filters.',
  channelFilter: 'Channel',
  addBot: 'Add bot',
  botsHint: 'Manage your bots and filter by channel.',
  connectedBots: 'Connected bots',
  noConnectedBots: 'No bots yet. Select “Add bot” to get started.',
  dingtalk: 'DingTalk',

  runtimeUser: 'Run as user',
  selectUser: 'Select a user',
  runtimeUserHint:
    'Select an ordinary user in this account. The bot uses their resource and memory permissions. Credentials are bound by the server; no API key copying is needed.',
  userUnavailable: 'Credential unavailable',
  noUsers: 'No ordinary users yet. Create a user, then refresh this list.',
  manageUsers: 'Manage users',

  title: 'VikingBot',
  conversations: 'Conversations',
  channels: 'Bots',
  intro:
    'Talk to VikingBot here, or connect it to your team’s messaging platform.',
  newChat: 'New conversation',
  accountRequired: 'Select an account before managing bots',
  web: 'Web',
  all: 'All',
  search: 'Search conversations',
  empty: 'Start a conversation',
  emptyHint:
    'Ask a question, explore your resources, or connect a bot to your messaging platform.',
  manageBots: 'Manage bots',
  enable: 'Enable VikingBot to begin',
  enableHint:
    'Ask your administrator to start OpenViking with Bot support and configure a conversation model.',
  modelHint: 'VikingBot inherits the root vlm model configuration by default.',
  retry: 'Retry',
  loading: 'Loading…',
  error: 'Something went wrong: {{error}}',
  comingSoon: 'Coming soon',
  adminOnly:
    'Only the server administrator can manage connections and view platform history.',
  webReady: 'Web conversations use your current OpenViking identity.',
  manageHint:
    'Connect an application once, then add its bot to multiple groups.',
  back: 'Back',
  deleteConnection: 'Delete connection',
  deleteConnectionHint:
    'Delete the connection for “{{title}}”? This stops the bot connection and permanently removes its Studio chat history. The platform app and group messages remain unchanged.',
  deleteFailed: 'Deletion failed: {{error}}',
  cancelDelete: 'Cancel',
  deletingConnection: 'Deleting…',
  confirmDeleteConnection: 'Delete',
  continueSetup: 'Continue setup',
  pause: 'Pause',
  resume: 'Resume',
  state: { connected: 'Connected', connecting: 'Connecting', paused: 'Paused' },
  historyHint:
    'Only messages received since this connection was set up are shown. This is not the complete group history.',
  readonly:
    'This conversation comes from a messaging platform. Continue chatting there.',
  unknownSender: 'Group member',
  noHistory: 'No received messages yet',
  earlier: 'Load earlier messages',
  delivery: {
    received: 'Received',
    sent: 'Accepted by platform',
    send_failed: 'Sending failed',
  },
  connectionError: 'Bot service is unavailable. Check the service and retry.',
  lastReceived: 'Last received',
  lastSent: 'Last successful reply',
} as const
