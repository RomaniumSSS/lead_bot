from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(_db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "leads" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "telegram_id" BIGINT NOT NULL UNIQUE,
    "username" VARCHAR(255),
    "first_name" VARCHAR(255),
    "last_name" VARCHAR(255),
    "status" VARCHAR(4) NOT NULL DEFAULT 'new',
    "task" TEXT,
    "budget" VARCHAR(255),
    "deadline" VARCHAR(255),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "last_message_at" TIMESTAMPTZ
);
COMMENT ON COLUMN "leads"."telegram_id" IS 'Telegram User ID';
COMMENT ON COLUMN "leads"."username" IS '@username в Telegram';
COMMENT ON COLUMN "leads"."first_name" IS 'Имя';
COMMENT ON COLUMN "leads"."last_name" IS 'Фамилия';
COMMENT ON COLUMN "leads"."status" IS 'Статус лида';
COMMENT ON COLUMN "leads"."task" IS 'Какая задача у лида';
COMMENT ON COLUMN "leads"."budget" IS 'Бюджет';
COMMENT ON COLUMN "leads"."deadline" IS 'Когда нужно решить';
COMMENT ON COLUMN "leads"."created_at" IS 'Дата создания';
COMMENT ON COLUMN "leads"."updated_at" IS 'Дата обновления';
COMMENT ON COLUMN "leads"."last_message_at" IS 'Последнее сообщение от лида';
COMMENT ON TABLE "leads" IS 'Модель лида (потенциального клиента).';
CREATE TABLE IF NOT EXISTS "conversations" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "role" VARCHAR(9) NOT NULL,
    "content" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lead_id" INT NOT NULL REFERENCES "leads" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "conversations"."role" IS 'Роль отправителя';
COMMENT ON COLUMN "conversations"."content" IS 'Текст сообщения';
COMMENT ON COLUMN "conversations"."created_at" IS 'Дата отправки';
COMMENT ON COLUMN "conversations"."lead_id" IS 'Связанный лид';
COMMENT ON TABLE "conversations" IS 'Модель диалога (история сообщений).';
CREATE TABLE IF NOT EXISTS "meetings" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "scheduled_at" TIMESTAMPTZ NOT NULL,
    "status" VARCHAR(9) NOT NULL DEFAULT 'scheduled',
    "notes" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lead_id" INT NOT NULL REFERENCES "leads" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "meetings"."scheduled_at" IS 'Дата и время встречи';
COMMENT ON COLUMN "meetings"."status" IS 'Статус встречи';
COMMENT ON COLUMN "meetings"."notes" IS 'Заметки о встрече';
COMMENT ON COLUMN "meetings"."created_at" IS 'Дата создания';
COMMENT ON COLUMN "meetings"."updated_at" IS 'Дата обновления';
COMMENT ON COLUMN "meetings"."lead_id" IS 'Связанный лид';
COMMENT ON TABLE "meetings" IS 'Модель встречи с лидом.';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(_db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztW1tz2jgU/isentKZbAaMCbBPSxLSss1lJ6G7nXY7jLAFeOILteVNMp3899XN6PhGwS"
    "HUJLxojKQjS993pHOR+VFzfQs74dGp7/2HgxAR2/dqv2s/ah5yMX3IbT/Uamg+V62sgqCx"
    "wwVM0JO3oHFIAmQS2jhBTohplYVDM7Dn8mW1f6O60TBZ2cS8NHjZ4uWYlYapgYYOL+uqWY"
    "o1Rb12oHoZDV7qqpdRB60TTXWSg4hSiHXBPCzw6u67I7Yyyzfp0mxvusuLiDz7e4RHxJ9i"
    "MsMBXcrXb7Ta9iz8gMP45/xuNLGxYyV0w7bYALx+RB7nvG7gkXPekeEzHpm+E7me6jx/JD"
    "PfW/S2PcJqp9jDASKYDU+CiKmIFzmOVKlYa8RMVRcxRSBj4QmKHKZoTDqjZ3ElYE1WUZ1l"
    "OkpnE/IFTtlbftMbRtvoNI+NDu3CZ7KoaT+J5am1C0GOwNWw9sTbEUGiB4dR4Rb4dLQMcq"
    "czFPS9yOXwDeiEkGfiDIyxbApIOv00kDFsy5CMKxSUaosuxZKru14HypZQcQwUdgIUVpQ6"
    "UF49s0sm6a1VQJKLHkYO9qZkRn92lxDyd+/m9EPv5qD7jo3s07NInFRXskFnLYwxxRB9F8"
    "FCN5MkDfFDgX4DkUpwA4FF8BQpdVqsysoSGob9z0M2iBuG3x2I/8Fl7zOnxn2ULRfXV+/j"
    "7oCv04vrkzRRAWaQjlAOV2e0hdguLuArIZmizJKiR/HD9glsGGrHyF1SX31zIUHdiluJQm"
    "Fde86jPEqXkTi47N8Oe5d/JZg86w37rEVPsBjXHhynNt5iEO2fwfCDxn5qX66v+pwIPyTT"
    "gL9R9Rt+qbE5oYj4I8+/HyELnPpxbYxvQj8curLRWnYKSPzcWG1hHzcUqwZnu9kGbFuqNI"
    "QX0dWASyEsvbGiGmzA7DFfYXKXa/UYsFkezv0A21PvI37M2L0U/NITvZDDvFoanmKNjGuV"
    "qgfofuGGQUWlKFFsMBF+RO/2tHfWr3Euxsi8u0eBNUqQwlp83U/VLPpmm1zdTdcgD005jG"
    "wVbM6Qn5wIIuatOHJgC9p4xJAgIOFaTzKHKbB6xnG+k26YgG/osGMNnLvwpXBQeYw/K3qo"
    "7oL2kcTWIwlCd/00QG6uiTuxp4UYpgQ3Y+lKokmdajEZ7VOIA21wtpa56up6s9nW683jTs"
    "tot1ud+gLkbNMytE8G7xngCU8lZkAhHtEp8ufc+C0fbChTKjaQOG7Alv0Rz0Xsbl2LsS8T"
    "dOmt1gphF+1VGHjxtiTAEzsIyWhdiJNSvxhkfpiLw9IsH9K+CLoOKgFuQqgC2OogNBIIS9"
    "MEzFSFMKceLYnCsgkfJb29tELNw/e1ZY5wbPjVs9EUaYVCJ6UMHcYKZBiFVBhpIggK79ZJ"
    "6cT9K6DyDQRUHjzL5G8iGIGJgzZIHBjNZ5Kz7eTOOLKoK7nOSaUkqsCZ2CrQnz9WHrShV+"
    "aAsmjg5djeWjYBylQBa5QJYAyg+jJcaQISLBDlyASa4KUDjIg42szKMPUG052JTHU7fcCV"
    "yVG/4nRnNLdK6kdScof0A95eJNIYOjB2pe8zXo2uyMmnIgEXhyGa4hL6kiO+AaXZsFGAGb"
    "FGRh0MoBSiplXuJr2VuJd5QSerQhoW85A5jjI3AMVp6MR9a/KjkVQmS4qff7zBzuIblPz7"
    "gfSXKm/uniCxy11Mt543fSaml2KUtwnnS16WxMDm3JcAzIuvTCC9m7w10dU5KH1g6CELCj"
    "rysCw678QrzOfcdWx6Gvsbiq3fUITmDFuRU8onTcvuklfagRoMtDbOCK+h4G/Db9jxjOlC"
    "V5+VN92gPrzo93GeT3AOP8Wp1IVAFXJF0IUwAb6JT6ekT786L61qJlH3KSMQgqVDtzeXBt"
    "injJRm7FNG66aM9h9T7j+m3C0advxjyh4ObHNWy0kPyJbDZdkBpPr8LDdQHC/uY+atx8ws"
    "fynzcatexwKRX/zvk9VRfPnrUrY11gBRdt9NABv1+goA0l6FAPK2Ff8H9eft9dW6/4P65N"
    "EFfrVskxxqjh2Sb9WEdQmKbNXLA7R0LJbywdgAJ3mWfZvm5el/2V+ibw=="
)
