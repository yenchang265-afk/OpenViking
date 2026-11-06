"""Provision the shared OAuth and usage schemas as an explicit operator action.

Run ``python -m openviking.server.shared_schema --config ov.conf`` to review
DDL, or add ``--apply`` to create missing tables. Existing tables are never
dropped or reset. Account and task schemas have their own provisioning tools.
"""

import argparse
import asyncio


async def provision(config_path, apply=False):
    from sqlalchemy.dialects.mysql import dialect
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.schema import CreateIndex, CreateTable

    from openviking.observability.usage_audit.mysql_store import metadata as usage
    from openviking.server.account_stores.mysql import MySQLAccountStore
    from openviking.server.config import load_server_config
    from openviking.server.oauth.mysql_store import metadata as oauth
    from openviking_cli.utils.config.open_viking_config import get_openviking_config

    server = load_server_config(config_path)
    config = get_openviking_config()
    selections = []
    if config.oauth.enabled and config.oauth.backend == "mysql":
        selections.append((oauth, config.oauth.mysql))
    audit = server.observability.usage_audit
    if audit.enabled and audit.backend == "mysql":
        selections.append((usage, audit.mysql))
    for metadata, params in selections:
        if not apply:
            for table in metadata.sorted_tables:
                print(str(CreateTable(table).compile(dialect=dialect())) + ";")
                for index in sorted(table.indexes, key=lambda index: index.name):
                    print(str(CreateIndex(index).compile(dialect=dialect())) + ";")
            continue
        url, options = MySQLAccountStore._connection_options(dict(params))
        engine = create_async_engine(url, **options)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(metadata.create_all)
        finally:
            await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(provision(args.config, args.apply))


if __name__ == "__main__":
    main()
