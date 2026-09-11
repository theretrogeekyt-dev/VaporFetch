import sys
import getpass
import argparse
import time
from typing import List

from vaporfetch.config import (
    load_settings,
    save_settings,
    get_storage_stats,
    find_steamcmd_path,
)
from vaporfetch.steamcmd import (
    get_current_session,
    start_login,
    submit_2fa_code,
    clear_session,
    auth_session,
)
from vaporfetch.library import (
    get_library,
    resolver,
)
from vaporfetch.downloader import manager

def cli_login():
    """Interactive SteamCMD login flow from terminal."""
    print("\n=== VaporFetch SteamCMD Login ===")
    session = get_current_session()
    if session.get("logged_in") and session.get("username"):
        print(f"Already logged in as: {session['username']}")
        ans = input("Do you want to re-login with another account? [y/N]: ").strip().lower()
        if ans != "y":
            return

    username = input("Steam Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return

    password = getpass.getpass("Steam Password (leave empty if remembering credentials): ").strip()

    print(f"Connecting to SteamCMD with user '{username}'...")
    res = start_login(username, password if password else None)

    if res["status"] == "awaiting_2fa":
        print(f"\n[Steam Guard] {res.get('prompt', 'Enter 2FA code')}:")
        code = input("Code: ").strip()
        verif = submit_2fa_code(code)
        if verif["status"] == "logged_in":
            print("\n✅ Successfully authenticated with Steam Guard!")
        else:
            print(f"\n❌ 2FA verification failed: {verif.get('error')}")
    elif res["status"] == "logged_in":
        print("\n✅ Successfully logged into Steam!")
    else:
        print(f"\n❌ Login failed: {res.get('error')}")


def cli_logout():
    """Clear session from terminal."""
    clear_session()
    print("Logged out from Steam session.")


def cli_status():
    """Display system and session status."""
    print("\n=== VaporFetch Status ===")
    session = get_current_session()
    if session.get("logged_in"):
        print(f"Steam Account: {session.get('username')} (Logged In)")
    else:
        print("Steam Account: Not Authenticated")

    print(f"SteamCMD Path: {find_steamcmd_path()}")

    storage = get_storage_stats()
    print(f"Storage Space: {storage['free_gb']} GB Free / {storage['total_gb']} GB Total ({storage['percent_used']}% used)")

    q_state = manager.get_queue_state()
    cur = q_state.get("current")
    if cur:
        print(f"Active Download: {cur['name']} ({cur['percent']}%) - {cur['speed_formatted']}")
    else:
        print("Active Download: None")
    print(f"Queued Items:    {len(q_state.get('queue', []))}")


def cli_list(args):
    """List owned games from Steam licenses."""
    session = get_current_session()
    if not session.get("logged_in"):
        print("Not logged in. Please run `vaporfetch login` first.")
        return

    print("Fetching Steam library licenses...")
    games = get_library(force_refresh=args.refresh)
    if not games:
        print("No games found in account licenses.")
        return

    query = (args.filter or "").lower()
    filtered = [g for g in games if query in g["name"].lower() or query in str(g["appid"])]

    if args.downloaded:
        filtered = [g for g in filtered if g["backup_status"] == "downloaded"]
    elif args.missing:
        filtered = [g for g in filtered if g["backup_status"] != "downloaded"]

    print(f"\nFound {len(filtered)} games:")
    print(f"{'AppID':<10} {'Status':<15} {'Size':<12} {'Game Name'}")
    print("-" * 65)
    for g in filtered:
        status = g["backup_status"].replace("_", " ").title()
        size = g["backup_size"] if g["backup_status"] == "downloaded" else "-"
        print(f"{g['appid']:<10} {status:<15} {size:<12} {g['name']}")


def cli_backup(args):
    """Queue and backup games from command line."""
    session = get_current_session()
    if not session.get("logged_in"):
        print("Not logged in. Please run `vaporfetch login` first.")
        return

    platform = args.platform or load_settings().get("default_platform", "windows")

    if args.all:
        games = get_library()
        if not games:
            print("No games found in library.")
            return
        confirm = input(f"Are you sure you want to backup all {len(games)} games in your library? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return
        items = [{"appid": g["appid"], "name": g["name"]} for g in games]
        added = manager.add_batch(items, platform=platform)
        print(f"Queued {added} games for backup (Platform: {platform}).")
    elif args.appid:
        appids = [int(x.strip()) for x in args.appid.split(",") if x.strip().isdigit()]
        for aid in appids:
            name = resolver.resolve_name(aid)
            manager.add_to_queue(aid, name, platform=platform)
            print(f"Queued AppID {aid} ({name}) for backup (Platform: {platform}).")
    else:
        print("Please specify --appid <id,id,...> or --all to backup.")
        return

    if args.watch:
        _watch_downloads()


def _watch_downloads():
    """Terminal progress watcher."""
    print("\nWatching download progress... (Press Ctrl+C to exit watcher)")
    try:
        while True:
            state = manager.get_queue_state()
            cur = state.get("current")
            q_len = len(state.get("queue", []))

            if cur:
                bar_len = 30
                filled = int(bar_len * (cur["percent"] / 100.0))
                bar = "█" * filled + "-" * (bar_len - filled)
                sys.stdout.write(
                    f"\r[{bar}] {cur['percent']}% | {cur['speed_formatted']} | ETA: {cur['eta_seconds']}s | {cur['name'][:25]} (Queue: {q_len})   "
                )
                sys.stdout.flush()
            elif q_len > 0:
                sys.stdout.write(f"\rWaiting for next task in queue ({q_len} remaining)...       ")
                sys.stdout.flush()
            else:
                sys.stdout.write("\rAll queued downloads completed.                                      \n")
                sys.stdout.flush()
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nDetached from download monitor (downloads continue in background).")


def main():
    parser = argparse.ArgumentParser(
        prog="vaporfetch",
        description="VaporFetch: Docker-based Steam game downloader and backup tool using SteamCMD.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # login
    subparsers.add_parser("login", help="Log into Steam account with SteamCMD")

    # logout
    subparsers.add_parser("logout", help="Log out and remove cached credentials")

    # status
    subparsers.add_parser("status", help="Show current login, storage, and queue status")

    # list
    list_p = subparsers.add_parser("list", help="List owned Steam games")
    list_p.add_argument("--refresh", action="store_true", help="Force sync licenses from SteamCMD")
    list_p.add_argument("--filter", type=str, default="", help="Filter games by title or AppID")
    list_p.add_argument("--downloaded", action="store_true", help="Show only backed up games")
    list_p.add_argument("--missing", action="store_true", help="Show only games not yet backed up")

    # backup
    backup_p = subparsers.add_parser("backup", help="Download and backup games")
    backup_p.add_argument("--appid", type=str, help="Comma-separated list of AppIDs to backup")
    backup_p.add_argument("--all", action="store_true", help="Backup all games in your Steam library")
    backup_p.add_argument("--platform", type=str, choices=["windows", "linux", "macos"], help="Target depot platform")
    backup_p.add_argument("--watch", action="store_true", help="Watch download progress in terminal")

    # serve
    serve_p = subparsers.add_parser("serve", help="Launch the VaporFetch Web UI dashboard")
    serve_p.add_argument("--host", type=str, default="0.0.0.0", help="Web server bind host")
    serve_p.add_argument("--port", type=int, default=8080, help="Web server port")

    args = parser.parse_args()

    if args.command == "login":
        cli_login()
    elif args.command == "logout":
        cli_logout()
    elif args.command == "status":
        cli_status()
    elif args.command == "list":
        cli_list(args)
    elif args.command == "backup":
        cli_backup(args)
    elif args.command == "serve":
        from vaporfetch.web.server import run_server
        run_server(host=args.host, port=args.port)
    else:
        # Default behavior when launched inside Docker without args: run the web server!
        from vaporfetch.web.server import run_server
        run_server()


if __name__ == "__main__":
    main()

