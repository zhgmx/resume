import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "Max_Zhang_Resume.yaml"
PDF = ROOT / "rendercv_output" / "resume.pdf"


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def revision() -> tuple[str, str]:
    commit, timestamp = git("log", "-1", "--format=%H %ct", "--", SOURCE).split()
    date = datetime.fromtimestamp(int(timestamp), ZoneInfo("America/New_York")).date()
    return commit, date.isoformat()


def current_main() -> bool:
    remote = git("ls-remote", "--exit-code", "origin", "refs/heads/main").split()[0]
    if git("rev-parse", "HEAD") != remote:
        print("Skipping publication: this checkout is not the current main commit.")
        return False
    subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--", SOURCE], cwd=ROOT, check=True
    )
    return True


def render(date: str) -> bytes:
    subprocess.run(
        [
            "rendercv",
            "render",
            SOURCE,
            "--pdf-path",
            str(PDF),
            "--settings.current_date",
            date,
            "--dont-generate-markdown",
            "--dont-generate-html",
            "--dont-generate-png",
        ],
        cwd=ROOT,
        check=True,
    )
    data = PDF.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError(
            "RenderCV did not produce a PDF; the published resume was not changed."
        )
    return data


def upload(data: bytes, commit: str, date: str) -> None:
    import boto3

    required = [
        "CLOUDFLARE_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing publication configuration: " + ", ".join(missing))

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )
    filename = f"Max_Zhang_Resume_{date}.pdf"
    client.put_object(
        Bucket=os.environ["R2_BUCKET"],
        Key="resume.pdf",
        Body=data,
        ContentType="application/pdf",
        ContentDisposition=f'inline; filename="{filename}"',
        CacheControl="no-cache",
        Metadata={"source-commit": commit, "updated": date},
    )
    print(f"Published {filename} to https://zhgmx.com/resume.pdf")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--upload", action="store_true", help="Publish after rendering successfully."
    )
    args = parser.parse_args()
    if args.upload and not current_main():
        return
    commit, date = revision()
    data = render(date)
    print(f"Rendered {PDF.name} ({len(data):,} bytes), revision {date}.")
    if args.upload:
        upload(data, commit, date)


if __name__ == "__main__":
    main()
