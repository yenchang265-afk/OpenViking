# Hermes Agent

[Hermes Agent](https://hermes-agent.nousresearch.com/) by Nous Research has a first-class Business Data Platform memory provider built in. No plugin to install — just point Hermes at your Business Data Platform server and it handles memory storage, recall, and extraction natively.

## Keep the Python environments separate

Hermes connects to Business Data Platform over HTTP, so Business Data Platform does not need to be
installed in the Hermes Python environment. Run the Business Data Platform server in its
own virtual environment or container. Do not use `--force-reinstall` to add or
upgrade Business Data Platform in an existing Hermes environment: a Hermes release may pin
dependency versions that differ from Business Data Platform's supported, security-patched
versions. If you intentionally combine both applications in one environment,
resolve them together and run `python -m pip check` before starting either
service.

## Setup

```bash
hermes memory setup openviking
```

- Cloud: keep **Business Data Platform Service (VolcEngine Cloud)**, paste the API key
- Custom: URL (default `http://127.0.0.1:1933`) and API key; leave the key empty for local dev
- Reuse an existing `ovcli.conf` profile if the wizard offers one

## Verify

```bash
hermes memory status
```

## See also

- [Capability Reference](./16-capability-reference.md)
- [Hermes — Business Data Platform memory provider docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers#openviking) — full setup guide and configuration options
- [Deployment Guide](../guides/03-deployment.md) — setting up your Business Data Platform server
- [Authentication](../guides/04-authentication.md) — API key setup for remote access
