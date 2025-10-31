# lightbulb

## Features & Specifications

### Core Monitoring Capabilities

#### 1. Multi-Service Monitoring
- **Temporal Workflows**: Monitor workflow execution status, success/failure rates, and performance metrics
- **Python Processes**: Track process health, resource usage, and runtime status
- **REST API Endpoints**: Monitor endpoint availability, response times, and error rates
- **Database Services**: ClickHouse cluster health, query performance, and storage metrics
- **Kubernetes Pods**: Pod health checks, resource utilization, and log monitoring

#### 2. Real-time Status Dashboard
- **Visual Service Map**: Interactive flow diagram showing service dependencies and relationships
- **Status Indicators**: Color-coded status system (OK/DEGRADED/FAILED/STARTING/STOPPED/UNKNOWN)
- **Real-time Updates**: Live status updates with WebSocket connections
- **Historical Trends**: Time-series data visualization for service performance over time

#### 3. Intelligent Alerting & Notifications
- **Multi-channel Alerts**: Email, Slack, Teams, and webhook notifications
- **Smart Thresholds**: Configurable alerting rules based on service metrics
- **Escalation Policies**: Automatic escalation for critical failures
- **Alert Correlation**: Group related alerts to reduce noise

#### 4. Advanced Analytics & Insights
- **AI-Powered Log Analysis**: OpenAI integration for automatic log interpretation and root cause analysis
- **Performance Metrics**: Response time percentiles, throughput, and error rates
- **Dependency Mapping**: Visualize service dependencies and impact analysis
- **Capacity Planning**: Predictive analytics for resource utilization

#### 5. Security & Access Control
- **OIDC Authentication**: Single sign-on integration with corporate identity providers
- **Role-based Access Control**: Granular permissions for different user roles
- **Audit Logging**: Complete audit trail of all monitoring activities
- **Secure API Access**: JWT-based API authentication with rate limiting

### Technical Specifications

#### Frontend Architecture
- **Framework**: React 18+ with TypeScript
- **Build Tool**: Vite for fast development and optimized builds
- **Styling**: Tailwind CSS for modern, responsive design
- **State Management**: React Query for server state management
- **Visualization**: React Flow for interactive service diagrams
- **Charts**: Chart.js or D3.js for performance metrics visualization

#### Backend Architecture
- **Framework**: FastAPI with Python 3.12+
- **Database**: ClickHouse for time-series data and analytics
- **Authentication**: Vault OIDC integration
- **API Design**: RESTful APIs with OpenAPI documentation
- **Background Tasks**: FastAPI BackgroundTasks for monitoring jobs
- **Caching**: Redis for real-time data caching

#### Data Models

##### Service Status Schema
```yaml
status_codes:
  0: "OK"           # Healthy, all checks passed
  1: "DEGRADED"     # Running with warnings
  2: "FAILED"       # Critical failure
  3: "STARTING"     # Initializing
  4: "STOPPED"      # Intentionally stopped
  5: "UNKNOWN"      # Unable to determine status

service_types:
  - temporal_workflow
  - python_process
  - api_endpoint
  - database
  - kubernetes_pod
  - application
```

##### Monitoring Fields
- `service_id`: Unique identifier
- `timestamp`: Status check time (ISO 8601)
- `status_code`: Current status (0-5)
- `message`: Human-readable status description
- `metrics`: Performance data (response_time, cpu_usage, memory_usage)
- `details`: Additional context (error logs, stack traces)

#### Integration Specifications

##### Temporal Integration
- **Workflow Status**: Monitor workflow execution state
- **Activity Monitoring**: Track individual activity performance
- **Worker Health**: Monitor temporal worker processes
- **Schedule Validation**: Verify scheduled workflow execution

##### Kubernetes Integration
- **Pod Health Checks**: Readiness and liveness probes
- **Resource Metrics**: CPU, memory, and storage utilization
- **Log Aggregation**: Centralized logging from pod containers
- **Event Monitoring**: K8s events and pod lifecycle tracking

##### ClickHouse Integration
- **Cluster Health**: Monitor all cluster nodes
- **Query Performance**: Track slow queries and execution times
- **Storage Metrics**: Disk usage, table sizes, and compression ratios
- **Replication Status**: Monitor data replication across nodes

#### Performance Requirements
- **Response Time**: < 200ms for status API calls
- **Throughput**: Support 1000+ concurrent monitoring checks
- **Data Retention**: 90 days of detailed metrics, 1 year of aggregated data
- **Availability**: 99.9% uptime SLA

#### Deployment Specifications
- **Containerization**: Docker containers with multi-stage builds
- **Orchestration**: Kubernetes deployment with Helm charts
- **Scaling**: Horizontal pod autoscaling based on CPU/memory
- **Storage**: Persistent volumes for ClickHouse data
- **Networking**: Ingress controller with TLS termination

### Implementation Roadmap

#### Phase 1: Foundation & Core Infrastructure (Weeks 1-4)
**Objective**: Establish the basic monitoring framework and data pipeline

**Backend Tasks:**
- [x] **Database Schema Design** - Create ClickHouse tables for service status, metrics, and logs
- [ ] **Core Data Models** - Implement Pydantic models for services, status, and metrics
- [x] **Basic REST APIs** - CRUD operations for services and status endpoints
- [ ] **Admin API Endpoints** - Create/Update/Delete APIs for services and relations management
- [ ] **ClickHouse Integration** - Setup connection pool and query optimization
- [ ] **Configuration Management** - Extend services.yaml with environment-specific configs
- [ ] **Health Check Framework** - Basic ping/HTTP status check implementations

**Frontend Tasks:**
- [ ] **Project Setup** - Configure Tailwind CSS, React Query, and routing
- [ ] **Component Library** - Create reusable UI components (StatusBadge, ServiceCard, etc.)
- [ ] **Basic Dashboard** - Simple service list view with status indicators
- [ ] **Admin Dashboard** - Service and relation management interface with popup forms
- [ ] **Service Management** - Forms for adding/editing monitored services
- [ ] **API Integration** - Setup axios/fetch client with error handling

**DevOps Tasks:**
- [v] **CI/CD Pipeline** - Automated testing and build processes

#### Phase 2: Advanced Monitoring & Visualization (Weeks 5-8)
**Objective**: Implement service-specific monitoring and visual dashboard

**Backend Tasks:**
- [ ] **Temporal Integration** - Workflow status monitoring and metrics collection
- [ ] **Kubernetes SDK** - Pod health checks and resource monitoring
- [ ] **Python Process Monitoring** - PID tracking and resource usage collection
- [ ] **API Endpoint Monitoring** - Response time and availability checks
- [ ] **Background Job Scheduler** - Periodic monitoring tasks with FastAPI BackgroundTasks
- [ ] **WebSocket Support** - Real-time status updates for frontend

**Frontend Tasks:**
- [ ] **React Flow Integration** - Interactive service dependency diagram
- [ ] **Real-time Updates** - WebSocket connection for live status changes
- [ ] **Service Detail Views** - Detailed monitoring pages for each service type
- [ ] **Metrics Dashboard** - Charts for response times, resource usage, and trends
- [ ] **Responsive Design** - Mobile-friendly layouts and touch interactions

**Integration Tasks:**
- [ ] **Service Discovery** - Automatic detection of services in K8s clusters
- [ ] **Metric Collection** - Time-series data aggregation and storage
- [ ] **Status Aggregation** - Rollup logic for service health scoring

#### Phase 3: Intelligence & Analytics (Weeks 9-12)
**Objective**: Add AI-powered insights and advanced analytics

**Backend Tasks:**
- [ ] **OpenAI Integration** - Log analysis and error interpretation
- [ ] **Alert Engine** - Rule-based alerting with escalation policies
- [ ] **Historical Analytics** - Performance trend analysis and capacity planning
- [ ] **Anomaly Detection** - Machine learning for unusual pattern identification
- [ ] **Notification Service** - Multi-channel alert delivery (email, Slack, webhooks)

**Frontend Tasks:**
- [ ] **AI Insights Panel** - Display OpenAI analysis of service issues
- [ ] **Alert Management** - Configure and manage alerting rules
- [ ] **Analytics Dashboard** - Historical trends and performance analytics
- [ ] **Anomaly Visualization** - Charts highlighting detected anomalies
- [ ] **Search & Filtering** - Advanced filtering for services and logs

**AI/ML Tasks:**
- [ ] **Log Processing Pipeline** - Structured log parsing and analysis
- [ ] **Pattern Recognition** - Identify common failure patterns
- [ ] **Predictive Modeling** - Forecast potential service issues

#### Phase 4: Security & Enterprise Features (Weeks 13-16)
**Objective**: Implement enterprise-grade security and access controls

**Backend Tasks:**
- [ ] **Vault Integration** - Secure credential management for service checks
- [ ] **OIDC Authentication** - Corporate SSO integration
- [ ] **Role-Based Access Control** - Granular permissions for different user types
- [ ] **Audit Logging** - Complete activity tracking and compliance reporting
- [ ] **API Rate Limiting** - Prevent abuse and ensure system stability
- [ ] **Data Encryption** - Encrypt sensitive data at rest and in transit

**Frontend Tasks:**
- [ ] **Authentication Flow** - Login/logout with OIDC provider
- [ ] **User Management** - Role assignment and permission management
- [ ] **Audit Dashboard** - View system activity and user actions
- [ ] **Security Settings** - Configure security policies and access controls
- [ ] **Session Management** - Secure token handling and refresh

**Security Tasks:**
- [ ] **Penetration Testing** - Security vulnerability assessment
- [ ] **Compliance Review** - Ensure SOC2/ISO27001 compliance
- [ ] **Backup Strategy** - Data backup and disaster recovery procedures

#### Phase 5: Production Readiness & Optimization (Weeks 17-20)
**Objective**: Prepare for production deployment and scale optimization

**Backend Tasks:**
- [ ] **Performance Optimization** - Query optimization and caching strategies
- [ ] **Load Testing** - Verify system can handle 1000+ concurrent checks
- [ ] **Error Handling** - Comprehensive error recovery and retry logic
- [ ] **Monitoring & Observability** - Self-monitoring with Prometheus/Grafana
- [ ] **Database Optimization** - ClickHouse cluster tuning and partitioning

**Frontend Tasks:**
- [ ] **Performance Optimization** - Code splitting and lazy loading
- [ ] **Progressive Web App** - Offline capabilities and push notifications
- [ ] **User Experience** - Usability testing and interface refinements
- [ ] **Accessibility** - WCAG compliance and keyboard navigation
- [ ] **Documentation** - User guides and help system

**DevOps Tasks:**
- [ ] **Kubernetes Deployment** - Production-ready Helm charts
- [ ] **Auto-scaling** - HPA configuration for variable load
- [ ] **Monitoring Setup** - Application monitoring with alerting
- [ ] **Backup Automation** - Automated backup and restore procedures
- [ ] **Disaster Recovery** - Multi-region deployment and failover

#### Phase 6: Advanced Features & Maintenance (Weeks 21+)
**Objective**: Continuous improvement and advanced capabilities

**Advanced Features:**
- [ ] **Custom Dashboards** - User-configurable monitoring views
- [ ] **Advanced Reporting** - Scheduled reports and SLA tracking
- [ ] **API Integrations** - Third-party tool integrations (PagerDuty, ServiceNow)
- [ ] **Mobile Application** - Native mobile app for on-the-go monitoring
- [ ] **Multi-tenant Support** - Support for multiple organizations
- [ ] **Advanced Analytics** - Machine learning for capacity planning

**Maintenance Tasks:**
- [ ] **Regular Updates** - Security patches and dependency updates
- [ ] **Performance Monitoring** - Continuous performance optimization
- [ ] **User Feedback** - Regular user surveys and feature requests
- [ ] **Documentation Updates** - Keep documentation current with features

### Admin Dashboard Feature Planning (Phase 1)

#### Overview
The Admin Dashboard provides a comprehensive interface for managing services and service relationships through intuitive popup dialog forms, enabling administrators to configure the monitoring system without direct database access.

#### Backend API Requirements

##### Service Management APIs
```python
# Service CRUD Operations
POST   /api/admin/services              # Create new service
GET    /api/admin/services              # List all services (with pagination)
GET    /api/admin/services/{service_id} # Get service details
PUT    /api/admin/services/{service_id} # Update service
DELETE /api/admin/services/{service_id} # Delete service
```

##### Service Relations Management APIs
```python
# Service Relations CRUD Operations  
POST   /api/admin/relations              # Create new relation
GET    /api/admin/relations              # List all relations
GET    /api/admin/relations/{relation_id} # Get relation details
PUT    /api/admin/relations/{relation_id} # Update relation
DELETE /api/admin/relations/{relation_id} # Delete relation
```

##### Validation & Business Logic
- **Service ID Uniqueness**: Ensure service_id is unique across the system
- **Circular Dependency Detection**: Prevent creating circular dependencies in service relations
- **Cascade Operations**: Handle dependent relations when deleting services
- **Configuration Validation**: Validate JSON status_config and metric_config

#### Frontend Component Architecture

##### 1. Admin Dashboard Layout
```
AdminDashboard/
├── ServiceManagement/
│   ├── ServiceList.tsx          # Main services table with actions
│   ├── ServiceForm.tsx          # Add/Edit service popup form
│   ├── ServiceCard.tsx          # Service preview card
│   └── ServiceFilters.tsx       # Search and filter controls
├── RelationManagement/
│   ├── RelationList.tsx         # Relations table view
│   ├── RelationForm.tsx         # Add/Edit relation popup form
│   ├── RelationGraph.tsx        # Visual dependency graph
│   └── RelationValidation.tsx   # Dependency validation component
└── Common/
    ├── ConfirmDialog.tsx        # Delete confirmation modal
    ├── Toast.tsx                # Success/Error notifications
    └── LoadingSpinner.tsx       # Loading states
```

##### 2. Service Management Features
- **Service List View**: Paginated table with search, filter, and sort capabilities
- **Add Service Dialog**: Multi-step form for service creation
  - Basic Info: service_id, label, service_type
  - Configuration: status_config, metric_config (JSON editors)
  - Preview: Service card preview before creation
- **Edit Service Dialog**: Pre-populated form for service updates
- **Delete Confirmation**: Warning dialog showing dependent relations
- **Bulk Operations**: Select multiple services for bulk enable/disable

##### 3. Service Relations Features
- **Relations List View**: Table showing source → target relationships
- **Add Relation Dialog**: 
  - Source/Target service dropdowns (with search)
  - Relation type selection
  - Dependency validation warnings
- **Visual Dependency Graph**: Interactive graph showing service connections
- **Relation Validation**: Real-time circular dependency detection
- **Relation Templates**: Pre-defined relation types (dependency, communication, data-flow)

##### 4. Form Components & Validation
```typescript
// Service Form Schema
interface ServiceFormData {
  service_id: string;           // Required, unique, alphanumeric + hyphens
  label: string;                // Required, display name
  service_type: ServiceType;    // Required, dropdown selection
  status_config: string;        // JSON string, validated
  metric_config?: string;       // Optional JSON string
  enabled: boolean;             // Toggle switch
}

// Relation Form Schema  
interface RelationFormData {
  source_service_id: string;    // Required, existing service
  target_service_id: string;    // Required, existing service, different from source
  relation_type: string;        // Required, predefined types
  enabled: boolean;             // Toggle switch
}
```

##### 5. User Experience Features
- **Auto-save Drafts**: Save form progress automatically
- **Form Validation**: Real-time validation with helpful error messages
- **Keyboard Shortcuts**: Quick actions (Ctrl+N for new service, etc.)
- **Responsive Design**: Mobile-friendly dialogs and tables
- **Undo/Redo**: Recent changes tracking with undo capability
- **Import/Export**: Bulk import services from CSV/JSON files

#### Data Flow & State Management

##### 1. React Query Integration
```typescript
// Service Management Hooks
const useServices = () => useQuery(['services'], fetchServices);
const useCreateService = () => useMutation(createService);
const useUpdateService = () => useMutation(updateService);
const useDeleteService = () => useMutation(deleteService);

// Relation Management Hooks
const useRelations = () => useQuery(['relations'], fetchRelations);
const useCreateRelation = () => useMutation(createRelation);
const useValidateRelation = () => useMutation(validateRelation);
```

##### 2. Form State Management
- **React Hook Form**: Form validation and state management
- **Zod Schema**: Runtime validation for form data
- **Optimistic Updates**: Immediate UI updates with rollback on failure

##### 3. Global State
- **Service Registry**: Cached service list for dropdowns and validation
- **Current User Permissions**: Role-based feature access control
- **UI State**: Dialog open/close states, selected items

#### Security & Permissions

##### 1. Role-Based Access Control
- **Admin Role**: Full CRUD access to all services and relations
- **Editor Role**: Create/Update services, limited relation management
- **Viewer Role**: Read-only access, no admin dashboard access

##### 2. Operation Auditing
- **Change Tracking**: Log all create/update/delete operations
- **User Attribution**: Track which user made each change
- **Rollback Capability**: Ability to revert changes if needed

#### Technical Implementation Details

##### 1. Database Operations
```sql
-- Service CRUD with validation
INSERT INTO monitor.services (service_id, label, service_type, status_config, metric_config)
VALUES (?, ?, ?, ?, ?);

-- Relation creation with circular dependency check
WITH RECURSIVE dependency_check AS (
  SELECT source_service_id, target_service_id, 1 as depth
  FROM monitor.service_relations 
  WHERE source_service_id = ?
  UNION ALL
  SELECT sr.source_service_id, sr.target_service_id, dc.depth + 1
  FROM monitor.service_relations sr
  JOIN dependency_check dc ON sr.source_service_id = dc.target_service_id
  WHERE dc.depth < 10
)
SELECT * FROM dependency_check WHERE target_service_id = ?;
```

##### 2. API Response Formats
```typescript
// Service API Response
interface ServiceResponse {
  service_id: string;
  label: string;
  service_type: string;
  status_config: object;
  metric_config?: object;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  relations: {
    incoming: RelationSummary[];
    outgoing: RelationSummary[];
  };
}

// Bulk Operation Response
interface BulkOperationResponse {
  success_count: number;
  failed_count: number;
  errors: Array<{
    item_id: string;
    error_message: string;
  }>;
}
```

#### Testing Strategy

##### 1. Backend Testing
- **Unit Tests**: Service/Relation CRUD operations
- **Integration Tests**: Database operations and validation logic
- **API Tests**: Endpoint validation and error handling

##### 2. Frontend Testing
- **Component Tests**: Individual form components and dialogs
- **Integration Tests**: Complete workflow testing (create → edit → delete)
- **E2E Tests**: Full admin dashboard user journeys

#### Success Metrics
- **Performance**: < 200ms API response time, 99.9% uptime
- **Scale**: Support 1000+ concurrent monitoring checks
- **User Adoption**: 90% user satisfaction score
- **Reliability**: < 1% false positive alert rate
- **Security**: Zero security incidents in production

### Service Status Rendering Strategies

#### Overview
The frontend needs to efficiently display real-time status updates for potentially hundreds of services. This section analyzes different approaches for fetching and rendering service status data from the backend.

---

#### Strategy 2: Individual Service Polling
**Description**: Fetch status for each service individually on-demand or staggered intervals.

**Implementation:**
```typescript
// Frontend - Individual service polling
const fetchServiceStatus = async (serviceId: string): Promise<ServiceStatus> => {
  const response = await fetch(`/api/status/${serviceId}`);
  return response.json();
};

// Staggered polling for different services
useEffect(() => {
  serviceNodes.forEach((service, index) => {
    setTimeout(() => {
      const interval = setInterval(async () => {
        const status = await fetchServiceStatus(service.service_id);
        setServiceStatus(service.service_id, status);
      }, 3000);
      
      serviceIntervals.current[service.service_id] = interval;
    }, index * 200); // Stagger initial requests
  });
  
  return () => {
    Object.values(serviceIntervals.current).forEach(clearInterval);
  };
}, [serviceNodes]);
```

**Backend Endpoint:**
```python
@app.get('/api/status/{service_id}', response_model=ServiceStatus)
def get_service_status(service_id: str):
    """Get current status for a specific service"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        query = """
        SELECT 
            status_code,
            message,
            time,
            response_time_ms,
            cpu_usage,
            memory_usage
        FROM monitor.service_status 
        WHERE service_id = '{service_id}'
        ORDER BY time DESC
        LIMIT 1
        """.format(service_id=service_id)
        
        result = client.execute(query)
        if not result:
            raise HTTPException(status_code=404, detail="Service not found")
            
        row = result[0]
        return ServiceStatus(
            service_id=service_id,
            status_code=row[0],
            message=row[1],
            last_check=row[2],
            response_time_ms=row[3],
            cpu_usage=row[4],
            memory_usage=row[5]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Pros:**
- Fine-grained control over polling frequency per service
- Spreads network load over time
- Can prioritize critical services with higher frequency
- Better error isolation (one service failure doesn't affect others)

**Cons:**
- More complex implementation
- Higher total number of requests
- Potential for request storms
- More difficult to optimize and cache

---

#### Strategy 3: Server-Sent Events (SSE)
**Description**: Establish persistent connections where the server pushes status updates as they occur.

**Implementation:**
```typescript
// Frontend - SSE implementation
useEffect(() => {
  const eventSource = new EventSource('/api/status/stream');
  
  eventSource.onmessage = (event) => {
    const statusUpdate: ServiceStatusUpdate = JSON.parse(event.data);
    setServiceStatus(statusUpdate.service_id, statusUpdate.status);
  };
  
  eventSource.onerror = (error) => {
    console.error('SSE connection error:', error);
    // Implement reconnection logic
  };
  
  return () => {
    eventSource.close();
  };
}, []);
```

**Backend Implementation:**
```python
from fastapi.responses import StreamingResponse
import asyncio
import json

@app.get('/api/status/stream')
async def stream_service_status():
    """Stream real-time service status updates via SSE"""
    
    async def event_generator():
        last_check = datetime.now()
        
        while True:
            try:
                client = ResourceConnector().connect_clickhouse_static('monitor')
                
                # Query for status changes since last check
                query = """
                SELECT 
                    service_id,
                    status_code,
                    message,
                    time,
                    response_time_ms
                FROM monitor.service_status 
                WHERE time > '{last_check}'
                ORDER BY service_id, time DESC
                """.format(last_check=last_check.strftime('%Y-%m-%d %H:%M:%S'))
                
                result = client.execute(query)
                
                # Group by service_id and get latest status for each
                latest_statuses = {}
                for row in result:
                    service_id = row[0]
                    if service_id not in latest_statuses:
                        latest_statuses[service_id] = {
                            'service_id': service_id,
                            'status_code': row[1],
                            'message': row[2],
                            'last_check': row[3].isoformat(),
                            'response_time_ms': row[4]
                        }
                
                # Send updates for changed services
                for status in latest_statuses.values():
                    yield f"data: {json.dumps(status)}\n\n"
                
                last_check = datetime.now()
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                error_data = {'error': str(e)}
                yield f"data: {json.dumps(error_data)}\n\n"
                await asyncio.sleep(5)  # Longer wait on error
    
    return StreamingResponse(
        event_generator(),
        media_type='text/plain',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'text/event-stream'
        }
    )
```

**Pros:**
- Near real-time updates
- Efficient network usage (only sends changes)
- Automatic browser reconnection handling
- Works well with existing HTTP infrastructure

**Cons:**
- Persistent connections consume server resources
- Complexity in handling connection failures
- Browser connection limits
- More complex deployment considerations

---

#### Strategy 4: WebSocket Implementation
**Description**: Full-duplex communication for real-time bidirectional updates.

**Implementation:**
```typescript
// Frontend - WebSocket implementation
useEffect(() => {
  const ws = new WebSocket('ws://localhost:8000/api/status/websocket');
  
  ws.onopen = () => {
    // Subscribe to specific services
    ws.send(JSON.stringify({
      type: 'subscribe',
      services: serviceNodes.map(s => s.service_id)
    }));
  };
  
  ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    if (update.type === 'status_update') {
      setServiceStatus(update.service_id, update.status);
    }
  };
  
  ws.onclose = () => {
    // Implement reconnection logic
    setTimeout(() => {
      // Reconnect
    }, 5000);
  };
  
  return () => ws.close();
}, [serviceNodes]);
```

**Backend Implementation:**
```python
from fastapi import WebSocket, WebSocketDisconnect
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast_status_update(self, service_id: str, status: dict):
        message = {
            'type': 'status_update',
            'service_id': service_id,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except:
                # Handle disconnected clients
                pass

manager = ConnectionManager()

@app.websocket('/api/status/websocket')
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        while True:
            # Listen for client messages (subscription requests, etc.)
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message['type'] == 'subscribe':
                # Handle service subscription logic
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

**Pros:**
- True real-time bidirectional communication
- Efficient for high-frequency updates
- Supports selective subscription
- Lower latency than HTTP polling

**Cons:**
- More complex implementation
- Additional infrastructure considerations
- Connection state management complexity
- Firewall and proxy challenges

---

#### Recommended Hybrid Approach

**For Production Implementation:**

1. **Primary Strategy**: Server-Sent Events (SSE) for real-time updates
   - Provides near real-time performance
   - Works well with existing HTTP infrastructure
   - Easier to implement and debug than WebSockets

2. **Fallback Strategy**: Batch polling every 30 seconds
   - Ensures data consistency if SSE connection fails
   - Handles browser compatibility issues
   - Provides backup when real-time updates aren't critical

3. **On-Demand Strategy**: Individual service polling for user-initiated actions
   - Immediate feedback for manual refresh actions
   - Detailed status queries when users click on specific services

**Implementation Architecture:**
```typescript
// Hybrid status management
class StatusManager {
  private sseConnection: EventSource | null = null;
  private pollInterval: NodeJS.Timeout | null = null;
  private readonly FALLBACK_POLL_INTERVAL = 30000;
  
  async initializeStatusUpdates() {
    // Try SSE first
    this.establishSSEConnection();
    
    // Start fallback polling
    this.startFallbackPolling();
  }
  
  private establishSSEConnection() {
    this.sseConnection = new EventSource('/api/status/stream');
    
    this.sseConnection.onmessage = (event) => {
      this.handleStatusUpdate(JSON.parse(event.data));
      this.resetFallbackPolling(); // Reset polling timer on successful SSE
    };
    
    this.sseConnection.onerror = () => {
      this.accelerateFallbackPolling(); // Poll more frequently when SSE fails
    };
  }
  
  private startFallbackPolling() {
    this.pollInterval = setInterval(async () => {
      const statuses = await this.fetchAllServiceStatus();
      statuses.forEach(status => this.handleStatusUpdate(status));
    }, this.FALLBACK_POLL_INTERVAL);
  }
}
```

#### Performance Considerations

1. **Database Optimization:**
   - Use materialized views for fast status aggregation
   - Implement proper indexing on service_id and timestamp
   - Consider read replicas for high-frequency queries

2. **Caching Strategy:**
   - Redis cache for frequently accessed status data
   - CDN caching for static service metadata
   - Browser caching with appropriate cache headers

3. **Rate Limiting:**
   - Implement rate limiting to prevent abuse
   - Throttle individual service queries
   - Graceful degradation under high load

4. **Connection Management:**
   - Limit concurrent SSE/WebSocket connections per user
   - Implement connection pooling for database queries
   - Monitor and alert on connection counts

This hybrid approach provides resilience, performance, and scalability while maintaining real-time capabilities where possible.

---

### Server-Sent Events (SSE) Deep Dive

#### What are Server-Sent Events?

Server-Sent Events (SSE) is a web standard that allows a server to push data to a web page over a single HTTP connection. Unlike WebSockets, SSE is unidirectional - data flows only from server to client. This makes SSE simpler to implement and more firewall-friendly while still providing real-time updates.

#### Key Characteristics

- **HTTP-based**: Uses standard HTTP connections
- **Unidirectional**: Server pushes data to client only
- **Automatic Reconnection**: Browsers automatically reconnect on connection loss
- **Event-driven**: Supports custom event types
- **Lightweight**: Lower overhead than WebSockets for server-to-client updates

#### When to Use SSE

**Best for:**
- Real-time status updates
- Live notifications
- Progress tracking
- Dashboard updates
- Chat applications (receive-only)

**Not ideal for:**
- Bidirectional communication needs
- High-frequency updates (>10 per second)
- Binary data transmission
- Complex client-to-server interactions

#### Basic Example Implementation

##### Python Backend (FastAPI)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json
import time
from datetime import datetime

app = FastAPI()

# Simulated data source
service_status = {
    "database": {"status": "healthy", "response_time": 50},
    "api": {"status": "healthy", "response_time": 120},
    "cache": {"status": "degraded", "response_time": 200}
}

@app.get("/events")
async def stream_events():
    """SSE endpoint that streams service status updates"""
    
    async def event_generator():
        while True:
            # Simulate status changes
            current_time = datetime.now().isoformat()
            
            for service_id, status in service_status.items():
                # Simulate random status changes
                import random
                if random.random() < 0.1:  # 10% chance of status change
                    statuses = ["healthy", "degraded", "failed"]
                    status["status"] = random.choice(statuses)
                    status["response_time"] = random.randint(50, 500)
                
                # Send update as SSE
                event_data = {
                    "service_id": service_id,
                    "status": status["status"],
                    "response_time": status["response_time"],
                    "timestamp": current_time
                }
                
                # SSE format: "data: {json}\n\n"
                yield f"data: {json.dumps(event_data)}\n\n"
            
            # Wait before next update
            await asyncio.sleep(2)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

@app.get("/status")
async def get_current_status():
    """REST endpoint to get current status"""
    return service_status

# CORS middleware for development
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

##### React TypeScript Frontend

```typescript
import React, { useState, useEffect } from 'react';

interface ServiceStatus {
  service_id: string;
  status: 'healthy' | 'degraded' | 'failed';
  response_time: number;
  timestamp: string;
}

interface StatusMap {
  [key: string]: Omit<ServiceStatus, 'service_id'>;
}

const SSEDashboard: React.FC = () => {
  const [services, setServices] = useState<StatusMap>({});
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [lastUpdate, setLastUpdate] = useState<string>('');

  useEffect(() => {
    // Create SSE connection
    const eventSource = new EventSource('http://localhost:8000/events');
    
    eventSource.onopen = () => {
      console.log('SSE connection opened');
      setConnectionStatus('connected');
    };
    
    eventSource.onmessage = (event) => {
      try {
        const statusUpdate: ServiceStatus = JSON.parse(event.data);
        
        // Update service status
        setServices(prev => ({
          ...prev,
          [statusUpdate.service_id]: {
            status: statusUpdate.status,
            response_time: statusUpdate.response_time,
            timestamp: statusUpdate.timestamp
          }
        }));
        
        setLastUpdate(new Date().toLocaleTimeString());
      } catch (error) {
        console.error('Error parsing SSE data:', error);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      setConnectionStatus('disconnected');
    };
    
    // Cleanup on unmount
    return () => {
      eventSource.close();
    };
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600 bg-green-100';
      case 'degraded': return 'text-yellow-600 bg-yellow-100';
      case 'failed': return 'text-red-600 bg-red-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  const getConnectionColor = (status: string) => {
    switch (status) {
      case 'connected': return 'text-green-600';
      case 'connecting': return 'text-yellow-600';
      case 'disconnected': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Real-time Service Status Dashboard
        </h1>
        
        <div className="flex items-center space-x-4 text-sm">
          <div className="flex items-center space-x-2">
            <div className={`w-3 h-3 rounded-full ${
              connectionStatus === 'connected' ? 'bg-green-500' : 
              connectionStatus === 'connecting' ? 'bg-yellow-500' : 'bg-red-500'
            }`} />
            <span className={getConnectionColor(connectionStatus)}>
              SSE: {connectionStatus}
            </span>
          </div>
          
          {lastUpdate && (
            <span className="text-gray-600">
              Last update: {lastUpdate}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(services).map(([serviceId, status]) => (
          <div key={serviceId} className="bg-white rounded-lg shadow-md p-4 border">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold capitalize">{serviceId}</h3>
              <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(status.status)}`}>
                {status.status}
              </span>
            </div>
            
            <div className="space-y-2 text-sm text-gray-600">
              <div className="flex justify-between">
                <span>Response Time:</span>
                <span className="font-mono">{status.response_time}ms</span>
              </div>
              
              <div className="flex justify-between">
                <span>Last Check:</span>
                <span className="font-mono">
                  {new Date(status.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {Object.keys(services).length === 0 && (
        <div className="text-center py-12">
          <div className="text-gray-500">
            {connectionStatus === 'connected' 
              ? 'Waiting for service status updates...' 
              : 'Connecting to status stream...'}
          </div>
        </div>
      )}
      
      <div className="mt-8 bg-blue-50 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 mb-2">How SSE Works:</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Browser opens persistent HTTP connection to /events endpoint</li>
          <li>• Server continuously streams data in "data: content\n\n" format</li>
          <li>• Browser automatically parses events and triggers onmessage</li>
          <li>• Connection auto-reconnects if interrupted</li>
          <li>• No polling needed - truly real-time updates</li>
        </ul>
      </div>
    </div>
  );
};

export default SSEDashboard;
```

#### Running the Example

1. **Start the Python backend:**
```bash
pip install fastapi uvicorn
uvicorn main:app --reload --port 8000
```

2. **Access the SSE endpoint directly:**
```bash
curl http://localhost:8000/events
```

3. **Integrate with React frontend** using the component above

#### SSE Message Format

SSE uses a simple text-based format:

```
data: {"service_id": "database", "status": "healthy"}

data: {"service_id": "api", "status": "degraded"}

event: custom-event
data: {"message": "Custom event data"}

```

Key points:
- Each message ends with double newline (`\n\n`)
- `data:` prefix is required
- Optional `event:` for custom event types
- `id:` for message IDs (enables automatic reconnection from last received)

#### Error Handling and Reconnection

```typescript
useEffect(() => {
  let eventSource: EventSource;
  let reconnectTimer: NodeJS.Timeout;
  
  const connect = () => {
    eventSource = new EventSource('/api/events');
    
    eventSource.onopen = () => {
      setConnectionStatus('connected');
      // Clear any reconnection timer
      if (reconnectTimer) clearTimeout(reconnectTimer);
    };
    
    eventSource.onerror = () => {
      setConnectionStatus('disconnected');
      eventSource.close();
      
      // Attempt reconnection after delay
      reconnectTimer = setTimeout(() => {
        console.log('Attempting to reconnect...');
        connect();
      }, 5000);
    };
  };
  
  connect();
  
  return () => {
    if (eventSource) eventSource.close();
    if (reconnectTimer) clearTimeout(reconnectTimer);
  };
}, []);
```

This example demonstrates the core concepts of SSE: persistent connection, real-time data streaming, and automatic reconnection handling. The server continuously pushes updates, and the client receives them instantly without polling.

## Add your files

## Integrate with your tools

- [ ] [Set up project integrations](https://gitlab.nova.hksmartone.com/smartone/pm_service/lightbulb/-/settings/integrations)

## Collaborate with your team

- [ ] [Invite team members and collaborators](https://docs.gitlab.com/ee/user/project/members/)
- [ ] [Create a new merge request](https://docs.gitlab.com/ee/user/project/merge_requests/creating_merge_requests.html)
- [ ] [Automatically close issues from merge requests](https://docs.gitlab.com/ee/user/project/issues/managing_issues.html#closing-issues-automatically)
- [ ] [Enable merge request approvals](https://docs.gitlab.com/ee/user/project/merge_requests/approvals/)
- [ ] [Set auto-merge](https://docs.gitlab.com/ee/user/project/merge_requests/merge_when_pipeline_succeeds.html)

## Test and Deploy

Use the built-in continuous integration in GitLab.

- [ ] [Get started with GitLab CI/CD](https://docs.gitlab.com/ee/ci/quick_start/)
- [ ] [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/ee/user/application_security/sast/)
- [ ] [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/ee/topics/autodevops/requirements.html)
- [ ] [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/ee/user/clusters/agent/)
- [ ] [Set up protected environments](https://docs.gitlab.com/ee/ci/environments/protected_environments.html)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
