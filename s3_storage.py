import io
import os
import boto3

BUCKET_NAME = "pfa1"
AWS_REGION = "eu-north-1"
LAST_S3_ERROR = None

s3 = None


def get_s3_client():
    """Lazily initialize or return cached S3 client."""
    global s3
    if s3 is not None:
        return s3
    try:
        s3 = boto3.client(
            "s3",
            region_name=AWS_REGION
        )
        return s3
    except Exception as e:
        print(f"Warning: Could not initialize S3 client: {e}")
        return None


# Initialize module-level client
s3 = get_s3_client()


def get_last_s3_error():
    """Return the last S3 error message, if any."""
    global LAST_S3_ERROR
    return LAST_S3_ERROR


def upload_file_to_s3(file_data, file_name: str) -> bool:
    """Upload file (filepath, bytes, or file-like object) to S3 bucket.

    Returns True if successfully uploaded and verified with head_object.
    Returns False and records error in LAST_S3_ERROR on failure.
    """
    global LAST_S3_ERROR
    LAST_S3_ERROR = None

    client = get_s3_client()
    if client is None:
        LAST_S3_ERROR = "S3 client is not initialized. Please verify AWS credentials."
        print(f"S3 upload error: {LAST_S3_ERROR}")
        return False

    try:
        # Determine content type for proper MIME headers in S3
        extra_args = {}
        lower_name = file_name.lower()
        if lower_name.endswith(".csv"):
            extra_args["ContentType"] = "text/csv"
        elif lower_name.endswith(".pdf"):
            extra_args["ContentType"] = "application/pdf"

        if isinstance(file_data, str) and os.path.exists(file_data):
            if extra_args:
                client.upload_file(file_data, BUCKET_NAME, file_name, ExtraArgs=extra_args)
            else:
                client.upload_file(file_data, BUCKET_NAME, file_name)

        elif isinstance(file_data, bytes):
            bio = io.BytesIO(file_data)
            if extra_args:
                client.upload_fileobj(bio, BUCKET_NAME, file_name, ExtraArgs=extra_args)
            else:
                client.upload_fileobj(bio, BUCKET_NAME, file_name)

        elif hasattr(file_data, "read"):
            if hasattr(file_data, "seek"):
                file_data.seek(0)
            if extra_args:
                client.upload_fileobj(file_data, BUCKET_NAME, file_name, ExtraArgs=extra_args)
            else:
                client.upload_fileobj(file_data, BUCKET_NAME, file_name)

        else:
            LAST_S3_ERROR = f"Unsupported file data type: {type(file_data)}"
            print(LAST_S3_ERROR)
            return False

        # Confirm upload by verifying object exists in bucket
        client.head_object(Bucket=BUCKET_NAME, Key=file_name)

        print(
            f"File {file_name} uploaded and verified successfully "
            f"to S3 bucket '{BUCKET_NAME}'!"
        )
        return True

    except Exception as e:
        LAST_S3_ERROR = str(e)
        print(f"S3 upload failed for {file_name}: {e}")
        return False
