import apiClient from '@/services/apiClient'

export const getPermissionMatrix = () =>
  apiClient({
    url: '/api/v1/security/permissions',
    method: 'GET'
  })

export const getAuditLogs = (params = {}) =>
  apiClient({
    url: '/api/v1/security/audit-logs',
    method: 'GET',
    params
  })

export const exportAuditLogs = (params = {}) =>
  apiClient({
    url: '/api/v1/security/audit-logs/export',
    method: 'GET',
    params,
    responseType: 'blob'
  })
