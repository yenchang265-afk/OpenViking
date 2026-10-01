# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
import json

import requests  # type: ignore
from requests.adapters import HTTPAdapter
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials

import openviking

# Default request timeout (seconds)
DEFAULT_TIMEOUT = 30

# Connection pool sizing for the per-client keep-alive session.
_POOL_CONNECTIONS = 16
_POOL_MAXSIZE = 32


def _build_pooled_session() -> requests.Session:
    """Create a session that reuses TCP/TLS connections across requests.

    Each client owns one long-lived session so repeated search/find calls hit a
    warm keep-alive connection instead of paying a fresh TCP + TLS handshake.
    """
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=_POOL_CONNECTIONS, pool_maxsize=_POOL_MAXSIZE)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class ClientForDataApi:
    _global_host = {
        "cn-beijing": "api-vikingdb.vikingdb.cn-beijing.volces.com",
        "cn-shanghai": "api-vikingdb.vikingdb.cn-shanghai.volces.com",
        "cn-guangzhou": "api-vikingdb.vikingdb.cn-guangzhou.volces.com",
        "ap-southeast-1": "api-vikingdb.vikingdb.ap-southeast-1.volces.com",
    }

    def __init__(self, ak, sk, region, host=None, session_token=None):
        self.ak = ak
        self.sk = sk
        self.region = region
        self.host = host if host else ClientForDataApi._global_host[region]
        self.session_token = session_token or ""

        if not all([self.ak, self.sk, self.host, self.region]):
            raise ValueError("AK, SK, Host, and Region are required for ClientForDataApi")

        self._session = _build_pooled_session()

    def prepare_request(self, method, path, params=None, data=None):
        if Request is None:
            raise ImportError(
                "volcengine package is required. Please install it via 'pip install volcengine'"
            )

        r = Request()
        r.set_shema("https")
        r.set_method(method)
        r.set_connection_timeout(DEFAULT_TIMEOUT)
        r.set_socket_timeout(DEFAULT_TIMEOUT)
        mheaders = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Host": self.host,
            "User-Agent": f"openviking/{openviking.__version__}",
        }
        r.set_headers(mheaders)
        if params:
            r.set_query(params)
        r.set_host(self.host)
        r.set_path(path)
        if data is not None:
            r.set_body(json.dumps(data))

        credentials = Credentials(
            self.ak,
            self.sk,
            "vikingdb",
            self.region,
            session_token=self.session_token,
        )
        SignerV4.sign(r, credentials)
        return r

    def do_req(self, req_method, req_path, req_params=None, req_body=None):
        req = self.prepare_request(
            method=req_method, path=req_path, params=req_params, data=req_body
        )
        return self._session.request(
            method=req.method,
            url=f"https://{self.host}{req.path}",
            headers=req.headers,
            params=req.query,
            data=req.body,
            timeout=DEFAULT_TIMEOUT,
        )
