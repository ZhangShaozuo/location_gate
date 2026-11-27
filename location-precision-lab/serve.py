"""Serve the static location precision lab on the local loopback address."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class LabRequestHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080, help="Local port (default: 8080)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    assets = Path(__file__).resolve().parent / "dist"
    handler = partial(LabRequestHandler, directory=str(assets))
    try:
        with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            print(f"定位精度实验台 http://127.0.0.1:{server.server_port}/", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except OSError as error:
        parser.exit(1, f"无法启动服务。检查端口是否被占用：{error}\n")


if __name__ == "__main__":
    main()
