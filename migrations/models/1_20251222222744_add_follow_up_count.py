from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:  # noqa: ARG001
    return """
        ALTER TABLE "leads" ADD "follow_up_count" INT NOT NULL DEFAULT 0;
        COMMENT ON COLUMN "leads"."follow_up_count" IS 'Количество отправленных follow-up';"""


async def downgrade(db: BaseDBAsyncClient) -> str:  # noqa: ARG001
    return """
        ALTER TABLE "leads" DROP COLUMN "follow_up_count";"""


MODELS_STATE = (
    "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"
)
