"""Create a superadmin account, or promote / reset an existing one.

The password is typed at a hidden prompt, never passed on the command line,
so it does not land in shell history or process listings.

    cd backend && ./venv/Scripts/python.exe scripts/create_superadmin.py <username> ["Display Name"] [--email you@adani.com]

An existing username is made superadmin with the new password (an explicit
operator action - use it to recover a locked-out installation). The account
must set its own password at first sign-in unless --no-change is given.
"""
import argparse
import getpass
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from auto_migrate import auto_upgrade_schema  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AkashaUser  # noqa: E402
from services import access, security  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("username")
    ap.add_argument("display_name", nargs="?", default="Super Admin")
    ap.add_argument("--email")
    ap.add_argument("--no-change", action="store_true", help="do not require a password change at first sign-in")
    args = ap.parse_args()

    auto_upgrade_schema()
    db = SessionLocal()
    try:
        access.seed_roles(db)
        password = getpass.getpass(f"Password for {args.username}: ")
        problems = security.password_problems(password, args.username)
        if problems:
            print("Password needs: " + "; ".join(problems))
            return 1
        if getpass.getpass("Repeat password: ") != password:
            print("Passwords do not match")
            return 1

        user = db.query(AkashaUser).filter(func.lower(AkashaUser.username) == args.username.lower()).first()
        action = "user.superadmin_reset" if user else "user.bootstrap"
        if not user:
            user = AkashaUser(username=args.username, created_at=datetime.utcnow())
            db.add(user)
        user.display_name = args.display_name if not user.display_name or args.display_name != "Super Admin" else user.display_name
        if args.email:
            user.email = args.email
        user.role = access.SUPERADMIN
        user.is_active = True
        user.password_hash = security.hash_password(password)
        user.must_change_password = not args.no_change
        user.failed_login_count = 0
        user.locked_until = None
        user.updated_at = datetime.utcnow()
        db.flush()
        security.end_all_sessions(db, user.id)
        security.audit(db, action, target=user.username, detail={"via": "create_superadmin.py"})
        db.commit()
        print(f"Superadmin '{user.username}' ready." +
              ("" if args.no_change else " A new password must be set at first sign-in."))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
