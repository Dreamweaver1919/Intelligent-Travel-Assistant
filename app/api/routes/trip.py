import asyncio

from fastapi import APIRouter

from app.models.datamodels import DebugInfo
from app.agents.tripplanneragent import TripPlannerAgent
from app.config import get_settings
from app.models.datamodels import TripPlanRequest, TripPlan
from app.services.unsplash_service import UnsplashService


router = APIRouter()
settings = get_settings()
trip_planner_agent = TripPlannerAgent()
unsplash_service = UnsplashService(settings.unsplash_access_key)


@router.post("/plan", response_model=TripPlan)
async def create_trip_plan(request: TripPlanRequest) -> TripPlan:
    try:
        trip_plan = await asyncio.wait_for(
            asyncio.to_thread(trip_planner_agent.plan_trip, request),
            timeout=settings.agent_timeout_seconds,
        )
    except asyncio.TimeoutError:
        trip_planner_agent.last_generation_source = "fallback"
        trip_planner_agent.last_error = (
            f"完整Agent流程超过 {settings.agent_timeout_seconds} 秒仍未返回"
        )
        trip_planner_agent._set_failure(TimeoutError(trip_planner_agent.last_error))
        trip_plan = trip_planner_agent._fallback_plan(request)

    unsplash_error = ""
    should_fetch_images = trip_plan.generation_source == "agent_mcp"
    fetched_images = 0

    if should_fetch_images:
        for day in trip_plan.days:
            for attraction in day.attractions:
                if attraction.image_url or fetched_images >= 3:
                    continue
                try:
                    attraction.image_url = unsplash_service.get_photo_url(
                        f"{attraction.name} {trip_plan.city}"
                    )
                    fetched_images += 1
                except Exception as exc:
                    unsplash_error = str(exc)
                    break
            if unsplash_error:
                break

    if unsplash_error:
        if not trip_plan.debug_info:
            trip_plan.debug_info = DebugInfo(generation_source=trip_plan.generation_source)
        if trip_plan.generation_source == "agent_mcp":
            trip_plan.generation_source = "fallback"
            trip_plan.debug_info.generation_source = "fallback"
        trip_plan.debug_info.failure_stage = "unsplash"
        trip_plan.debug_info.failure_reason = "Unsplash图片服务调用失败"
        trip_plan.debug_info.details = unsplash_error[:1000]

    return trip_plan
