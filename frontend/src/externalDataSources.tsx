import axios, { AxiosError } from 'axios'
import { useQuery, type UseQueryOptions, type UseQueryResult } from '@tanstack/react-query'

import { API_ROOT } from './constants.tsx'
import { type ServiceNode, type ServiceRelation, type ServiceStatusSummary, type ServiceFailureRecord } from './model.tsx'


type HookOption<T, E, S = T> = UseQueryOptions<T, E, S, any>
type HookQueryResult<T, E> = UseQueryResult<T, E>
type SimpleAxiosHook<T, S = T> = (options: HookOption<T, AxiosError>) => HookQueryResult<S, AxiosError>
// type ParametrizedAxiosHook<R, T, S =T> = (request: R, options: HookOption<T, AxiosError>) => HookQueryResult<S, AxiosError>

interface StatusRange {
    startDate?: string;
    endDate?: string;
}

const buildRangeQuery = (range?: StatusRange): string => {
    if (!range?.startDate && !range?.endDate) {
        return ''
    }
    const params = new URLSearchParams()
    if (range.startDate) {
        params.set('start', range.startDate)
    }
    if (range.endDate) {
        params.set('end', range.endDate)
    }
    const serialized = params.toString()
    return serialized ? `?${serialized}` : ''
}

export const fetchServiceStatus = async (serviceId: string, range?: StatusRange): Promise<ServiceStatusSummary> => {
    const query = buildRangeQuery(range)
    const { data } = await axios.get<ServiceStatusSummary>(`${API_ROOT}/status/${serviceId}${query}`)
    return data
}

export const fetchServiceFailures = async (serviceId: string, range?: StatusRange): Promise<ServiceFailureRecord[]> => {
    const query = buildRangeQuery(range)
    const { data } = await axios.get<ServiceFailureRecord[]>(`${API_ROOT}/status/${serviceId}/failures${query}`)
    return data
}


interface FlowResponse {
    serviceNodes: Array<ServiceNode>
    serviceRelations: Array<ServiceRelation>
}

export const useFlowChart: SimpleAxiosHook<FlowResponse> = (options) => {
    return useQuery({
        queryFn: async() => {
            const { data } = await axios.get(`${API_ROOT}/flowchart`)
            return data
        },
        placeholderData: {serviceNodes: [], serviceRelations: []},
        ...options
    })
}

export const useServiceStatus = (
    serviceId: string,
    range?: StatusRange,
    options?: HookOption<ServiceStatusSummary, AxiosError>
) => {
    return useQuery({
        queryKey: ['serviceStatus', serviceId, range?.startDate ?? null, range?.endDate ?? null],
        queryFn: () => fetchServiceStatus(serviceId, range),
        enabled: !!serviceId,
        staleTime: 30 * 60 * 1000,
        gcTime: 60 * 60 * 1000,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        refetchOnMount: false,
        retry: 0,
        ...options
    })
}

export const useServiceFailures = (
    serviceId: string,
    range?: StatusRange,
    options?: HookOption<ServiceFailureRecord[], AxiosError>
) => {
    return useQuery({
        queryKey: ['serviceFailures', serviceId, range?.startDate ?? null, range?.endDate ?? null],
        queryFn: () => fetchServiceFailures(serviceId, range),
        enabled: !!serviceId,
        staleTime: 5 * 60 * 1000,
        gcTime: 15 * 60 * 1000,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        refetchOnMount: false,
        retry: 0,
        ...options
    })
}