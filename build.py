import os
import subprocess
import sys


def main():
    if os.environ.get("VERCEL") != "1":
        return
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required for a Vercel deployment.")
    subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], check=True)


if __name__ == "__main__":
    main()