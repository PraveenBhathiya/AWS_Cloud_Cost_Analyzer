import boto3
import pandas as pd
import datetime

# ===============================
# CONFIGURATION
# ===============================
REGION = "ap-south-1"  # change as needed
#S3_BUCKET = "cloud-analyzer-reports-3842"  # create this bucket first
REPORT_FILE = r"C:\Users\MSII\Desktop\cloud_resource_analyzer\dashboard\aws_resource_report.csv"

# ===============================
# COST ESTIMATION HELPERS
# (Approximate pricing in USD - you can refine with AWS Pricing API later)
# ===============================
EC2_COST_PER_HOUR = 0.023  # t2.micro approx
RDS_COST_PER_HOUR = 0.041  # db.t3.micro approx
S3_COST_PER_GB = 0.023     # Standard storage

HOURS_PER_MONTH = 730  # average hours in month


# ===============================
# COLLECT EC2 DATA
# ===============================
def analyze_ec2():
    ec2 = boto3.client("ec2", region_name=REGION)
    cloudwatch = boto3.client("cloudwatch", region_name=REGION)

    instances = ec2.describe_instances()
    rows = []

    for reservation in instances["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]

            # CPU Utilization (avg of last 7 days)
            metric = cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=datetime.datetime.utcnow() - datetime.timedelta(days=7),
                EndTime=datetime.datetime.utcnow(),
                Period=3600,
                Statistics=["Average"]
            )

            avg_cpu = 0
            if metric["Datapoints"]:
                avg_cpu = sum([d["Average"] for d in metric["Datapoints"]]) / len(metric["Datapoints"])

            est_cost = EC2_COST_PER_HOUR * HOURS_PER_MONTH
            potential_saving = est_cost if avg_cpu < 5 else 0  # assume idle if CPU < 5%

            rows.append({
                "ResourceID": instance_id,
                "Service": "EC2",
                "ResourceType": instance.get("InstanceType", "unknown"),
                "UsageMetric": f"CPU {avg_cpu:.2f}%",
                "EstimatedCostUSD": round(est_cost, 2),
                "PotentialSavingsUSD": round(potential_saving, 2)
            })

    return rows


# ===============================
# COLLECT RDS DATA
# ===============================
def analyze_rds():
    rds = boto3.client("rds", region_name=REGION)
    cloudwatch = boto3.client("cloudwatch", region_name=REGION)

    instances = rds.describe_db_instances()["DBInstances"]
    rows = []

    for db in instances:
        db_id = db["DBInstanceIdentifier"]

        # CPU Utilization (avg of last 7 days)
        metric = cloudwatch.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
            StartTime=datetime.datetime.utcnow() - datetime.timedelta(days=7),
            EndTime=datetime.datetime.utcnow(),
            Period=3600,
            Statistics=["Average"]
        )

        avg_cpu = 0
        if metric["Datapoints"]:
            avg_cpu = sum([d["Average"] for d in metric["Datapoints"]]) / len(metric["Datapoints"])

        est_cost = RDS_COST_PER_HOUR * HOURS_PER_MONTH
        potential_saving = est_cost if avg_cpu < 5 else 0

        rows.append({
            "ResourceID": db_id,
            "Service": "RDS",
            "ResourceType": db.get("DBInstanceClass", "unknown"),
            "UsageMetric": f"CPU {avg_cpu:.2f}%",
            "EstimatedCostUSD": round(est_cost, 2),
            "PotentialSavingsUSD": round(potential_saving, 2)
        })

    return rows


# ===============================
# COLLECT S3 DATA
# ===============================
def analyze_s3():
    s3 = boto3.client("s3", region_name=REGION)
    buckets = s3.list_buckets()["Buckets"]

    rows = []

    for bucket in buckets:
        bucket_name = bucket["Name"]

        # Estimate size (simplified: just count #objects * 1MB)
        # For real use, enable StorageMetrics in CloudWatch
        size_gb = 0
        try:
            paginator = s3.get_paginator("list_objects_v2")
            total_size = 0
            for page in paginator.paginate(Bucket=bucket_name):
                for obj in page.get("Contents", []):
                    total_size += obj["Size"]
            size_gb = total_size / (1024 ** 3)
        except Exception as e:
            pass

        est_cost = size_gb * S3_COST_PER_GB
        potential_saving = est_cost * 0.5 if size_gb > 1 else 0  # Suggest Glacier for large buckets

        rows.append({
            "ResourceID": bucket_name,
            "Service": "S3",
            "ResourceType": "Bucket",
            "UsageMetric": f"Size {size_gb:.2f} GB",
            "EstimatedCostUSD": round(est_cost, 2),
            "PotentialSavingsUSD": round(potential_saving, 2)
        })

    return rows


# ===============================
# MAIN SCRIPT
# ===============================
if __name__ == "__main__":
    all_rows = []

    print("Analyzing EC2...")
    all_rows.extend(analyze_ec2())

    print("Analyzing RDS...")
    all_rows.extend(analyze_rds())

    print("Analyzing S3...")
    all_rows.extend(analyze_s3())

    # Save to CSV
    df = pd.DataFrame(all_rows)
    df.to_csv(REPORT_FILE, index=False)
    print(f"Report saved as {REPORT_FILE}")

    # Upload to S3 for QuickSight
    s3 = boto3.client("s3", region_name=REGION)
    try:
        s3.upload_file(REPORT_FILE, S3_BUCKET, REPORT_FILE)
        print(f"Uploaded report to s3://{S3_BUCKET}/{REPORT_FILE}")
    except Exception as e:
        print(f"Error uploading to S3: {e}")
