import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

table = boto3.resource("dynamodb").Table(os.environ["ORDERS_TABLE"])

def process_order(order_id):
    try:
        table.update_item(
            Key={"orderId": order_id},
            UpdateExpression="SET #status = :processed",
            ConditionExpression="#status = :received",
            ExpressionAttributeNames={
                "#status": "status",
            },
            ExpressionAttributeValues={
                ":received": "RECEIVED",
                ":processed": "PROCESSED",
            },
        )

        logger.info("Order processed: %s", order_id)

    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Missing orders and orders no longer in RECEIVED are not changed.
            logger.warning(
                "Order skipped; missing or no longer RECEIVED: %s",
                order_id,
            )
            return

        raise


def lambda_handler(event, context):
    failures = []

    for record in event["Records"]:
        try:
            message = json.loads(record["body"])
            order_id = message["orderId"]

            if not isinstance(order_id, str) or not order_id.strip():
                raise ValueError("orderId must be a non-empty string")

            process_order(order_id)

        except Exception:
            logger.exception(
                "Failed to process message: %s",
                record["messageId"],
            )
            failures.append({
                "itemIdentifier": record["messageId"],
            })

    return {"batchItemFailures": failures}