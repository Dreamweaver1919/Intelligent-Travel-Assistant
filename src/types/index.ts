// frontend/src/types/index.ts
export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
}

export interface Hotel {    
    name: string
    address: string
    location?: Location
    price_range: string
    rating: string
    distance: string
    type: string
    estimated_cost: number
}

export interface Meal {
    type: string
    name: string
    address?: string
    location?: Location
    description?: string
    estimated_cost: number
}

export interface DayPlan {
    date: string
    day_index: number
    description: string
    transportation: string
    accommodation: string
    hotel?: Hotel
    attractions: Attraction[]
    meals: Meal[]
}

export interface WeatherInfo {

    date: string
    day_weather: string
    night_weather: string
    day_temp: number
    night_temp: number
    wind_direction: string
    wind_power: string
    
}

export interface Budget {
    total_attractions: number
    total_hotels: number
    total_meals: number
    total_transportation: number
    total: number
}

export interface DebugInfo {
  generation_source: 'agent_mcp' | 'fallback' | 'unknown' | string
  failure_stage?: 'llm' | 'amap' | 'unsplash' | 'dependency' | 'planner' | 'timeout' | 'network' | 'unknown' | string
  failure_reason?: string
  details?: string
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
  generation_source?: 'agent_mcp' | 'fallback' | 'unknown' | string
  debug_info?: DebugInfo
}

export interface TripPlanRequest {
  city: string
  start_date: string
  end_date: string
  days: number
  preferences: string
  budget: string
  transportation: string
  accommodation: string
}
