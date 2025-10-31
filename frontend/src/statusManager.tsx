import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { API_ROOT } from './constants';

// Status code definitions matching backend
export const STATUS_CODES = {
  0: 'OK',
  1: 'DEGRADED', 
  2: 'FAILED',
  3: 'STARTING',
  4: 'STOPPED',
  5: 'UNKNOWN'
} as const;

export interface ServiceStatus {
  service_id: string;
  status_code: number;
  message: string;
  last_check: string;
  response_time_ms?: number;
  cpu_usage?: number;
  memory_usage?: number;
  details?: string;
}

export type ServiceStatusMap = Record<string, ServiceStatus>;

interface StatusUpdateEvent {
  service_id: string;
  status_code: number;
  message: string;
  last_check: string;
  response_time_ms?: number;
  cpu_usage?: number;
  memory_usage?: number;
  details?: string;
}

interface StatusManagerOptions {
  serviceIds: string[];
  enableSSE?: boolean;
  enableWebSocket?: boolean;
  fallbackPollInterval?: number;
  onStatusUpdate?: (serviceId: string, status: ServiceStatus) => void;
  onError?: (error: Error) => void;
}

export class StatusManager {
  private serviceIds: string[];
  private statusMap: ServiceStatusMap = {};
  private sseConnection: EventSource | null = null;
  private wsConnection: WebSocket | null = null;
  private pollInterval: NodeJS.Timeout | null = null;
  private statusUpdateCallbacks: Set<(statusMap: ServiceStatusMap) => void> = new Set();
  private errorCallbacks: Set<(error: Error) => void> = new Set();
  
  private readonly FALLBACK_POLL_INTERVAL: number;
  private readonly SSE_ENABLED: boolean;
  private readonly WS_ENABLED: boolean;
  
  constructor(options: StatusManagerOptions) {
    this.serviceIds = options.serviceIds;
    this.FALLBACK_POLL_INTERVAL = options.fallbackPollInterval || 30000;
    this.SSE_ENABLED = options.enableSSE ?? true;
    this.WS_ENABLED = options.enableWebSocket ?? false;
  }

  // Subscribe to status updates
  onStatusUpdate(callback: (statusMap: ServiceStatusMap) => void) {
    this.statusUpdateCallbacks.add(callback);
    return () => this.statusUpdateCallbacks.delete(callback);
  }

  // Subscribe to errors
  onError(callback: (error: Error) => void) {
    this.errorCallbacks.add(callback);
    return () => this.errorCallbacks.delete(callback);
  }

  // Initialize status monitoring
  async initialize() {
    // Load initial status
    await this.fetchAllStatus();
    
    // Try real-time connections
    if (this.WS_ENABLED) {
      this.establishWebSocketConnection();
    } else if (this.SSE_ENABLED) {
      this.establishSSEConnection();
    }
    
    // Start fallback polling
    this.startFallbackPolling();
  }

  // Cleanup connections
  cleanup() {
    if (this.sseConnection) {
      this.sseConnection.close();
      this.sseConnection = null;
    }
    
    if (this.wsConnection) {
      this.wsConnection.close();
      this.wsConnection = null;
    }
    
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    
    this.statusUpdateCallbacks.clear();
    this.errorCallbacks.clear();
  }

  // Get current status map
  getStatusMap(): ServiceStatusMap {
    return { ...this.statusMap };
  }

  // Get status for specific service
  getServiceStatus(serviceId: string): ServiceStatus | null {
    return this.statusMap[serviceId] || null;
  }

  // Fetch individual service status
  async fetchServiceStatus(serviceId: string): Promise<ServiceStatus | null> {
    try {
      const response = await axios.get(`${API_ROOT}/status/${serviceId}`);
      const status = response.data as ServiceStatus;
      this.updateServiceStatus(serviceId, status);
      return status;
    } catch (error) {
      this.notifyError(new Error(`Failed to fetch status for ${serviceId}: ${error}`));
      return null;
    }
  }

  // Fetch all service statuses in batch
  async fetchAllStatus(): Promise<void> {
    try {
      const response = await axios.get(`${API_ROOT}/api/status/batch`);
      const statusMap = response.data as ServiceStatusMap;
      
      // Update only services we're tracking
      for (const serviceId of this.serviceIds) {
        if (statusMap[serviceId]) {
          this.updateServiceStatus(serviceId, statusMap[serviceId]);
        }
      }
    } catch (error) {
      this.notifyError(new Error(`Failed to fetch batch status: ${error}`));
    }
  }

  // Establish Server-Sent Events connection
  private establishSSEConnection(): void {
    try {
      this.sseConnection = new EventSource(`${API_ROOT}/api/status/stream`);
      
      this.sseConnection.onmessage = (event) => {
        try {
          const statusUpdate = JSON.parse(event.data) as StatusUpdateEvent;
          
          // Only process updates for services we're tracking
          if (this.serviceIds.includes(statusUpdate.service_id)) {
            this.updateServiceStatus(statusUpdate.service_id, statusUpdate);
            this.resetFallbackPolling(); // Reset polling timer on successful SSE
          }
        } catch (error) {
          this.notifyError(new Error(`SSE message parsing error: ${error}`));
        }
      };
      
      this.sseConnection.onerror = (error) => {
        console.error('SSE connection error:', error);
        this.accelerateFallbackPolling(); // Poll more frequently when SSE fails
      };
      
      this.sseConnection.onopen = () => {
        console.log('SSE connection established');
      };
      
    } catch (error) {
      this.notifyError(new Error(`Failed to establish SSE connection: ${error}`));
    }
  }

  // Establish WebSocket connection
  private establishWebSocketConnection(): void {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}${API_ROOT}/api/status/websocket`;
      
      this.wsConnection = new WebSocket(wsUrl);
      
      this.wsConnection.onopen = () => {
        console.log('WebSocket connection established');
        
        // Subscribe to our services
        if (this.wsConnection) {
          this.wsConnection.send(JSON.stringify({
            type: 'subscribe',
            services: this.serviceIds
          }));
        }
      };
      
      this.wsConnection.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          if (message.type === 'status_update') {
            const serviceId = message.service_id;
            if (this.serviceIds.includes(serviceId)) {
              this.updateServiceStatus(serviceId, message.status);
              this.resetFallbackPolling();
            }
          } else if (message.type === 'subscription_confirmed') {
            console.log('WebSocket subscription confirmed for services:', message.services);
          }
        } catch (error) {
          this.notifyError(new Error(`WebSocket message parsing error: ${error}`));
        }
      };
      
      this.wsConnection.onclose = () => {
        console.log('WebSocket connection closed');
        this.accelerateFallbackPolling();
        
        // Attempt to reconnect after delay
        setTimeout(() => {
          if (!this.wsConnection || this.wsConnection.readyState === WebSocket.CLOSED) {
            this.establishWebSocketConnection();
          }
        }, 5000);
      };
      
      this.wsConnection.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.notifyError(new Error('WebSocket connection error'));
      };
      
    } catch (error) {
      this.notifyError(new Error(`Failed to establish WebSocket connection: ${error}`));
    }
  }

  // Start fallback polling
  private startFallbackPolling(): void {
    this.pollInterval = setInterval(() => {
      this.fetchAllStatus();
    }, this.FALLBACK_POLL_INTERVAL);
  }

  // Reset polling interval to normal
  private resetFallbackPolling(): void {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.startFallbackPolling();
    }
  }

  // Accelerate polling when real-time connection fails
  private accelerateFallbackPolling(): void {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      
      // Poll every 5 seconds when real-time is unavailable
      this.pollInterval = setInterval(() => {
        this.fetchAllStatus();
      }, 5000);
    }
  }

  // Update service status and notify subscribers
  private updateServiceStatus(serviceId: string, status: ServiceStatus): void {
    this.statusMap[serviceId] = status;
    this.notifyStatusUpdate();
  }

  // Notify status update callbacks
  private notifyStatusUpdate(): void {
    const statusMap = this.getStatusMap();
    this.statusUpdateCallbacks.forEach(callback => {
      try {
        callback(statusMap);
      } catch (error) {
        console.error('Error in status update callback:', error);
      }
    });
  }

  // Notify error callbacks
  private notifyError(error: Error): void {
    this.errorCallbacks.forEach(callback => {
      try {
        callback(error);
      } catch (callbackError) {
        console.error('Error in error callback:', callbackError);
      }
    });
  }
}

// React hook for service status management
export function useServiceStatus(serviceIds: string[], options: Partial<StatusManagerOptions> = {}) {
  const [statusMap, setStatusMap] = useState<ServiceStatusMap>({});
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const managerRef = useRef<StatusManager | null>(null);

  // Initialize status manager
  useEffect(() => {
    if (serviceIds.length === 0) return;

    const manager = new StatusManager({
      serviceIds,
      enableSSE: options.enableSSE ?? true,
      enableWebSocket: options.enableWebSocket ?? false,
      fallbackPollInterval: options.fallbackPollInterval ?? 30000,
    });

    managerRef.current = manager;

    // Subscribe to status updates
    const unsubscribeStatus = manager.onStatusUpdate((newStatusMap) => {
      setStatusMap(newStatusMap);
      setIsConnected(true);
      setError(null);
    });

    // Subscribe to errors
    const unsubscribeError = manager.onError((err) => {
      setError(err);
      setIsConnected(false);
    });

    // Initialize manager
    manager.initialize().catch((err) => {
      setError(new Error(`Failed to initialize status manager: ${err}`));
    });

    // Cleanup on unmount
    return () => {
      unsubscribeStatus();
      unsubscribeError();
      manager.cleanup();
    };
  }, [serviceIds.join(','), options.enableSSE, options.enableWebSocket, options.fallbackPollInterval]);

  // Manual refresh function
  const refresh = useCallback(async () => {
    if (managerRef.current) {
      await managerRef.current.fetchAllStatus();
    }
  }, []);

  // Get status for specific service
  const getServiceStatus = useCallback((serviceId: string) => {
    return managerRef.current?.getServiceStatus(serviceId) || null;
  }, [statusMap]);

  // Fetch individual service status
  const fetchServiceStatus = useCallback(async (serviceId: string) => {
    if (managerRef.current) {
      return await managerRef.current.fetchServiceStatus(serviceId);
    }
    return null;
  }, []);

  return {
    statusMap,
    isConnected,
    error,
    refresh,
    getServiceStatus,
    fetchServiceStatus,
    // Helper functions
    getStatusText: (statusCode: number) => STATUS_CODES[statusCode as keyof typeof STATUS_CODES] || 'UNKNOWN',
    isHealthy: (serviceId: string) => {
      const status = getServiceStatus(serviceId);
      return status?.status_code === 0;
    },
    isDegraded: (serviceId: string) => {
      const status = getServiceStatus(serviceId);
      return status?.status_code === 1;
    },
    isFailed: (serviceId: string) => {
      const status = getServiceStatus(serviceId);
      return status?.status_code === 2;
    }
  };
}

// Simple hook for individual service status (polling-based)
export function useIndividualServiceStatus(serviceId: string, pollInterval: number = 5000) {
  const [status, setStatus] = useState<ServiceStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!serviceId) return;

    const fetchStatus = async () => {
      try {
        const response = await axios.get(`${API_ROOT}/status/${serviceId}`);
        setStatus(response.data);
        setError(null);
      } catch (err) {
        setError(new Error(`Failed to fetch status: ${err}`));
      } finally {
        setLoading(false);
      }
    };

    // Initial fetch
    fetchStatus();

    // Set up polling
    const interval = setInterval(fetchStatus, pollInterval);

    return () => clearInterval(interval);
  }, [serviceId, pollInterval]);

  return { status, loading, error };
}
