# Deployment modes

<a id="service-options"></a>

Run OpenViking yourself or connect to Volcengine's managed service. Choose based on where data lives, who operates the system, and the support you need.

If you already have an endpoint and API key, go straight to [CLI basics](05-cli-setup.md). To try a complete local question-answering workflow, follow the [quickstart](02-quickstart.md).

## Choose a path

| Option                       | Data and environment                                                                      | Operations and support                                                                              | Prepare                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| **Open-source self-hosting** | Your machine, servers, or cloud environment, with storage you configure                   | You deploy, upgrade, back up, and configure access control; help is available through the community | Runtime environment, model credentials, and storage     |
| **Managed service**          | Volcengine's hosted environment; consult the service terms for region and data conditions | The provider operates infrastructure; you manage access, data, and authorization                    | Service activation, connection details, and an API key  |

Open-source/commercial describes software and support arrangements; self-hosted/managed describes operational responsibility. Open-source deployments can also serve teams. Consider your access-control needs, deployment environment, and support preferences when choosing an option. Version and service documentation describes the available capabilities and limits.

## Open-source self-hosting

Choose this to control the environment, debug locally, or build an application. The open-source server uses AGPLv3; local trials do not need enterprise deployment materials. The [quickstart](02-quickstart.md) walks through model setup, starting the server and VikingBot, and asking about a sample source.

Before sharing a service, configure authentication, persistence, backup, and operations. See [Server deployment](../guides/03-deployment.md) for Docker and open-source Helm options, and [LICENSE](https://github.com/volcengine/OpenViking/blob/main/LICENSE) for the license text.

## Managed service

Volcengine's OpenViking Context is a managed service built on the open-source core. After activation, obtain an API key from the [OpenViking console](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing). Choose **OpenViking Service** in `ov config` and save the connection. You do not need to start the data service locally.

See the [official service documentation](https://docs.volcengine.com/docs/84313/2374478) for plans, quotas, regions, and support. VikingBot and Compile Runtime availability depends on the service configuration; your provider can help confirm support for these capabilities. You can also connect your own agent to the data service.

## After choosing

With an endpoint and data-access credentials, continue to [CLI basics](05-cli-setup.md). For a complete local trial, use the [quickstart](02-quickstart.md).

Sources: [project commercial options](https://github.com/volcengine/OpenViking/blob/main/docs/repository/README_CN.md#商业版本) and [managed-service introduction](https://docs.volcengine.com/docs/84313/2374478). Reviewed on 2026-10-27.
