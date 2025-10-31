from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Union
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4
import json


class ServiceCategory(str, Enum):
    DATABASE = "Database"
    APPLICATION = "Application"
    AUTOMATION = "Automation"
    ALERT = "Alert"
    PIPELINE = "Pipeline"
    PLATFORM = "Platform"
    REPORTING = "Reporting"


class HeartbeatStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


def get_timestamp():
    return datetime.now()


class Heatbeat(BaseModel):
    timestamp: datetime = Field(default_factory=get_timestamp)
    status: HeartbeatStatus = HeartbeatStatus.UNKNOWN
    message: Optional[str] = None

    class Config: json_schema_extra = {
        "example": {
            "timestamp": "2023-10-01T12:00:00Z",
            "status": "healthy",
            "message": "Service is running smoothly."
        }
    }


class Metric(BaseModel):
    name: str
    value: Union[int, float]
    unit: Optional[str] = None
    timestamp: datetime = Field(default_factory=get_timestamp)

    class Config: json_schema_extra = {
        "example": {
            "name": "CPU Usage",
            "value": 75.5,
            "unit": "%",
            "timestamp": "2023-10-01T12:00:00Z"
        }
    }


class ServiceRelationship(BaseModel):
    service_id: UUID
    relationship_type: str  # e.g., "depends_on", "related_to", etc.


class Service(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: Optional[str] = None
    relationship_type: str
    category: ServiceCategory
    owner: Optional[str] = None
    created_at: datetime = Field(default_factory=get_timestamp)
    updated_at: datetime = Field(default_factory=get_timestamp)
    heartbeat: Optional[Heatbeat] = None
    metrics: List[Metric] = Field(default_factory=list)
    upstream_services: List[ServiceRelationship] = Field(default_factory=list)
    downstream_services: List[ServiceRelationship] = Field(default_factory=list)
    metadata: Optional[Dict[str, str]] = None  # Additional metadata as key-value pairs
    tags: List[str] = Field(default_factory=list)  # Tags for categorization

    def add_upstream(self):
        pass

    def add_downstream(self):
        pass

    def update_heartbeat(self):
        pass

    def update_metric(self):
        pass


class PipelineService(Service):
    pipeline_id: UUID
    stage: Optional[str] = None  # e.g., "build", "test", "deploy"


class ServiceRegistry(BaseModel):
    services: Dict[UUID, Service] = Field(default_factory=dict)

    def add_service(self, service: Service):
        self.services[service.id] = service
        return service.id

    def get_service(self, service_id: UUID) -> Optional[Service]:
        return self.services.get(service_id)

    def get_all_services(self) -> List[Service]:
        return list(self.services.values())

    def build_dependency_graph(self) -> Dict[UUID, List[ServiceRelationship]]:
        pass


# Flowchart API Models
class ServiceNode(BaseModel):
    """Service node for flowchart visualization"""
    service_id: str
    label: str
    service_type: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "service_id": "platform-0",
                "label": "ClickHouse",
                "service_type": "database"
            }
        }


class ServiceRelation(BaseModel):
    """Service relation for flowchart visualization"""
    relation_id: str
    source: str
    target: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "relation_id": "0-1",
                "source": "platform-0",
                "target": "temporal-1"
            }
        }


class FlowchartResponse(BaseModel):
    """Response model for /flowchart endpoint"""
    serviceNodes: List[ServiceNode]
    serviceRelations: List[ServiceRelation]
    
    class Config:
        json_schema_extra = {
            "example": {
                "serviceNodes": [
                    {
                        "service_id": "platform-0",
                        "label": "ClickHouse", 
                        "service_type": "database"
                    }
                ],
                "serviceRelations": [
                    {
                        "relation_id": "0-1",
                        "source": "platform-0",
                        "target": "temporal-1"
                    }
                ]
            }
        }


# Admin API Models
class ServiceCreateRequest(BaseModel):
    """Request model for creating a new service"""
    service_id: str = Field(..., description="Unique service identifier")
    label: str = Field(..., min_length=1, max_length=100, description="Display name for the service")
    service_type: str = Field(..., description="Type of service (temporal_workflow, python_process, etc.)")
    status_config: str = Field(default='{}', description="JSON configuration for status checks")
    metric_config: str = Field(default='{}', description="JSON configuration for metrics collection")
    enabled: bool = Field(default=True, description="Whether the service is enabled")

    @field_validator('status_config', 'metric_config')
    def validate_json(cls, v):
        try:
            json.loads(v) if v else {}
            return v
        except json.JSONDecodeError:
            raise ValueError('Must be valid JSON string')

class ServiceUpdateRequest(BaseModel):
    """Request model for updating an existing service"""
    label: Optional[str] = Field(None, min_length=1, max_length=100)
    service_type: Optional[str] = None
    status_config: Optional[str] = None
    metric_config: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator('status_config', 'metric_config')
    def validate_json(cls, v):
        if v is not None:
            try:
                json.loads(v)
                return v
            except json.JSONDecodeError:
                raise ValueError('Must be valid JSON string')
        return v

class ServiceResponse(BaseModel):
    """Response model for service data"""
    service_id: str
    label: str
    service_type: str
    status_config: str
    metric_config: str
    enabled: bool
    created_at: str
    updated_at: str

class RelationCreateRequest(BaseModel):
    """Request model for creating a new service relation"""
    source_service_id: str = Field(..., description="Source service ID")
    target_service_id: str = Field(..., description="Target service ID") 
    relation_type: str = Field(default='dependency', description="Type of relation")
    enabled: bool = Field(default=True, description="Whether the relation is enabled")

    @field_validator('target_service_id')
    def validate_different_services(cls, v, info):
        if 'source_service_id' in info.data and v == info.data['source_service_id']:
            raise ValueError('Source and target services must be different')
        return v

class RelationUpdateRequest(BaseModel):
    """Request model for updating an existing relation"""
    relation_type: Optional[str] = None
    enabled: Optional[bool] = None

class RelationResponse(BaseModel):
    """Response model for relation data"""
    relation_id: str
    source_service_id: str
    target_service_id: str
    relation_type: str
    enabled: bool
    created_at: str

class BulkOperationResponse(BaseModel):
    """Response model for bulk operations"""
    success_count: int
    failed_count: int
    errors: List[Dict[str, str]] = Field(default_factory=list)


# Service Status Models for API responses
class ServiceStatus(BaseModel):
    service_id: str
    status_code: int  # 0=OK, 1=DEGRADED, 2=FAILED, 3=STARTING, 4=STOPPED, 5=UNKNOWN
    message: str
    time: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "service_id": "api-service-1",
                "status_code": 0,
                "message": "Service is healthy",
                "time": "2023-10-01T12:00:00Z",
            }
        }


class ServiceStatusSummary(BaseModel):
    service_id: str
    stime: datetime
    last_check: datetime
    last_status_code: int
    last_message: str
    check_count: int
    failed_count: int



# Service Status Update Request Models
class ServiceStatusUpdateRequest(BaseModel):
    """Request model for updating service status"""
    status_code: int = Field(..., ge=0, le=5, description="Status code: 0=OK, 1=DEGRADED, 2=FAILED, 3=STARTING, 4=STOPPED, 5=UNKNOWN")
    message: Optional[str] = Field(..., min_length=1, max_length=500, description="Status message")

    class Config:
        json_schema_extra = {
            "example": {
                "status_code": 0,
                "message": "Service is healthy",
            }
        }


# Service Status Mapping for batch responses
ServiceStatusMap = Dict[str, ServiceStatus]

class Notification(BaseModel):
    service_id: str


class ServiceFailureRecord(BaseModel):
    service_id: str
    time: str
    message: str