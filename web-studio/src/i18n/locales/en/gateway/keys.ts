const keys = {
  description:
    "Each gateway key belongs to one Business Data Platform user and uses one context profile and a set of upstreams. Keys can't be edited — issue a new key and revoke the old one.",
  issue: 'Issue key',
  loadFailed: "Couldn't load gateway keys",
  prerequisites: {
    upstream: 'Add an upstream before issuing a key.',
    profile: 'Create a context profile before issuing a key.',
    both: 'Add an upstream and create a context profile before issuing a key.',
    addUpstream: 'Add an upstream',
    createProfile: 'Create a context profile',
  },
  empty: {
    title: 'No gateway keys yet',
    description:
      "A client uses a gateway key in place of a model API key. Its requests reach your upstreams and read and save one Business Data Platform user's memory. Issue one key per person and client, so you can revoke each on its own.",
  },
  table: {
    name: 'Name',
    key: 'Key',
    user: 'Business Data Platform user',
    profile: 'Context profile',
    upstreams: 'Upstreams',
    models: 'Models',
    created: 'Created',
    actions: 'Actions',
  },
  missing: 'Missing',
  missingProfile: 'This context profile no longer exists',
  missingUpstream: 'This upstream no longer exists',
  extra: '+{{count}}',
  actions: {
    revokeKey: 'Revoke “{{name}}”',
    more: 'More actions for “{{name}}”',
    deleteUserData: "Delete this user's gateway data…",
  },
  revoke: {
    title: 'Revoke “{{name}}”?',
    description:
      'Clients using this key lose access immediately. Conversations and memory stay; a new key for the same user continues them. Turns not yet saved to Business Data Platform, such as the latest reply, are saved only if the conversation continues with a new key.',
    confirm: 'Revoke key',
    done: 'Revoked “{{name}}”',
  },
  deleteUser: {
    title: "Delete {{user}}'s gateway data?",
    description_one:
      "This revokes {{user}}'s gateway key and deletes the conversation state the gateway keeps for this user, including turns not yet saved to Business Data Platform. Their clients lose access immediately. Memories already in Business Data Platform are not affected.",
    description_other:
      'This revokes all {{count}} gateway keys of {{user}} and deletes the conversation state the gateway keeps for this user, including turns not yet saved to Business Data Platform. Their clients lose access immediately. Memories already in Business Data Platform are not affected.',
    confirm: 'Delete gateway data',
    done: "Deleted {{user}}'s gateway data",
  },
  form: {
    title: 'Issue a gateway key',
    description:
      'The key works as soon as it is issued. You will see the full key only once, right after issuing it.',
    name: {
      label: 'Name',
      placeholder: 'e.g. Alice · Claude Code',
      description:
        'Helps you tell keys apart. The person and the client make a good name.',
    },
    user: {
      label: 'Business Data Platform user',
      placeholder: 'Choose a Business Data Platform user',
      loading: 'Loading users…',
      description:
        'The gateway recalls and saves memory as this user. Their Business Data Platform key is read on the server, stored encrypted by the gateway and never shown.',
      roles: {
        admin: 'Admin',
        user: 'User',
      },
      unavailable: "Key can't be read on the server; paste it instead",
      loadFailed:
        "Couldn't load this account's users, so paste the key instead.",
      none: "The server can't read the keys of this account's users, so paste the key instead.",
      root: "With the root key you can't choose a user here, so paste the key instead.",
      choose: 'Choose a user',
    },
    openvikingKey: {
      label: 'Business Data Platform key',
      description:
        "A Business Data Platform user key from this account. The gateway recalls and saves memory as this user. Root keys aren't accepted. Stored encrypted and never shown again.",
      gatewayKey:
        "This is a gateway key. Enter the Business Data Platform user's own key instead.",
      paste: 'Paste a Business Data Platform key',
    },
    profile: {
      label: 'Context profile',
      placeholder: 'Choose a context profile',
      description:
        'Decides how memory is recalled and saved in conversations that use this key.',
      empty: 'There are no context profiles yet.',
      create: 'Create one',
    },
    upstreams: {
      label: 'Upstreams',
      description:
        "For each request, the gateway picks a selected upstream that speaks the client's protocol and serves the requested model.",
      required: 'Choose at least one upstream',
      empty: 'There are no upstreams yet.',
      create: 'Add one',
      off: 'Off',
    },
    models: {
      label: 'Allowed models',
      optional: 'Optional',
      placeholder: 'Type a model name and press Enter',
      description: 'Leave empty to allow every model these upstreams serve.',
    },
    submit: 'Issue key',
  },
  errors: {
    title: "Couldn't issue the key",
    rootKey:
      'This is a root key. Use the key of a Business Data Platform user in this account.',
    otherAccount:
      'This Business Data Platform key belongs to another account. Use a user key from this account.',
    invalidKey:
      "Business Data Platform rejected this key. Check that it's complete and hasn't been regenerated.",
    unavailable:
      "The gateway couldn't reach Business Data Platform to check this key. Try again in a moment.",
    versionMismatch:
      'Business Data Platform is older than the gateway requires. Upgrade Business Data Platform, then try again.',
    unknownUser: 'This user is no longer in this account. Choose another user.',
    userKeyUnreadable:
      "The server can't read this user's Business Data Platform key. Paste the key instead.",
  },
  secret: {
    title: 'Copy your gateway key',
    once: 'This is the only time the full key is shown.',
    copyKey: 'Copy gateway key',
    user: 'Business Data Platform user',
    profile: 'Context profile',
    connectTitle: 'Connect a client',
    clients: {
      'claude-code': {
        intro:
          'Set these variables in the terminal you start Claude Code from.',
      },
      codex: {
        intro:
          'Add the gateway as a provider in the Codex config file, then export the key in your terminal.',
      },
      chat: {
        intro:
          'Use these settings in any OpenAI-compatible client or SDK. Send the same X-OpenViking-Session with every message of a conversation.',
      },
    },
    noProtocol:
      "This key has no enabled {{protocol}} upstream, so {{client}} can't use it.",
    moreClients: 'Other clients and setup details',
    done: "I've copied it",
  },
}

export default keys
