export interface ServiceNode {
    service_id: string
    label: string
    service_type: string
}

export interface ServiceRelation {
    relation_id: string
    source: string
    target: string
}

export interface ServiceStatusSummary {
    service_id: string
    stime: string  // ISO 8601 datetime string
    last_check: string  // ISO 8601 datetime string
    last_status_code: number  // 0=OK, 1=DEGRADED, 2=FAILED, 3=STARTING, 4=STOPPED, 5=UNKNOWN
    last_message: string
    check_count: number
    failed_count: number
}

export interface ServiceFailureRecord {
    service_id: string
    time: string
    message: string
}

export interface Notification {
    service_id: string
}