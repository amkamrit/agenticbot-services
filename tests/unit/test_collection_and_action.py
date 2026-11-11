import asyncio
import json
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis import redis_client
from app.models.form_collection import FormCollection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TENANT_ID = 100

TENANT_100_CONFIG = {
    "forms": {
        "company_registration": {
            "name": "Company Registration",
            "description": "User wants to register, onboard, or sign up their business",
            "fields": {
                "company_name": "Registered name of your company or business",
                "interested_modules": "Interested modules like CSS, SMS, Viber, WhatsApp",
                "contact_number": "Contact phone or mobile number",
            },
            "action": {
                "type": "http_request",
                "method": "POST",
                "url": "https://wms-uat.worldlink.com.np/api/api/v1/messaging",
                "headers": {
                    "Api-Token": "$2y$10$IJFAo1n.9NFK6jBOWeBz.OPpzFta3ZbwFkdY7YlA7hiaMKYh3YIQi",
                    "Content-Type": "application/json",
                },
                "payload_template": {
                    "message": "Dear customer, your company registration has been recorded.",
                    "recipients": [
                        {
                            "mobile": "{contact_number}",
                            "postData": {"name": "{company_name}"},
                        }
                    ],
                },
            },
        },
        "check_billing": {
            "name": "Check Billing Status",
            "description": "User wants to check billing status, invoice, balance, or payment due",
            "fields": {
                "account_number": "Account number or customer ID",
                "registered_phone": "Registered contact phone number",
            },
            "action": {
                "type": "http_request",
                "method": "POST",
                "url": "https://wms-uat.worldlink.com.np/api/api/v1/messaging",
                "headers": {
                    "Api-Token": "$2y$10$IJFAo1n.9NFK6jBOWeBz.OPpzFta3ZbwFkdY7YlA7hiaMKYh3YIQi",
                    "Content-Type": "application/json",
                },
                "payload_template": {
                    "message": "Dear customer, your billing status inquiry for account {account_number} has been processed.",
                    "recipients": [
                        {
                            "mobile": "{registered_phone}",
                            "postData": {"name": "Account {account_number}"},
                        }
                    ],
                },
            },
        },
    }
}


async def seed_tenant_100():
    logger.info("Seeding multi-form configuration for tenant_id=%s...", TENANT_ID)

    # 1. Persist/Update to PostgreSQL
    async with AsyncSessionLocal() as db:
        stmt = select(FormCollection).where(
            FormCollection.tenant_id == TENANT_ID,
            FormCollection.status == "config",
        )
        result = await db.execute(stmt)
        record = result.scalars().first()

        if record:
            record.data = TENANT_100_CONFIG
            logger.info("Updated existing DB config for tenant %s", TENANT_ID)
        else:
            record = FormCollection(
                tenant_id=TENANT_ID,
                status="config",
                data=TENANT_100_CONFIG,
            )
            db.add(record)
            logger.info("Created new DB config for tenant %s", TENANT_ID)

        await db.commit()

    # 2. Sync to Redis cache
    redis_key = f"tenant_id:{TENANT_ID}_collection_config"
    await redis_client.set(redis_key, json.dumps(TENANT_100_CONFIG))
    logger.info("Synced multi-form config to Redis key: %s", redis_key)


if __name__ == "__main__":
    asyncio.run(seed_tenant_100())