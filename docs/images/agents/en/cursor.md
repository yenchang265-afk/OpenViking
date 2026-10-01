## Step 1: Install

1. Run the installer in your terminal:

   ```bash
   bash <(curl -fsSL https://ovrelease.tos-cn-beijing.volces.com/memory-plugin-shared/install.sh)
   ```

2. The installer will ask for language (English / Chinese) and Business Data Platform credentials. In the Business Data Platform credential step, choose **VolcEngine Business Data Platform Cloud Service [api.vikingdb.cn-beijing.volces.com]** and enter the API KEY:

   ```text
   {{OPENVIKING_API_KEY}}
   ```

## Step 2: Verify

1. Open **Customize → MCPs** and confirm both **openviking User** and **openviking Plugin** are visible.
2. Open **Customize → Hooks** and confirm the **openviking-memory** entry is visible.

## Troubleshoot

| Problem | Fix |
|---|---|
| Hooks do not run | Quit Cursor completely, restart, new Agent session |
| Connection / auth fails | Check `~/.openviking/ovcli.conf` and restart Cursor |
| Need logs | `OPENVIKING_DEBUG=1` and `~/.openviking/logs/cursor-hooks.log` |

## Reference

- Docs on Manual Settings: [Cursor](https://docs.openviking.net/en/agent-integrations/12-cursor)
- Code: [examples/agent-hook-plugin](https://github.com/volcengine/OpenViking/tree/main/examples/agent-hook-plugin)
