from __future__ import annotations

import argparse

import uvicorn

from backend.config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run Parrot Script backend')
    parser.add_argument('--host', default=settings.api_host)
    parser.add_argument('--port', type=int, default=settings.api_port)
    parser.add_argument('--workers', type=int, default=settings.api_workers)
    parser.add_argument('--log-level', default=settings.api_log_level)
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
    parser.add_argument('--no-reload', action='store_true', help='Disable auto-reload')
    return parser.parse_args()


def resolve_reload(args: argparse.Namespace) -> bool:
    reload_enabled = settings.api_reload
    if args.reload:
        reload_enabled = True
    if args.no_reload:
        reload_enabled = False
    return reload_enabled


def main() -> None:
    args = parse_args()
    reload_enabled = resolve_reload(args)
    workers = max(1, int(args.workers))

    # Uvicorn does not support multi-worker mode with reload.
    if reload_enabled:
        workers = 1

    uvicorn.run(
        'backend.api.server:app',
        host=args.host,
        port=args.port,
        reload=reload_enabled,
        workers=workers,
        log_level=args.log_level,
    )


if __name__ == '__main__':
    main()
