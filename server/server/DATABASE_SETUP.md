# Database Schema Setup Guide

This guide explains how to set up the ClickHouse database schema for the lightbulb monitoring system.

## Prerequisites

1. ClickHouse cluster with production configuration
2. Access to `clickhouse-client` with admin privileges
3. `pmconnector` library installed in Python environment

## Setup Steps

### 1. Manual Grant Execution

First, execute the grant statements manually using `clickhouse-client` as an admin user:

```bash
# Connect to ClickHouse as admin
clickhouse-client --host your-clickhouse-host --user admin

# Execute the following grants:
```

```sql
-- Create user monitor with password (replace 'your_password' with actual password)
CREATE USER IF NOT EXISTS monitor IDENTIFIED WITH plaintext_password BY 'your_password';

-- Grant access to system tables for monitoring
GRANT SELECT ON system.* TO monitor;

-- Grant all permissions on monitor database
GRANT ALL ON monitor.* TO monitor;

-- Assign 'program' settings profile to monitor user
ALTER USER monitor SETTINGS PROFILE 'program';

-- Create monitor database if not exists
CREATE DATABASE IF NOT EXISTS monitor ON CLUSTER production;
```

### 2. Table Creation

Run the bootstrap script to create all required tables:

```bash
cd /path/to/server/server
python bootstrap.py
```

### 3. Schema Validation

Validate that all tables were created correctly:

```bash
python validate_schema.py
```

## Database Schema

### Core Tables

#### 1. service_status
Stores real-time status information for all monitored services.

**Columns:**
- `service_id` (String): Unique service identifier
- `timestamp` (DateTime64): Status check timestamp
- `status_code` (UInt8): Status code (0-5)
- `message` (String): Human-readable status message
- `service_type` (String): Type of service (temporal_workflow, python_process, etc.)
- `stack` (String): Service stack category
- `details` (String): Additional context (JSON format)
- `response_time_ms` (Nullable UInt32): Response time in milliseconds
- `cpu_usage` (Nullable Float32): CPU usage percentage
- `memory_usage` (Nullable Float32): Memory usage percentage

**Partitioning:** Monthly partitions by timestamp
**TTL:** 90 days retention

#### 2. service_metrics
Stores time-series metrics for service performance monitoring.

**Columns:**
- `service_id` (String): Service identifier
- `timestamp` (DateTime64): Metric collection time
- `metric_name` (String): Name of the metric
- `metric_value` (Float64): Metric value
- `metric_unit` (String): Unit of measurement
- `tags` (Map(String, String)): Additional metric tags

**Partitioning:** Monthly partitions by timestamp
**TTL:** 90 days retention

#### 3. service_logs
Stores log entries from monitored services.

**Columns:**
- `service_id` (String): Service identifier
- `timestamp` (DateTime64): Log entry timestamp
- `log_level` (String): Log level (ERROR, WARN, INFO, DEBUG)
- `message` (String): Log message
- `source` (String): Log source (file, component, etc.)
- `error_code` (Nullable String): Error code if applicable
- `stack_trace` (Nullable String): Stack trace for errors
- `context` (Map(String, String)): Additional context

**Partitioning:** Monthly partitions by timestamp
**TTL:** 90 days retention

#### 4. services
Configuration and metadata for all monitored services.

**Columns:**
- `service_id` (String): Unique service identifier
- `label` (String): Human-readable service name
- `service_type` (String): Service type
- `stack` (String): Service stack
- `status_config` (String): Status check configuration (JSON)
- `metric_config` (String): Metric collection configuration (JSON)
- `enabled` (UInt8): Whether monitoring is enabled

#### 5. service_relations
Defines dependencies and relationships between services.

**Columns:**
- `relation_id` (String): Unique relation identifier
- `source_service_id` (String): Source service
- `target_service_id` (String): Target service
- `relation_type` (String): Type of relationship
- `enabled` (UInt8): Whether relation is active

#### 6. alert_rules
Configuration for alerting rules and thresholds.

**Columns:**
- `rule_id` (String): Unique rule identifier
- `service_id` (String): Target service
- `rule_name` (String): Rule name
- `condition` (String): Alert condition
- `threshold` (Float64): Alert threshold value
- `severity` (String): Alert severity level
- `notification_channels` (Array(String)): Notification destinations

### Materialized Views

#### service_status_summary
Real-time aggregated view of service status by hour.

**Purpose:** Provides quick access to hourly service health summaries for dashboards and reporting.

## Status Codes

- `0`: OK - Service is healthy
- `1`: DEGRADED - Running with warnings
- `2`: FAILED - Critical failure
- `3`: STARTING - Initializing
- `4`: STOPPED - Intentionally stopped
- `5`: UNKNOWN - Unable to determine status

## Query Examples

### Get current status of all services
```sql
SELECT 
    service_id,
    argMax(status_code, timestamp) as current_status,
    argMax(message, timestamp) as last_message,
    argMax(timestamp, timestamp) as last_check
FROM monitor.service_status 
GROUP BY service_id;
```

### Get service health over time
```sql
SELECT 
    service_id,
    toStartOfHour(timestamp) as hour,
    avg(response_time_ms) as avg_response_time,
    countIf(status_code = 2) as failures,
    count() as total_checks
FROM monitor.service_status
WHERE timestamp >= now() - INTERVAL 24 HOUR
GROUP BY service_id, hour
ORDER BY service_id, hour;
```

### Get top failing services
```sql
SELECT 
    service_id,
    countIf(status_code = 2) / count() * 100 as failure_rate,
    count() as total_checks
FROM monitor.service_status
WHERE timestamp >= now() - INTERVAL 1 HOUR
GROUP BY service_id
HAVING failure_rate > 5
ORDER BY failure_rate DESC;
```

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure monitor user has correct grants
2. **Cluster Not Found**: Verify ClickHouse cluster configuration
3. **TTL Not Working**: Check ClickHouse version and cluster settings

### Useful Commands

```sql
-- Check table sizes
SELECT 
    table,
    formatReadableSize(sum(bytes)) as size,
    sum(rows) as rows
FROM system.parts 
WHERE database = 'monitor' 
GROUP BY table;

-- Check replication status
SELECT * FROM system.replicas WHERE database = 'monitor';

-- Monitor query performance
SELECT 
    query,
    query_duration_ms,
    memory_usage
FROM system.query_log 
WHERE database = 'monitor' 
ORDER BY event_time DESC 
LIMIT 10;
```
