"""Says whether this machine can run the app, and what is missing.

Run this first. It answers the questions that otherwise turn into a confusing
error later: is Python new enough, is Pillow there, can the folders be reached.
"""

import os
import platform
import sys

# Run as `python scripts/doctor.py` from anywhere: the code is one folder up.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    ok = True
    print("Photo Manager - environment check")
    print("-" * 52)
    print(f"  Python        {platform.python_version()}  ({sys.executable})")
    if sys.version_info < (3, 10):
        print("                NEEDS 3.10 or newer")
        ok = False
    print(f"  System        {platform.system()} {platform.release()}")

    try:
        import PIL
        print(f"  Pillow        {PIL.__version__}")
    except ImportError:
        print("  Pillow        not installed")
        print("                Only the 'previews' tool needs it. Everything else -")
        print("                unpair, remirror, ratings, cull, geotag, pin - runs")
        print("                without it.")
        print("                install with:  python -m pip install pillow")

    from core import heif
    reader = heif.decoder()
    if reader:
        print(f"  HEIC reader   {reader}")
    else:
        print("  HEIC reader   not installed")
        print("                HEIC dates and places are read without it; only")
        print("                HEIC thumbnails and previews need it.")
        print("                install with:  python -m pip install pi-heif")

    roots = [p for p in os.environ.get("ALLOWED_ROOTS", "").split(os.pathsep) if p]
    if roots:
        print("  Folders it may touch:")
        for r in roots:
            print(f"      {'ok ' if os.path.isdir(r) else 'MISSING'}  {r}")
    else:
        print("  Folders       no restriction set (ALLOWED_ROOTS is empty), so the")
        print("                web page can reach any path on this machine. That is")
        print("                fine on your own PC; set it on the NAS.")

    try:
        import app.tasks                       # noqa: F401
        from app import registry as R
        names = [t.name for t in R.all_tasks()]
        print(f"  Tools         {len(names)}: {', '.join(names)}")
    except Exception as exc:                   # noqa: BLE001
        print(f"  Tools         COULD NOT LOAD: {exc}")
        ok = False

    # Who this app writes as, against who owns the library.
    #
    # Worth a line of its own because it is the one fault here that reports
    # itself as nothing at all: every write succeeds, every move lands, the app
    # is perfectly happy - and Synology Drive, which reads the library as YOU,
    # stops syncing a tree it can no longer read, without saying anything
    # either. The first sign is a folder that has not appeared on the tablet for
    # a fortnight.
    try:
        from core import perms, settings as _s
        uid, gid = perms.writes_as()
        if uid is None:
            print("  Writes as     this machine has no file owners to get wrong")
        else:
            print(f"  Writes as     user {uid}, group {gid}"
                  + ("  (root)" if uid == 0 else ""))
            for key in ("library", "raw", "previews", "develop"):
                where = str(_s.load()[key] or "").strip()
                said = perms.mismatch(where)
                if said:
                    print(f"      {key}: {said}")
            print("                Files it rewrites keep the owner and mode they")
            print("                had; ones it creates take after the folder they")
            print("                land in. Both matter to Synology Drive.")
        # And the half that cannot be done from in here at all: DSM keeps its
        # access list in a privileged extended attribute, so a folder this app
        # makes as a normal user is handed to a job that runs as root.
        from core import acl as _acl
        waiting, ran = _acl.waiting(), _acl.last_run()
        if waiting or ran:
            import time as _t
            print(f"  Access list   {len(waiting):,} folder(s) waiting for the "
                  f"repair job")
            if ran:
                mins = max(0, int((_t.time() - ran["when"]) // 60))
                print(f"                it last ran {mins:,} minute(s) ago and "
                      f"put {ran['fixed']:,} right")
            else:
                print("                it has never run - Setup > Permissions "
                      "writes it and says where it goes")
    except Exception as exc:                        # noqa: BLE001
        print(f"  Writes as     could not be worked out: {exc}")

    print("-" * 52)
    print("  ready" if ok else "  NOT ready - see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
