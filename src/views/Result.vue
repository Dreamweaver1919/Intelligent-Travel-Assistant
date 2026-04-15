<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import type { TripPlan } from '@/types'

const router = useRouter()
const tripPlan = ref<TripPlan | null>(null)
const mapReady = ref(false)

const amapKey = import.meta.env.VITE_AMAP_WEB_KEY || ''

const allAttractions = computed(() => {
  return tripPlan.value?.days.flatMap(day => day.attractions) || []
})

const generationLabel = computed(() => {
  const source = tripPlan.value?.generation_source || tripPlan.value?.debug_info?.generation_source
  return source === 'agent_mcp' ? '完整 Agent + MCP 流程' : '本地兜底流程'
})

const generationTone = computed(() => {
  const source = tripPlan.value?.generation_source || tripPlan.value?.debug_info?.generation_source
  return source === 'agent_mcp' ? 'success' : 'warning'
})

const failureStageLabel = computed(() => {
  const stage = tripPlan.value?.debug_info?.failure_stage
  const labels: Record<string, string> = {
    llm: 'LLM',
    amap: '高德 MCP',
    unsplash: 'Unsplash 图片服务',
    dependency: '后端依赖',
    planner: '规划结果解析',
    timeout: '请求超时',
    network: '网络或后端服务',
    unknown: '未知环节'
  }
  return stage ? labels[stage] || stage : ''
})

const initMap = async () => {
  if (!amapKey || allAttractions.value.length === 0) {
    return
  }

  const first = allAttractions.value[0]
  const AMap = await AMapLoader.load({
    key: amapKey,
    version: '2.0'
  })

  const map = new AMap.Map('amap-container', {
    zoom: 12,
    center: [first.location.longitude, first.location.latitude]
  })

  allAttractions.value.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `${index + 1}`,
        direction: 'top'
      }
    })
    map.add(marker)
  })

  mapReady.value = true
}

const getExportElement = () => {
  const element = document.getElementById('trip-plan-content')
  if (!element) {
    message.error('没有找到可导出的行程内容')
    return null
  }
  return element
}

const exportAsImage = async () => {
  if (!tripPlan.value) return
  const element = getExportElement()
  if (!element) return

  const canvas = await html2canvas(element, { scale: 2, useCORS: true })
  const link = document.createElement('a')
  link.download = `${tripPlan.value.city}旅行计划.png`
  link.href = canvas.toDataURL('image/png')
  link.click()
}

const exportAsPDF = async () => {
  if (!tripPlan.value) return
  const element = getExportElement()
  if (!element) return

  const canvas = await html2canvas(element, { scale: 2, useCORS: true })
  const imgData = canvas.toDataURL('image/png')
  const pdf = new jsPDF('p', 'mm', 'a4')
  const imgWidth = 210
  const imgHeight = (canvas.height * imgWidth) / canvas.width

  pdf.addImage(imgData, 'PNG', 0, 0, imgWidth, imgHeight)
  pdf.save(`${tripPlan.value.city}旅行计划.pdf`)
}

onMounted(async () => {
  const savedPlan = sessionStorage.getItem('tripPlan')
  if (!savedPlan) {
    message.warning('请先生成旅行计划')
    await router.replace({ name: 'home' })
    return
  }

  tripPlan.value = JSON.parse(savedPlan) as TripPlan
  await nextTick()
  initMap().catch(() => {
    message.warning('地图加载失败，请检查高德 Web Key')
  })
})
</script>

<template>
  <main class="result-page">
    <template v-if="tripPlan">
      <header class="toolbar">
        <div>
          <p class="eyebrow">{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</p>
          <h1>{{ tripPlan.city }}旅行计划</h1>
        </div>
        <div class="actions">
          <a-button @click="router.push({ name: 'home' })">重新规划</a-button>
          <a-button @click="exportAsImage">导出图片</a-button>
          <a-button type="primary" @click="exportAsPDF">导出 PDF</a-button>
        </div>
      </header>

      <section id="trip-plan-content" class="content">
        <section class="diagnostic">
          <div>
            <h2>生成状态</h2>
            <p>
              <a-tag :color="generationTone">{{ generationLabel }}</a-tag>
              <span v-if="tripPlan.debug_info?.failure_stage">
                失败环节：{{ failureStageLabel }}
              </span>
            </p>
          </div>
          <div v-if="tripPlan.debug_info?.failure_reason" class="diagnostic-detail">
            <strong>具体原因</strong>
            <p>{{ tripPlan.debug_info.failure_reason }}</p>
            <details v-if="tripPlan.debug_info.details">
              <summary>查看原始错误</summary>
              <pre>{{ tripPlan.debug_info.details }}</pre>
            </details>
          </div>
        </section>

        <section class="summary">
          <h2>总体建议</h2>
          <p>{{ tripPlan.overall_suggestions }}</p>
        </section>

        <section v-if="tripPlan.budget" class="budget">
          <h2>预算</h2>
          <div class="budget-grid">
            <span>景点：¥{{ tripPlan.budget.total_attractions }}</span>
            <span>住宿：¥{{ tripPlan.budget.total_hotels }}</span>
            <span>餐饮：¥{{ tripPlan.budget.total_meals }}</span>
            <span>交通：¥{{ tripPlan.budget.total_transportation }}</span>
            <strong>总计：¥{{ tripPlan.budget.total }}</strong>
          </div>
        </section>

        <section v-if="amapKey" class="map-section">
          <h2>景点地图</h2>
          <div id="amap-container" class="map"></div>
          <p v-if="!mapReady" class="muted">地图加载中，或暂无可标记景点。</p>
        </section>

        <section class="days">
          <article v-for="day in tripPlan.days" :key="`${day.date}-${day.day_index}`" class="day">
            <h2>第 {{ day.day_index + 1 }} 天：{{ day.date }}</h2>
            <p>{{ day.description }}</p>
            <p class="muted">交通：{{ day.transportation }} / 住宿：{{ day.accommodation }}</p>

            <div v-if="day.hotel" class="block">
              <h3>住宿</h3>
              <p>{{ day.hotel.name }}，{{ day.hotel.address }}</p>
              <p class="muted">{{ day.hotel.type }} / {{ day.hotel.price_range }} / ¥{{ day.hotel.estimated_cost }}</p>
            </div>

            <div class="block">
              <h3>景点</h3>
              <div class="attractions">
                <article v-for="attraction in day.attractions" :key="attraction.name" class="attraction">
                  <img v-if="attraction.image_url" :src="attraction.image_url" :alt="attraction.name" />
                  <div>
                    <h4>{{ attraction.name }}</h4>
                    <p>{{ attraction.description }}</p>
                    <p class="muted">
                      {{ attraction.address }} / {{ attraction.visit_duration }} 分钟 / ¥{{ attraction.ticket_price || 0 }}
                    </p>
                  </div>
                </article>
              </div>
            </div>

            <div class="block">
              <h3>餐饮</h3>
              <ul>
                <li v-for="meal in day.meals" :key="`${meal.type}-${meal.name}`">
                  {{ meal.type }}：{{ meal.name }}，约 ¥{{ meal.estimated_cost }}
                </li>
              </ul>
            </div>
          </article>
        </section>
      </section>
    </template>
  </main>
</template>

<style scoped>
.result-page {
  min-height: 100vh;
  padding: 32px 20px 56px;
}

.toolbar,
.content {
  width: min(1100px, 100%);
  margin: 0 auto;
}

.toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 22px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #0f766e;
  font-weight: 700;
}

h1,
h2,
h3,
h4 {
  margin: 0;
}

h1 {
  font-size: 34px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.content,
.diagnostic,
.summary,
.budget,
.map-section,
.day {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.content {
  padding: 20px;
}

.summary,
.diagnostic,
.budget,
.map-section,
.day {
  padding: 20px;
  margin-bottom: 16px;
}

.diagnostic {
  display: grid;
  gap: 14px;
}

.diagnostic p {
  margin: 10px 0 0;
  color: #334155;
}

.diagnostic-detail {
  padding: 14px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  border-radius: 8px;
}

.diagnostic-detail strong {
  color: #9a3412;
}

details {
  margin-top: 10px;
}

summary {
  cursor: pointer;
  color: #9a3412;
}

pre {
  margin: 10px 0 0;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #7c2d12;
}

.summary p,
.day p {
  color: #334155;
  line-height: 1.8;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.budget-grid span,
.budget-grid strong {
  padding: 12px;
  background: #f8fafc;
  border-radius: 8px;
}

.map {
  width: 100%;
  height: 360px;
  margin-top: 14px;
  border-radius: 8px;
  overflow: hidden;
}

.muted {
  color: #64748b;
}

.block {
  margin-top: 18px;
}

.attractions {
  display: grid;
  gap: 14px;
  margin-top: 12px;
}

.attraction {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 16px;
  padding: 14px;
  background: #f8fafc;
  border-radius: 8px;
}

.attraction img {
  width: 160px;
  height: 110px;
  object-fit: cover;
  border-radius: 8px;
}

ul {
  margin: 10px 0 0;
  padding-left: 20px;
  line-height: 1.9;
}

@media (max-width: 760px) {
  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .budget-grid {
    grid-template-columns: 1fr;
  }

  .attraction {
    grid-template-columns: 1fr;
  }

  .attraction img {
    width: 100%;
    height: 180px;
  }
}
</style>
