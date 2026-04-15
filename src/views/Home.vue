<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { generateTripPlan } from '@/services/api'
import type { TripPlan, TripPlanRequest } from '@/types'

const router = useRouter()
const loading = ref(false)
const loadingProgress = ref(0)
const loadingStatus = ref('')

const formData = ref<TripPlanRequest>({
  city: '',
  start_date: '',
  end_date: '',
  days: 3,
  preferences: '历史文化',
  budget: '中等',
  transportation: '公共交通',
  accommodation: '经济型酒店'
})

const canSubmit = computed(() => {
  return Boolean(formData.value.city && formData.value.start_date && formData.value.end_date)
})

const buildClientErrorPlan = (errorMessage: string): TripPlan => {
  const isTimeout = errorMessage.toLowerCase().includes('timeout')

  return {
    city: formData.value.city,
    start_date: formData.value.start_date,
    end_date: formData.value.end_date,
    days: [],
    weather_info: [],
    overall_suggestions: '后端没有在前端等待时间内返回行程。请查看生成状态中的具体原因，并检查后端终端日志。',
    generation_source: 'fallback',
    debug_info: {
      generation_source: 'fallback',
      failure_stage: isTimeout ? 'timeout' : 'network',
      failure_reason: isTimeout ? '后端响应超过前端等待时间' : '前端无法从后端获得响应',
      details: errorMessage
    }
  }
}

const handleSubmit = async () => {
  if (!canSubmit.value) {
    message.warning('请填写目的地和出行日期')
    return
  }

  loading.value = true
  loadingProgress.value = 10
  loadingStatus.value = '正在生成行程计划...'

  const progressInterval = window.setInterval(() => {
    if (loadingProgress.value < 90) {
      loadingProgress.value += 10
    }
  }, 800)

  try {
    const tripPlan = await generateTripPlan(formData.value)
    sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan))
    loadingProgress.value = 100
    loadingStatus.value = '完成'
    await router.push({ name: 'result' })
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '生成计划失败'
    const diagnosticPlan = buildClientErrorPlan(errorMessage)
    sessionStorage.setItem('tripPlan', JSON.stringify(diagnosticPlan))
    message.error('生成流程未返回完整行程，已打开诊断结果')
    await router.push({ name: 'result' })
  } finally {
    window.clearInterval(progressInterval)
    loading.value = false
  }
}
</script>

<template>
  <main class="home-page">
    <section class="intro">
      <p class="eyebrow">Hello Agents</p>
      <h1>智能旅行助手</h1>
      <p>输入目的地、日期和偏好，生成一份包含景点、餐饮、住宿、天气和预算的旅行计划。</p>
    </section>

    <section class="planner">
      <a-form :model="formData" layout="vertical" @finish="handleSubmit">
        <div class="form-grid">
          <a-form-item label="目的地城市" name="city" :rules="[{ required: true, message: '请输入目的地城市' }]">
            <a-input v-model:value="formData.city" placeholder="如：北京" />
          </a-form-item>

          <a-form-item label="旅行天数" name="days">
            <a-input-number v-model:value="formData.days" :min="1" :max="14" class="full-width" />
          </a-form-item>

          <a-form-item label="开始日期" name="start_date" :rules="[{ required: true, message: '请选择开始日期' }]">
            <a-date-picker v-model:value="formData.start_date" value-format="YYYY-MM-DD" class="full-width" />
          </a-form-item>

          <a-form-item label="结束日期" name="end_date" :rules="[{ required: true, message: '请选择结束日期' }]">
            <a-date-picker v-model:value="formData.end_date" value-format="YYYY-MM-DD" class="full-width" />
          </a-form-item>

          <a-form-item label="旅行偏好" name="preferences">
            <a-select v-model:value="formData.preferences">
              <a-select-option value="历史文化">历史文化</a-select-option>
              <a-select-option value="自然风光">自然风光</a-select-option>
              <a-select-option value="美食探索">美食探索</a-select-option>
              <a-select-option value="亲子休闲">亲子休闲</a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item label="预算" name="budget">
            <a-select v-model:value="formData.budget">
              <a-select-option value="经济">经济</a-select-option>
              <a-select-option value="中等">中等</a-select-option>
              <a-select-option value="奢华">奢华</a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item label="交通方式" name="transportation">
            <a-select v-model:value="formData.transportation">
              <a-select-option value="公共交通">公共交通</a-select-option>
              <a-select-option value="自驾">自驾</a-select-option>
              <a-select-option value="打车">打车</a-select-option>
              <a-select-option value="步行优先">步行优先</a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item label="住宿偏好" name="accommodation">
            <a-select v-model:value="formData.accommodation">
              <a-select-option value="经济型酒店">经济型酒店</a-select-option>
              <a-select-option value="舒适型酒店">舒适型酒店</a-select-option>
              <a-select-option value="高端酒店">高端酒店</a-select-option>
              <a-select-option value="民宿">民宿</a-select-option>
            </a-select>
          </a-form-item>
        </div>

        <a-button type="primary" html-type="submit" size="large" :loading="loading">
          开始规划
        </a-button>

        <div v-if="loading" class="progress">
          <a-progress :percent="loadingProgress" status="active" />
          <p>{{ loadingStatus }}</p>
        </div>
      </a-form>
    </section>
  </main>
</template>

<style scoped>
.home-page {
  min-height: 100vh;
  padding: 56px 20px;
}

.intro,
.planner {
  width: min(960px, 100%);
  margin: 0 auto;
}

.intro {
  margin-bottom: 28px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #0f766e;
  font-weight: 700;
}

h1 {
  margin: 0;
  font-size: 42px;
  line-height: 1.15;
}

.intro p:last-child {
  max-width: 680px;
  margin: 14px 0 0;
  color: #5d6878;
  font-size: 17px;
}

.planner {
  padding: 24px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 18px;
}

.full-width {
  width: 100%;
}

.progress {
  margin-top: 22px;
}

.progress p {
  margin: 8px 0 0;
  color: #5d6878;
}

@media (max-width: 720px) {
  .home-page {
    padding: 32px 14px;
  }

  h1 {
    font-size: 34px;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
