from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:  # noqa: ARG001
    return """
        CREATE TABLE IF NOT EXISTS "llm_usage" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "model" VARCHAR(100) NOT NULL,
    "request_type" VARCHAR(50) NOT NULL,
    "input_tokens" INT NOT NULL,
    "output_tokens" INT NOT NULL,
    "cache_creation_tokens" INT NOT NULL DEFAULT 0,
    "cache_read_tokens" INT NOT NULL DEFAULT 0,
    "cost_input" INT NOT NULL,
    "cost_output" INT NOT NULL,
    "cost_cache_creation" INT NOT NULL DEFAULT 0,
    "cost_cache_read" INT NOT NULL DEFAULT 0,
    "total_cost" INT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lead_id" INT REFERENCES "leads" ("id") ON DELETE SET NULL
);
COMMENT ON COLUMN "llm_usage"."model" IS 'Модель Claude';
COMMENT ON COLUMN "llm_usage"."request_type" IS 'Тип запроса (greeting, free_chat, etc.)';
COMMENT ON COLUMN "llm_usage"."input_tokens" IS 'Input tokens';
COMMENT ON COLUMN "llm_usage"."output_tokens" IS 'Output tokens';
COMMENT ON COLUMN "llm_usage"."cache_creation_tokens" IS 'Cache creation tokens';
COMMENT ON COLUMN "llm_usage"."cache_read_tokens" IS 'Cache read tokens';
COMMENT ON COLUMN "llm_usage"."cost_input" IS 'Стоимость input токенов в центах';
COMMENT ON COLUMN "llm_usage"."cost_output" IS 'Стоимость output токенов в центах';
COMMENT ON COLUMN "llm_usage"."cost_cache_creation" IS 'Стоимость cache creation в центах';
COMMENT ON COLUMN "llm_usage"."cost_cache_read" IS 'Стоимость cache read в центах';
COMMENT ON COLUMN "llm_usage"."total_cost" IS 'Общая стоимость в центах';
COMMENT ON COLUMN "llm_usage"."created_at" IS 'Дата создания';
COMMENT ON COLUMN "llm_usage"."lead_id" IS 'Связанный лид (если есть)';
COMMENT ON TABLE "llm_usage" IS 'Трекинг использования LLM API.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:  # noqa: ARG001
    return """
        DROP TABLE IF EXISTS "llm_usage";"""


MODELS_STATE = (
    "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"
    "t5/B9Vwr5N"
)
