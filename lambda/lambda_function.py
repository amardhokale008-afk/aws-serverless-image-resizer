"""
Serverless Image Resizer - AWS Lambda handler
----------------------------------------------
Triggered by an S3 ObjectCreated event on the SOURCE bucket.
For every uploaded .jpg/.jpeg/.png it creates three resized copies
(thumbnail, medium, large) and writes them to a SEPARATE destination
bucket under  <size>/<original-key>.

Using a separate destination bucket avoids the classic recursive-trigger
bug (Lambda writes to the same bucket -> triggers itself forever).
"""

import io
import os
import urllib.parse

import boto3
from PIL import Image

s3 = boto3.client("s3")

DEST_BUCKET = os.environ.get("DEST_BUCKET", "")

# label -> max (width, height). Aspect ratio is preserved.
SIZES = {
    "thumbnail": (150, 150),
    "medium": (500, 500),
    "large": (1000, 1000),
}

FORMATS = {
    "jpg": ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "png": ("PNG", "image/png"),
}


def resize_image(data: bytes, fmt: str, max_size: tuple) -> bytes:
    """Return resized image bytes. Never upscales; keeps aspect ratio."""
    img = Image.open(io.BytesIO(data))
    img.load()
    img.thumbnail(max_size)
    if fmt == "JPEG" and img.mode not in ("RGB", "L"):
        img = img.convert("RGB")  # JPEG cannot store alpha
    out = io.BytesIO()
    if fmt == "JPEG":
        img.save(out, fmt, quality=85, optimize=True)
    else:
        img.save(out, fmt, optimize=True)
    return out.getvalue()


def handler(event, context):
    results = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""

        if ext not in FORMATS:
            print(f"SKIP {key}: unsupported extension '{ext}'")
            continue

        fmt, content_type = FORMATS[ext]
        print(f"Processing s3://{bucket}/{key}")

        original = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

        for label, size in SIZES.items():
            resized = resize_image(original, fmt, size)
            dest_key = f"{label}/{key}"
            s3.put_object(
                Bucket=DEST_BUCKET,
                Key=dest_key,
                Body=resized,
                ContentType=content_type,
            )
            print(f"  -> s3://{DEST_BUCKET}/{dest_key} ({len(resized)} bytes)")
            results.append(dest_key)

    return {"statusCode": 200, "created": results}
