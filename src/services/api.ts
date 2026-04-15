import axios from 'axios'
import type { TripPlanRequest, TripPlan } from '@/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.response.use(
  response => response,
  error => {
    const detail = error.response?.data?.detail || error.message || '请求失败'
    return Promise.reject(new Error(detail))
  }
)

export const generateTripPlan = async (request: TripPlanRequest): Promise<TripPlan> => {
  const response = await api.post<TripPlan>('/trip/plan', request)
  return response.data
}
