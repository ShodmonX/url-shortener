from sqlalchemy import BigInteger, Integer

BIGINT_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")
