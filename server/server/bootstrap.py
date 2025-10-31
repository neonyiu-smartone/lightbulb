import json
import logging
import yaml

from pmconnector import ResourceConnector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Grant statements to be executed manually by developer with clickhouse-client
grants = """
-- Create user monitor with password (replace 'your_password' with actual password)
CREATE USER IF NOT EXISTS monitor ON CLUSTER production IDENTIFIED WITH plaintext_password BY 'your_password';

-- Grant access to system tables for monitoring
GRANT SELECT ON system.* TO monitor ON CLUSTER production;

-- Grant all permissions on monitor database
GRANT ALL ON monitor.* TO monitor ON CLUSTER production;

-- Assign 'program' settings profile to monitor user
ALTER USER monitor ON CLUSTER production SETTINGS PROFILE 'program';

-- Create monitor database if not exists
CREATE DATABASE IF NOT EXISTS monitor ON CLUSTER production;
"""

# Table creation statements for services status tracking
create_status_table = """
CREATE TABLE IF NOT EXISTS monitor.service_status ON CLUSTER production (
    service_id String,
    time DateTime,
    status_code UInt8,
    message String DEFAULT ''
) ENGINE = ReplicatedMergeTree()
PARTITION BY toYYYYMM(time)
ORDER BY (service_id, time)
TTL time + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;
"""

# Table for storing service metrics
create_metrics_table = """
CREATE TABLE IF NOT EXISTS monitor.service_metrics ON CLUSTER production (
    service_id String,
    time DateTime,
    metric_name String,
    metric_value Float64,
    metric_unit String DEFAULT '',
    tags Map(String, String) DEFAULT map(),
    created_at DateTime DEFAULT now()
) ENGINE = ReplicatedMergeTree()
PARTITION BY toYYYYMM(time)
ORDER BY (service_id, metric_name, time)
TTL time + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;
"""

# Table for storing service logs
create_logs_table = """
CREATE TABLE IF NOT EXISTS monitor.service_logs ON CLUSTER production (
    service_id String,
    time DateTime,
    log_level String,
    message String,
    source String DEFAULT '',
    error_code Nullable(String),
    stack_trace Nullable(String),
    context Map(String, String) DEFAULT map(),
    created_at DateTime64(3, 'UTC') DEFAULT now64()
) ENGINE = ReplicatedMergeTree()
PARTITION BY toYYYYMM(time)
ORDER BY (service_id, time)
TTL time + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;
"""

# Table for service configuration and metadata
create_services_table = """
CREATE TABLE IF NOT EXISTS monitor.services ON CLUSTER production (
    service_id String,
    label String,
    service_type String,
    status_config String,
    metric_config String DEFAULT '',
    enabled UInt8 DEFAULT 1,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplicatedMergeTree()
ORDER BY service_id
SETTINGS index_granularity = 8192;
"""

# Table for service relationships/dependencies
create_relations_table = """
CREATE TABLE IF NOT EXISTS monitor.service_relations ON CLUSTER production (
    relation_id String,
    source_service_id String,
    target_service_id String,
    relation_type String DEFAULT 'dependency',
    enabled UInt8 DEFAULT 1,
    created_at DateTime DEFAULT now()
) ENGINE = ReplicatedMergeTree()
ORDER BY (source_service_id, target_service_id)
SETTINGS index_granularity = 8192;
"""

# Table for alert rules and configurations
create_alert_rules_table = """
CREATE TABLE IF NOT EXISTS monitor.alert_rules ON CLUSTER production (
    rule_id String,
    service_id String,
    rule_name String,
    condition String,
    threshold Float64,
    severity String,
    enabled UInt8 DEFAULT 1,
    notification_channels Array(String) DEFAULT [],
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplicatedMergeTree()
ORDER BY (service_id, rule_id)
SETTINGS index_granularity = 8192;
"""

create_workflow_monitor_configs_table = """
CREATE TABLE IF NOT EXISTS monitor.workflow_monitor_configs ON CLUSTER production (
    workflow_type String,
    service_id String,
    interval_minute UInt16
) ENGINE = ReplicatedMergeTree()
ORDER BY (workflow_type, service_id)
SETTINGS index_granularity = 8192;
"""

# Summary table for aggregated service status data
# Uses AggregatingMergeTree to properly merge duplicate aggregations
# that may occur from late-arriving data or materialized view rebuilds
create_status_summary_table = """
CREATE TABLE IF NOT EXISTS monitor.service_status_summary ON CLUSTER production (
    service_id String,
    stime DateTime,
    last_check AggregateFunction(max, DateTime),
    last_status_code AggregateFunction(argMax, UInt8, DateTime),
    last_message AggregateFunction(argMax, String, DateTime),
    check_count AggregateFunction(count),
    failure_count AggregateFunction(sum, UInt32)
) ENGINE = ReplicatedAggregatingMergeTree()
PARTITION BY toYYYYMM(stime)
ORDER BY (service_id, stime)
TTL stime + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;
"""

create_status_summary_view = """
CREATE MATERIALIZED VIEW IF NOT EXISTS monitor.service_status_summary_mv ON CLUSTER production
TO monitor.service_status_summary
AS
SELECT
    service_id,
    toStartOfDay(time) as stime,
    maxState(time) as last_check,
    argMaxState(status_code, time) as last_status_code,
    argMaxState(message, time) as last_message,
    countState() as check_count,
    sumState(toUInt32(status_code = 2)) as failure_count
FROM monitor.service_status
GROUP BY service_id, stime;
"""

def execute_table_creation():
    """Execute table creation statements using pmconnector"""
    try:
        # Connect to ClickHouse using monitor user
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        tables = [
            ("service_status", create_status_table),
            ("service_metrics", create_metrics_table),
            ("service_logs", create_logs_table),
            ("services", create_services_table),
            ("service_relations", create_relations_table),
            ("alert_rules", create_alert_rules_table),
            ("workflow_monitor_configs", create_workflow_monitor_configs_table),
            ("service_status_summary", create_status_summary_table),
            ("service_status_summary_mv", create_status_summary_view)
        ]
        
        for table_name, create_sql in tables:
            try:
                logger.info(f"Creating table: {table_name}")
                client.execute(create_sql)
                logger.info(f"Successfully created table: {table_name}")
            except Exception as e:
                logger.error(f"Failed to create table {table_name}: {e}")
                raise
        
        logger.info("All tables created successfully!")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

# Populate initial data into the monitor database, by reading from config/services.yaml
def populate_initial_data():
    """Populate initial data into the monitor database"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        # load config/services.yaml
        with open("config/services.yaml", "r") as f:
            config = yaml.safe_load(f)
            initial_services = config.get("serviceNodes", [])
            if not initial_services:
                logger.warning("No initial services found in config/services.yaml")
                return
            client.execute(f"INSERT INTO monitor.services (service_id, label, service_type, status_config, metric_config) VALUES",
                           ((service['id'], service['label'], service['type'],
                             json.dumps(service['status']) if service['status'] else '[]',
                             json.dumps(service['metric']) if service['metric'] else '[]'
                             ) for service in initial_services))
            initial_relations = config.get("serviceRelations", [])
            if not initial_relations:
                logger.warning("No initial realtions found in config/services.yaml")
                return
            client.execute(f"INSERT INTO monitor.service_relations (relation_id, source_service_id, target_service_id) VALUES",
                           ((relation['id'], relation['source'], relation['target']) for relation in initial_relations))
    except Exception as e:
        logger.error(f"Failed to populate initial data: {e}")

if __name__ == "__main__":
    logger.info("Starting database schema initialization...")
    logger.info("=" * 50)
    execute_table_creation()
    
    logger.info("populating initial services...")
    logger.info("=" * 50)
    populate_initial_data()

