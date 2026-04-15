import json
import os
import re
import select
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from app.config import get_settings
from app.models.datamodels import (
    Attraction,
    Budget,
    DayPlan,
    DebugInfo,
    Hotel,
    Location,
    Meal,
    TripPlan,
    TripPlanRequest,
    WeatherInfo,
)


ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。

**工具调用格式:**
使用 maps_text_search 工具搜索景点。

**示例:**
- 搜索北京景点: keywords=景点, city=北京
- 搜索上海博物馆: keywords=博物馆, city=上海

**重要:**
- 必须使用工具搜索,不要编造信息
- 根据用户偏好({preferences})搜索{city}的景点
"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。

**工具调用格式:**
使用 maps_weather 工具查询天气。

请查询{city}的天气信息。
"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。

**工具调用格式:**
使用 maps_text_search 工具搜索酒店。

请搜索{city}的{accommodation}酒店。
"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。

**输出格式：**
严格返回可解析的 JSON，顶层字段必须直接匹配 TripPlan 模型。

**必须返回的顶层字段:**
- city
- start_date
- end_date
- days
- weather_info
- overall_suggestions
- budget

**days 列表中每项必须包含:**
- day_index
- date
- description
- transportation
- accommodation
- hotel
- attractions
- meals

**禁止包装格式:**
- 不能返回 {"trip_plan": ...}
- 不能返回 {"data": ...}
- 不能使用 "destination" 替代 "city"
- 不要返回额外的外层字段

**规划要求:**
1. weather_info 必须包含每天的天气
2. 温度为纯数字，不带°C
3. 每天安排 2-3 个景点
4. 考虑景点距离和游览时间
5. 包含早中晚三餐
6. 提供实用建议
7. 包含预算信息

**示例输出结构:**
{
  "city": "北京",
  "start_date": "2026-05-01",
  "end_date": "2026-05-04",
  "days": [
    {
      "day_index": 0,
      "date": "2026-05-01",
      "description": "第一天游览天安门广场和故宫，晚餐推荐簋街。",
      "transportation": "地铁和步行",
      "accommodation": "四星酒店",
      "hotel": {"name": "北京国际大酒店", "address": "东城区东长安街", "location": {"longitude": 116.4039, "latitude": 39.9151}, "price_range": "中等", "rating": "4.5", "estimated_cost": 800},
      "attractions": [{"name": "故宫", "address": "北京市东城区景山前街4号", "location": {"longitude": 116.4039, "latitude": 39.9163}, "visit_duration": 180, "description": "历史故宫，适合了解明清皇宫。", "ticket_price": 60}],
      "meals": [{"type": "lunch", "name": "北京烤鸭", "description": "品尝正宗烤鸭。", "estimated_cost": 120}]
    }
  ],
  "weather_info": [{"date": "2026-05-01", "day_weather": "晴", "night_weather": "多云", "day_temp": 25, "night_temp": 16, "wind_direction": "东南风", "wind_power": "3级"}],
  "overall_suggestions": "建议带雨伞并提前购买故宫门票。",
  "budget": {"total_attractions": 200, "total_hotels": 2400, "total_meals": 600, "total_transportation": 150, "total": 3350}
}
"""


class TripPlannerAgent:
    """Coordinates attraction, weather, hotel and planner agents.

    If hello-agents or external API keys are not available, the class returns a
    deterministic TripPlan so the full frontend/backend loop can still run.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.last_generation_source = "unknown"
        self.last_error = ""
        self.last_failure_stage: Optional[str] = None
        self.last_failure_reason: Optional[str] = None
        self.llm: Optional[Any] = None
        self.attraction_agent: Optional[Any] = None
        self.weather_agent: Optional[Any] = None
        self.hotel_agent: Optional[Any] = None
        self.planner_agent: Optional[Any] = None
        try:
            self._setup_agents()
        except Exception as exc:
            self.last_generation_source = "fallback"
            self.last_error = str(exc)
            self._set_failure(exc)

    def plan_trip(self, request: TripPlanRequest) -> TripPlan:
        if not self._agents_ready():
            self.last_generation_source = "fallback"
            self.last_error = "hello-agents or MCP tools are not ready"
            self._set_failure(RuntimeError(self.last_error))
            return self._fallback_plan(request)

        try:
            attraction_response = self.attraction_agent.run(
                f"请搜索{request.city}的{request.preferences}景点"
            )
            weather_response = self.weather_agent.run(f"请查询{request.city}的天气")
            hotel_response = self.hotel_agent.run(
                f"请搜索{request.city}的{request.accommodation}酒店"
            )

            planner_query = self._build_planner_query(
                request,
                str(attraction_response),
                str(weather_response),
                str(hotel_response),
            )
            planner_response = self.planner_agent.run(planner_query)
            trip_plan = self._parse_trip_plan(planner_response)
            self.last_generation_source = "agent_mcp"
            self.last_error = ""
            self.last_failure_stage = None
            self.last_failure_reason = None
            trip_plan.generation_source = "agent_mcp"
            trip_plan.debug_info = DebugInfo(generation_source="agent_mcp")
            return trip_plan
        except Exception as exc:
            self.last_generation_source = "fallback"
            self.last_error = str(exc)
            self._set_failure(exc)
            return self._fallback_plan(request)

    def _setup_agents(self) -> None:
        try:
            from hello_agents import HelloAgentsLLM, SimpleAgent
        except Exception:
            return

        if not self.settings.amap_api_key:
            return

        self.llm = HelloAgentsLLM(
            model=self.settings.llm_model_id or None,
            api_key=self.settings.llm_api_key or None,
            base_url=self.settings.llm_base_url or None,
            temperature=0.3,
            timeout=300,
        )
        text_search_tool = AMapMCPTool("maps_text_search", self.settings.amap_api_key)
        weather_tool = AMapMCPTool("maps_weather", self.settings.amap_api_key)

        self.attraction_agent = SimpleAgent(
            name="AttractionSearchAgent",
            llm=self.llm,
            system_prompt=ATTRACTION_AGENT_PROMPT,
        )
        self.attraction_agent.add_tool(text_search_tool)

        self.weather_agent = SimpleAgent(
            name="WeatherQueryAgent",
            llm=self.llm,
            system_prompt=WEATHER_AGENT_PROMPT,
        )
        self.weather_agent.add_tool(weather_tool)

        self.hotel_agent = SimpleAgent(
            name="HotelAgent",
            llm=self.llm,
            system_prompt=HOTEL_AGENT_PROMPT,
        )
        self.hotel_agent.add_tool(text_search_tool)

        self.planner_agent = SimpleAgent(
            name="PlannerAgent",
            llm=self.llm,
            system_prompt=PLANNER_AGENT_PROMPT,
        )

    def _run_amap_text_search(self, keywords: str, city: str) -> str:
        result = _call_amap_mcp(
            "maps_text_search",
            {"keywords": keywords, "city": city},
            self.settings.amap_api_key,
        )
        if result.get("isError"):
            raise RuntimeError(_mcp_text(result))
        return _mcp_text(result)

    def _run_amap_weather(self, city: str) -> str:
        result = _call_amap_mcp(
            "maps_weather",
            {"city": city},
            self.settings.amap_api_key,
        )
        if result.get("isError"):
            raise RuntimeError(_mcp_text(result))
        return _mcp_text(result)

    def _agents_ready(self) -> bool:
        return all(
            [
                self.attraction_agent,
                self.weather_agent,
                self.hotel_agent,
                self.planner_agent,
            ]
        )

    def _build_planner_query(
        self,
        request: TripPlanRequest,
        attraction_response: str,
        weather_response: str,
        hotel_response: str,
    ) -> str:
        return f"""
请根据以下信息生成{request.city}的{request.days}日旅行计划:

**用户需求:**
- 目的地: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.days}天
- 偏好: {request.preferences}
- 预算: {request.budget}
- 交通方式: {request.transportation}
- 住宿类型: {request.accommodation}

**景点信息:**
{attraction_response}

**天气信息:**
{weather_response}

**酒店信息:**
{hotel_response}

请生成详细的旅行计划,包括每天的景点安排、餐饮推荐、住宿信息和预算明细。
"""

    def _run_planner_llm(self, planner_query: str) -> str:
        if not self.settings.llm_api_key or not self.settings.llm_base_url or not self.settings.llm_model_id:
            raise RuntimeError("LLM配置不完整，请检查 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_ID")

        response = requests.post(
            f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.llm_model_id,
                "messages": [
                    {"role": "system", "content": PLANNER_AGENT_PROMPT},
                    {"role": "user", "content": planner_query},
                ],
                "temperature": 0.3,
            },
            timeout=300,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"LLM服务返回非JSON响应: HTTP {response.status_code} {response.text[:500]}") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"LLM服务HTTP错误: HTTP {response.status_code} {payload}")

        choices = payload.get("choices")
        if not choices:
            raise RuntimeError(
                "LLM服务返回空choices，当前模型可能不可用、无权限或该服务不兼容OpenAI chat/completions格式。"
                f"原始响应: {json.dumps(payload, ensure_ascii=False)[:1000]}"
            )

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise RuntimeError(
                "LLM服务没有返回message.content。"
                f"原始响应: {json.dumps(payload, ensure_ascii=False)[:1000]}"
            )

        return content

    def _parse_trip_plan(self, response: Any) -> TripPlan:
        text = str(response)
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("planner response does not contain JSON")
        data = json.loads(match.group(0))

        if isinstance(data, dict):
            if isinstance(data.get("trip_plan"), dict):
                data = data["trip_plan"]
            elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("trip_plan"), dict):
                data = data["data"]["trip_plan"]

            # 兼容常见字段别名
            if "destination" in data and "city" not in data:
                data["city"] = data.pop("destination")
            if "overall_advice" in data and "overall_suggestions" not in data:
                data["overall_suggestions"] = data.pop("overall_advice")
            if "summary" in data and "overall_suggestions" not in data:
                data["overall_suggestions"] = data.pop("summary")

            if isinstance(data.get("days"), list):
                normalized_days = []
                for item in data["days"]:
                    if not isinstance(item, dict):
                        normalized_days.append(item)
                        continue

                    if "day" in item and "day_index" not in item:
                        item["day_index"] = item.pop("day")
                    if "day_number" in item and "day_index" not in item:
                        item["day_index"] = item.pop("day_number")
                    if "date" not in item and "day_date" in item:
                        item["date"] = item.pop("day_date")
                    if "description" not in item and "desc" in item:
                        item["description"] = item.pop("desc")
                    if "description" not in item and "details" in item:
                        item["description"] = item.pop("details")
                    if "transportation" not in item and "transport" in item:
                        item["transportation"] = item.pop("transport")
                    if "accommodation" not in item and "stay" in item:
                        item["accommodation"] = item.pop("stay")
                    if "attractions" not in item and "sights" in item:
                        item["attractions"] = item.pop("sights")
                    if "meals" not in item and "food" in item:
                        item["meals"] = item.pop("food")

                    normalized_days.append(item)
                data["days"] = normalized_days

        return TripPlan.model_validate(data)

    def _fallback_plan(self, request: TripPlanRequest) -> TripPlan:
        start_date = self._parse_date(request.start_date)
        attractions = self._sample_attractions(request.city, request.preferences)
        days: List[DayPlan] = []
        total_attractions = 0
        total_hotels = 0
        total_meals = 0

        for day_index in range(request.days):
            current_date = start_date + timedelta(days=day_index)
            day_attractions = [
                attractions[(day_index * 2) % len(attractions)],
                attractions[(day_index * 2 + 1) % len(attractions)],
            ]
            hotel_cost = self._hotel_cost(request.budget)
            meal_cost = self._meal_cost(request.budget)
            total_attractions += sum(item.ticket_price or 0 for item in day_attractions)
            total_hotels += hotel_cost
            total_meals += meal_cost * 3

            days.append(
                DayPlan(
                    date=current_date.strftime("%Y-%m-%d"),
                    day_index=day_index,
                    description=(
                        f"围绕{request.preferences}安排{request.city}经典路线, "
                        f"使用{request.transportation}串联主要目的地。"
                    ),
                    transportation=request.transportation,
                    accommodation=request.accommodation,
                    hotel=Hotel(
                        name=f"{request.city}{request.accommodation}精选酒店",
                        address=f"{request.city}核心游览区附近",
                        location=day_attractions[0].location,
                        price_range=request.budget,
                        rating="4.5",
                        distance="距离主要景点约2公里",
                        type=request.accommodation,
                        estimated_cost=hotel_cost,
                    ),
                    attractions=day_attractions,
                    meals=[
                        Meal(
                            type="breakfast",
                            name=f"{request.city}本地早餐",
                            description="选择酒店附近口碑早餐店",
                            estimated_cost=meal_cost,
                        ),
                        Meal(
                            type="lunch",
                            name=f"{request.city}特色午餐",
                            description="靠近上午景点,减少路程消耗",
                            estimated_cost=meal_cost,
                        ),
                        Meal(
                            type="dinner",
                            name=f"{request.city}风味晚餐",
                            description="结束当天行程后从容用餐",
                            estimated_cost=meal_cost,
                        ),
                    ],
                )
            )

        total_transportation = request.days * self._transport_cost(request.transportation)
        budget = Budget(
            total_attractions=total_attractions,
            total_hotels=total_hotels,
            total_meals=total_meals,
            total_transportation=total_transportation,
            total=total_attractions + total_hotels + total_meals + total_transportation,
        )

        weather_info = [
            WeatherInfo(
                date=(start_date + timedelta(days=index)).strftime("%Y-%m-%d"),
                day_weather="多云",
                night_weather="晴",
                day_temp=24,
                night_temp=16,
                wind_direction="东南风",
                wind_power="1-3级",
            )
            for index in range(request.days)
        ]

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=weather_info,
            overall_suggestions=(
                "这是本地兜底生成的结构化行程。配置 OPENAI_API_KEY 和 AMAP_API_KEY 后,"
                "系统会优先尝试使用 hello-agents 与高德 MCP 工具生成更真实的计划。"
            ),
            budget=budget,
            generation_source="fallback",
            debug_info=DebugInfo(
                generation_source="fallback",
                failure_stage=self.last_failure_stage,
                failure_reason=self.last_failure_reason,
                details=self.last_error[:1000] if self.last_error else None,
            ),
        )

    def _set_failure(self, error: Exception) -> None:
        text = str(error)
        lowered = text.lower()

        if "429" in text or "quota" in lowered or "free model quota" in lowered:
            self.last_failure_stage = "llm"
            self.last_failure_reason = "LLM额度已用尽或触发限流"
        elif (
            "choices" in lowered
            or "openai api" in lowered
            or "llm服务" in text
            or ("nonetype" in lowered and "subscriptable" in lowered)
        ):
            self.last_failure_stage = "llm"
            self.last_failure_reason = "LLM服务返回空结果或当前模型不可用"
        elif "timeout" in lowered or "timed out" in lowered or "超时" in text:
            self.last_failure_stage = "timeout"
            self.last_failure_reason = "完整Agent流程响应超时"
        elif "hello_agents" in lowered or "hello-agents" in lowered or "tools.response" in lowered or "not ready" in lowered:
            self.last_failure_stage = "dependency"
            self.last_failure_reason = "hello-agents版本或依赖不完整"
        elif "userkey_plat_nomatch" in lowered:
            self.last_failure_stage = "amap"
            self.last_failure_reason = "高德API Key平台类型不匹配，请使用Web服务Key"
        elif "invalid_user_key" in lowered:
            self.last_failure_stage = "amap"
            self.last_failure_reason = "高德API Key无效"
        elif "amap" in lowered or "maps_" in lowered or "mcp" in lowered:
            self.last_failure_stage = "amap"
            self.last_failure_reason = "高德MCP工具调用失败"
        elif "json" in lowered or "tripplan" in lowered or "validation" in lowered:
            self.last_failure_stage = "planner"
            self.last_failure_reason = "规划Agent输出无法解析为TripPlan结构"
        else:
            self.last_failure_stage = "unknown"
            self.last_failure_reason = "完整Agent流程失败，已回退到本地兜底行程"

    def _sample_attractions(self, city: str, preferences: str) -> List[Attraction]:
        lon, lat = self._city_center(city)
        names = [
            f"{city}历史文化街区",
            f"{city}城市博物馆",
            f"{city}地标公园",
            f"{city}特色商业街",
            f"{city}艺术中心",
            f"{city}夜景观景点",
        ]
        return [
            Attraction(
                name=name,
                address=f"{city}市中心区域",
                location=Location(longitude=lon + index * 0.01, latitude=lat + index * 0.008),
                visit_duration=90 + index * 10,
                description=f"适合{preferences}偏好的{city}代表性目的地。",
                category=preferences,
                rating=4.5,
                ticket_price=30 + index * 10,
            )
            for index, name in enumerate(names)
        ]

    def _city_center(self, city: str) -> tuple[float, float]:
        centers: Dict[str, tuple[float, float]] = {
            "北京": (116.397128, 39.916527),
            "上海": (121.473701, 31.230416),
            "广州": (113.264385, 23.129112),
            "深圳": (114.057868, 22.543099),
            "杭州": (120.15515, 30.27415),
            "成都": (104.066541, 30.572269),
            "西安": (108.940174, 34.341568),
        }
        return centers.get(city, (116.397128, 39.916527))

    def _parse_date(self, value: str) -> datetime:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return datetime.now()

    def _hotel_cost(self, budget: str) -> int:
        return {"经济": 260, "中等": 480, "奢华": 1200}.get(budget, 480)

    def _meal_cost(self, budget: str) -> int:
        return {"经济": 35, "中等": 80, "奢华": 200}.get(budget, 80)

    def _transport_cost(self, transportation: str) -> int:
        return {"公共交通": 35, "自驾": 120, "打车": 180, "步行优先": 15}.get(
            transportation, 60
        )


class AMapMCPTool:
    """hello-agents Tool wrapper for the official AMap MCP server."""

    def __new__(cls, tool_name: str, api_key: str):
        from hello_agents.tools.base import Tool, ToolParameter
        from hello_agents.tools.response import ToolResponse

        class _AMapMCPTool(Tool):
            def __init__(self) -> None:
                descriptions = {
                    "maps_text_search": "关键词搜索高德 POI",
                    "maps_weather": "根据城市名称查询高德天气",
                }
                super().__init__(name=tool_name, description=descriptions[tool_name])

            def get_parameters(self) -> List[Any]:
                if tool_name == "maps_weather":
                    return [
                        ToolParameter(
                            name="city",
                            type="string",
                            description="城市名称或者 adcode",
                            required=True,
                        )
                    ]

                return [
                    ToolParameter(
                        name="keywords",
                        type="string",
                        description="搜索关键词",
                        required=True,
                    ),
                    ToolParameter(
                        name="city",
                        type="string",
                        description="查询城市",
                        required=False,
                        default="",
                    ),
                    ToolParameter(
                        name="types",
                        type="string",
                        description="POI 类型",
                        required=False,
                        default="",
                    ),
                ]

            def run(self, parameters: Dict[str, Any]) -> Any:
                result = _call_amap_mcp(tool_name, parameters, api_key)
                if result.get("isError"):
                    text = _mcp_text(result)
                    return ToolResponse.error(code="AMAP_MCP_ERROR", message=text)
                return ToolResponse.success(text=_mcp_text(result), data=result)

        return _AMapMCPTool()


def _call_amap_mcp(tool_name: str, arguments: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    env = os.environ.copy()
    env["AMAP_MAPS_API_KEY"] = api_key
    env.setdefault("NPM_CONFIG_CACHE", "/tmp/helloagents-npm-cache")

    process = subprocess.Popen(
        ["npx", "-y", "@amap/amap-maps-mcp-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    try:
        _mcp_send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "helloagents-trip-planner", "version": "0.1"},
                },
            },
        )
        _mcp_read(process, timeout=15)
        _mcp_send(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _mcp_send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
        message = _mcp_read(process, timeout=30)
        if not message:
            raise RuntimeError(_mcp_read_stderr(process) or "AMap MCP did not respond")
        if "error" in message:
            raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
        return message.get("result", {})
    finally:
        process.kill()


def _mcp_send(process: subprocess.Popen, message: Dict[str, Any]) -> None:
    if process.stdin is None:
        raise RuntimeError("MCP process stdin is not available")
    process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    process.stdin.flush()


def _mcp_read(process: subprocess.Popen, timeout: int) -> Optional[Dict[str, Any]]:
    if process.stdout is None:
        return None

    end = datetime.now().timestamp() + timeout
    while datetime.now().timestamp() < end:
        readable, _, _ = select.select([process.stdout], [], [], 0.2)
        if not readable:
            continue
        line = process.stdout.readline()
        if line:
            return json.loads(line)
    return None


def _mcp_read_stderr(process: subprocess.Popen) -> str:
    if process.stderr is None:
        return ""
    readable, _, _ = select.select([process.stderr], [], [], 0.2)
    if not readable:
        return ""
    return process.stderr.read()


def _mcp_text(result: Dict[str, Any]) -> str:
    content = result.get("content", [])
    if not content:
        return json.dumps(result, ensure_ascii=False)
    return "\n".join(str(item.get("text", "")) for item in content if item.get("type") == "text")
