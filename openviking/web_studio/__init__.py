# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd.
# SPDX-License-Identifier: AGPL-3.0
"""Built web-studio assets, populated by ``setup.py`` when building a wheel.

The actual SPA source lives at the repository root in ``web-studio/``. A wheel
build runs ``npm run build`` and copies the Vite output (``web-studio/dist``)
into ``openviking/web_studio/dist`` so the wheel ships the bundle as
package-data. The server resolves ``dist/`` relative to this package at
runtime, unless ``OPENVIKING_WEB_STUDIO_DIR`` points elsewhere (the docker
``all-in-one`` image does this; the ``server`` image ships no Studio). If no
bundle is found, the /studio routes simply aren't registered.
"""
