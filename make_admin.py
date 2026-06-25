"""One-off CLI to promote an already-registered user to admin.

Usage: python make_admin.py someone@example.com
"""

import sys

from dotenv import load_dotenv

load_dotenv()

import models  # noqa: E402 -- must load .env (Cosmos credentials) before importing models/db

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python make_admin.py <email>")

    email = sys.argv[1]
    user = models.get_user_by_email(email)
    if user is None:
        sys.exit(f"No user found with email {email!r}. Sign up first, then promote.")

    models.update_user(user, role="admin")
    print(f"{email} is now an admin.")
