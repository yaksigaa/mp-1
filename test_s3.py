
import boto3
from botocore.exceptions import ClientError

BUCKET_NAME = "pfa1"
REGION = "eu-north-1"

try:
    s3 = boto3.client("s3", region_name=REGION)

    print("Checking AWS connection...")

    s3.head_bucket(Bucket=BUCKET_NAME)
    print("AWS CONNECTION SUCCESSFUL!")

    print("\nUploading test file...")

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="uploads/test_connection.txt",
        Body=b"My S3 connection is working!"
    )

    print("TEST FILE UPLOADED SUCCESSFULLY!")

    print("\nChecking uploaded file...")

    response = s3.list_objects_v2(
        Bucket=BUCKET_NAME,
        Prefix="uploads/"
    )

    for item in response.get("Contents", []):
        print("Found:", item["Key"])

except Exception as e:
    print("ERROR:", repr(e))
