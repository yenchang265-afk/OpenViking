# Community Plugins

Community-maintained integrations for various agent runtimes. Each differs in target platform, integration depth, and maintenance status — check the linked README before adopting.

## AstrBot plugin

[AstrBot](https://github.com/AstrBotDevs/AstrBot) is a multi-platform IM bot framework supporting QQ, Telegram, Discord, and 20+ other platforms.

Source: [astrbot_plugin_openviking_memory](https://github.com/t0saki/astrbot_plugin_openviking_memory)

Provides auto-capture of group/DM conversations, semantic recall before each LLM request, and configurable venue memory isolation.

**Install**: In AstrBot WebUI, search **OpenViking Memory** in the Plugin Marketplace; or install from URL: `https://github.com/t0saki/astrbot_plugin_openviking_memory.git`

The current plugin requires AstrBot 4.23.1+ and a compatible OpenViking server. Use a User key for `global`; `venue` needs an Admin key to create users. Check the linked plugin README before migrating an older configuration.

**Key features**:

- Auto-recall and auto-capture via hooks — the model doesn't need to invoke tools
- `self_scope=global` shares one bot identity; `venue` creates a separate user per group/DM. People are represented as peers. Legacy `isolation_mode` values are mapped to these scopes.
- Automatic commit by message count, token threshold, or idle timeout
- Backfills platform message history on first venue encounter

## More examples

The [examples/](https://github.com/volcengine/OpenViking/tree/main/examples) directory also contains deployment and integration samples beyond agent plugins — Grafana dashboards, Kubernetes Helm charts, multi-tenant setups, snapshot workflows, and SDK snippets.

## See also

- [Capability Reference](./16-capability-reference.md)
