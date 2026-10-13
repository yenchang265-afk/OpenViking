const common = {
  title: 'Business Data Platform Gateway',
  description:
    'Give any API-key model client Business Data Platform memory. Point the client at the gateway, and it adds relevant memory to each new message and saves conversations back to Business Data Platform.',
  beta: {
    label: 'Beta',
    hint: 'Beta: Business Data Platform Gateway is still evolving; later releases may change its settings and APIs.',
  },
  tabs: {
    label: 'Business Data Platform Gateway sections',
    overview: 'Overview',
    upstreams: 'Upstreams',
    profiles: 'Profiles',
    keys: 'Keys',
    requests: 'Requests',
    connect: 'Connect',
  },
  address: {
    label: 'Gateway address',
    copy: 'Copy gateway address',
  },
  actions: {
    cancel: 'Cancel',
    copy: 'Copy',
    delete: 'Delete',
    duplicate: 'Duplicate',
    edit: 'Edit',
    more: 'More actions',
    refresh: 'Refresh',
    remove: 'Remove',
    retry: 'Retry',
    revoke: 'Revoke',
    save: 'Save',
    viewAll: 'View all',
  },
  states: {
    loading: 'Loading…',
    saving: 'Saving…',
    updatedAt: 'Updated {{time}}',
    any: 'Any',
    on: 'On',
    off: 'Off',
  },
  copy: {
    done: 'Copied to clipboard',
    failed: "Couldn't copy. Select the text and copy it manually.",
  },
  access: {
    title: 'Account administrator access required',
    description:
      'Managing the Business Data Platform Gateway needs an account administrator or root key for this account. Add one in Connection settings.',
    action: 'Open connection settings',
  },
  unavailable: {
    notEnabled: {
      title: 'The Business Data Platform Gateway is turned off',
      description:
        'This server has the Business Data Platform Gateway turned off. Turn it on in ov.conf, restart Business Data Platform, then start the gateway.',
    },
    tokenMissing: {
      title: 'The management token is missing',
      description:
        'Business Data Platform needs the same management token as the gateway to manage it. Set this environment variable (at least 32 characters) for both Business Data Platform and the gateway, then restart them.',
    },
    tokenMismatch: {
      title: "The management tokens don't match",
      description:
        'Business Data Platform and the gateway were started with different management tokens, so the gateway turns Business Data Platform away. Set this environment variable to the same value for both, then restart them.',
    },
    unsupported: {
      title:
        "This Business Data Platform server can't manage a Business Data Platform Gateway",
      description:
        'Studio is connected to a Business Data Platform server without gateway support. Upgrade Business Data Platform Server, restart it, then retry.',
    },
    devMode: {
      title: 'Business Data Platform runs in development mode',
      description:
        'In development mode every key acts as root, and the gateway refuses root keys, so no gateway key can be issued. Switch Business Data Platform to API key mode, restart it, then add an account admin key in Connection settings.',
    },
    unreachable: {
      title: "Business Data Platform can't reach the gateway",
      description:
        'The gateway is not running, or gateway.url in ov.conf points to the wrong address. Start the gateway and check that Business Data Platform can reach that address.',
    },
    failed: {
      title: "Couldn't load the Business Data Platform Gateway",
    },
    fixLabel: 'What to change',
    terminal: 'Terminal',
    environment: 'Environment variable',
    docs: 'How to deploy',
  },
  errors: {
    reasons: {
      not_enabled:
        'The Business Data Platform Gateway is turned off on this server.',
      token_missing:
        "Business Data Platform can't manage the gateway because the management token isn't set.",
      token_mismatch:
        "The gateway rejected Business Data Platform's management token. Both must use the same token.",
      unreachable: "Business Data Platform can't reach the gateway.",
      unsupported:
        "This Business Data Platform server doesn't support the Business Data Platform Gateway.",
      conflict: 'This change conflicts with existing settings.',
      invalid:
        'The gateway rejected these settings. Check the values and try again.',
      forbidden: "You don't have permission to do this.",
      not_found: 'This item no longer exists. Refresh and try again.',
      unauthorized: 'Your key was rejected. Check Connection settings.',
      other: 'Something went wrong. Try again.',
    },
    inUse: 'Keys still use this. Revoke those keys first.',
    invalidSettings:
      'The gateway rejected these settings. Check the values and limits.',
    invalidKeyRequest:
      'The gateway rejected this key. Check the fields and try again.',
    unknownProfile: 'The selected context profile no longer exists.',
    unknownUpstream: 'One of the selected upstreams no longer exists.',
    keyNotFound:
      'The gateway key this conversation used has been revoked, so it can no longer be resynced.',
    sessionNotFound: 'The gateway no longer has this conversation.',
    upstreamKeyMissing:
      'There is no stored API key to test with. Clients of this upstream send their own key, or the key has not been set.',
    subscriptionKey:
      "Claude subscription logins aren't supported. Use a model API key.",
  },
  validation: {
    required: 'Required',
    number: 'Enter a number',
    integer: 'Enter a whole number',
    min: 'Must be at least {{min}}',
    max: 'Must be at most {{max}}',
    range: 'Must be between {{min}} and {{max}}',
    rangeExclusive: 'Must be more than {{min}} and at most {{max}}',
    greaterThan: 'Must be more than {{min}}',
    selectOneSource: 'Choose at least one source',
    unknownCategory: 'Unknown category “{{name}}”',
    quotasAllZero: 'Set at least one category above 0, or turn the limit off',
    softBelowHard: 'Must be below the hard reminder',
    baseUrl:
      'Enter an http:// or https:// URL without credentials, query or fragment',
    subscriptionKey:
      "Claude subscription tokens (sk-ant-oat…) aren't supported. Use a model API key.",
    apiKeyRequired:
      'Enter the API key, or let each client send its own key instead',
    headerInvalid: 'Header “{{name}}” has an invalid name or value',
    headerReserved: "“{{name}}” is set by the gateway and can't be changed",
    headerValue: 'Enter a value for “{{name}}”',
    aliasTarget: 'Enter the upstream model for “{{name}}”',
    contextWindow: 'The window for “{{name}}” must be at least {{min}} tokens',
    protocolUnsupported:
      '$t(enums.vendor.{{vendor}}) does not offer $t(enums.protocol.{{protocol}}). Pick another protocol, or set the provider to $t(enums.vendor.generic).',
  },
  units: {
    bytes: 'bytes',
    characters: 'characters',
    entries: 'entries',
    messages: 'messages',
    rounds: 'rounds',
    seconds: 'seconds',
    tokens: 'tokens',
  },
  field: {
    default: 'Default: {{value}}',
    notSet: 'Not set',
    noLimit: 'No limit',
    advanced: 'Advanced settings',
    sectionInvalid: 'Fix the highlighted settings in this section to save.',
    storedSecret: 'Stored — leave blank to keep',
  },
  keyValue: {
    add: 'Add',
    remove: 'Remove',
    duplicate: 'Listed twice; only the last one is kept',
  },
  tags: {
    remove: 'Remove {{value}}',
    suggestions: 'Suggestions',
  },
}

export default common
