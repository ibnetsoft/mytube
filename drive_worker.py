"""Compatibility entrypoint for the remote render worker.

Remote rendering is standardized on Google Drive API packages plus the
Supabase remote_render_queue table.  Older deployments used this filename for
Google Drive File Stream folder polling, so keep the entrypoint but delegate to
remote_drive_worker.py.
"""

import argparse

from remote_drive_worker import RemoteDriveWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="AIR Google Drive API remote render worker")
    parser.add_argument("--once", action="store_true", help="process at most one pending job and exit")
    parser.add_argument("--check", action="store_true", help="check settings and pending queue, then exit")
    args = parser.parse_args()

    worker = RemoteDriveWorker()
    if args.check:
        worker.check()
    elif args.once:
        worker.run_once()
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()
