"""Initialize Entity V0 with ``python -m scripts.init_app_db``."""

import argparse

from martin.db import get_app_db_path, init_schema


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", help="SQLite path (default: MARTIN_APP_DB_PATH)")
    args = parser.parse_args()
    init_schema(args.db_path)
    print(f"Initialized business database: {args.db_path or get_app_db_path()}")


if __name__ == "__main__":
    main()
