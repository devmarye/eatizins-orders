import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Created outside the handler so warm invocations can reuse it.
table = boto3.resource("dynamodb").Table(os.environ["ORDERS_TABLE"])


def json_default(value):
    # DynamoDB returns numbers as Decimal objects.
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=json_default),
    }


def create_order(event):
    try:
        body = json.loads(event.get("body") or "")
    except (json.JSONDecodeError, TypeError):
        return response(400, {"message": "Body must be valid JSON"})

    if not isinstance(body, dict):
        return response(400, {"message": "Body must be a JSON object"})

    name = body.get("customerName")
    items = body.get("items")

    if not isinstance(name, str) or not name.strip():
        return response(400, {"message": "customerName is required"})

    if not isinstance(items, list) or not items:
        return response(400, {"message": "items must be a non-empty list"})

    clean_items = []

    for item in items:
        if not isinstance(item, dict):
            return response(400, {"message": "Each item must be an object"})

        product = item.get("product")
        quantity = item.get("quantity")

        if not isinstance(product, str) or not product.strip():
            return response(400, {"message": "Each item needs a product"})

        if type(quantity) is not int or quantity <= 0:
            return response(
                400,
                {"message": "quantity must be a positive whole number"},
            )

        clean_items.append({
            "product": product.strip(),
            "quantity": quantity,
        })

    order = {
        "orderId": str(uuid.uuid4()),
        "customerName": name.strip(),
        "items": clean_items,
        "status": "RECEIVED",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    table.put_item(
        Item=order,
        ConditionExpression="attribute_not_exists(orderId)",
    )

    logger.info("Order created: %s", order["orderId"])
    return response(201, order)


def get_order(event):
    order_id = (event.get("pathParameters") or {}).get("orderId")

    if not order_id:
        return response(400, {"message": "orderId is required"})

    result = table.get_item(
        Key={"orderId": order_id},
        ConsistentRead=True,
    )

    if "Item" not in result:
        return response(404, {"message": "Order not found"})

    return response(200, result["Item"])


def lambda_handler(event, context):
    try:
        method = event.get("httpMethod")
        resource = event.get("resource")

        if method == "POST" and resource == "/orders":
            return create_order(event)

        if method == "GET" and resource == "/orders/{orderId}":
            return get_order(event)

        return response(404, {"message": "Route not found"})

    except Exception:
        logger.exception("Order request failed")
        return response(500, {"message": "Internal server error"})