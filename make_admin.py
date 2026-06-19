"""One-off CLI to promote an already-registered user to admin.

Usage: python make_admin.py someone@example.com
"""

import sys

from db import Base, SessionLocal, engine
from models import User

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python make_admin.py <email>")

    Base.metadata.create_all(bind=engine)
    email = sys.argv[1]

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        sys.exit(f"No user found with email {email!r}. Sign up first, then promote.")

    user.role = "admin"
    db.commit()
    print(f"{email} is now an admin.")
