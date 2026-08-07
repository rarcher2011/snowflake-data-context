import os

from openai_snowflake_agent_context import (
    SnowflakeContextConfig,
    SnowflakeMetadataProvider,
    connect_with_private_key,
)

config = SnowflakeContextConfig(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    database=os.environ.get("SNOWFLAKE_DATABASE"),
    schema=os.environ.get("SNOWFLAKE_SCHEMA"),
    private_key_path=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
)

connection = connect_with_private_key(
    config,
    private_key_passphrase=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
)

provider = SnowflakeMetadataProvider(connection, config)

def sample():
    cursor = connection.cursor()
    cd = cursor.execute("select * from rbac_dev.sample_data.gas_sample limit 1")
    print(cd.fetchone())

analysis = provider.analyze_schema_descriptions()
analysis.print_context()
import pdb; pdb.set_trace()
