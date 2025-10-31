#!/usr/bin/env python3
"""
Schema validation script for ClickHouse monitor database
This script validates that all required tables exist and have correct structure
"""

from pmconnector import ResourceConnector
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_tables():
    """Validate that all required tables exist in monitor database"""
    try:
        client = ResourceConnector.connect_clickhouse_static("monitor")
        
        # Expected tables
        expected_tables = [
            'service_status',
            'service_metrics', 
            'service_logs',
            'services',
            'service_relations',
            'alert_rules',
            'service_status_summary'
        ]
        
        # Check if database exists
        result = client.execute("SHOW DATABASES")
        databases = [row[0] for row in result]
        if 'monitor' not in databases:
            logger.error("Monitor database does not exist!")
            return False
        
        # Check tables
        result = client.execute("SHOW TABLES FROM monitor")
        existing_tables = [row[0] for row in result]
        
        logger.info(f"Existing tables in monitor database: {existing_tables}")
        
        missing_tables = set(expected_tables) - set(existing_tables)
        if missing_tables:
            logger.error(f"Missing tables: {missing_tables}")
            return False
        
        # Validate table structures
        for table in expected_tables:
            try:
                result = client.execute(f"DESCRIBE monitor.{table}")
                columns = [row[0] for row in result]
                logger.info(f"Table {table} columns: {columns}")
            except Exception as e:
                logger.error(f"Failed to describe table {table}: {e}")
                return False
        
        logger.info("All tables validated successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return False

def test_data_insertion():
    """Test inserting sample data into tables"""
    try:
        client = ResourceConnector.connect_clickhouse_static("monitor")
        
        # Test service insertion
        test_service = """
        INSERT INTO monitor.services (service_id, label, service_type, stack, status_config)
        VALUES ('test-service-1', 'Test Service', 'api_endpoint', 'application', '{"url": "http://test.example.com"}')
        """
        client.execute(test_service)
        
        # Test status insertion
        test_status = """
        INSERT INTO monitor.service_status (service_id, timestamp, status_code, message, service_type, stack)
        VALUES ('test-service-1', now64(), 0, 'Service is healthy', 'api_endpoint', 'application')
        """
        client.execute(test_status)
        
        # Test metrics insertion
        test_metrics = """
        INSERT INTO monitor.service_metrics (service_id, timestamp, metric_name, metric_value, metric_unit)
        VALUES ('test-service-1', now64(), 'response_time', 150.0, 'ms')
        """
        client.execute(test_metrics)
        
        logger.info("Test data insertion successful!")
        
        # Query test data
        result = client.execute("SELECT COUNT(*) FROM monitor.service_status WHERE service_id = 'test-service-1'")
        logger.info(f"Status records for test service: {result[0][0]}")
        
        # Cleanup test data
        client.execute("DELETE FROM monitor.services WHERE service_id = 'test-service-1'")
        client.execute("DELETE FROM monitor.service_status WHERE service_id = 'test-service-1'")
        client.execute("DELETE FROM monitor.service_metrics WHERE service_id = 'test-service-1'")
        
        logger.info("Test data cleanup completed!")
        return True
        
    except Exception as e:
        logger.error(f"Data insertion test failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting schema validation...")
    
    if validate_tables():
        logger.info("Schema validation passed!")
        
        if test_data_insertion():
            logger.info("Data insertion test passed!")
        else:
            logger.error("Data insertion test failed!")
    else:
        logger.error("Schema validation failed!")
