import { onBeforeUnmount, ref } from 'vue'

export function usePagedList(loadPage, listKey, pageSize = 24) {
  const items = ref([])
  const page = ref(1)
  const total = ref(0)
  const summary = ref({})
  const categories = ref([])
  const loading = ref(true)
  const loadError = ref('')
  const appliedFilters = ref({})
  let request

  async function fetchPage(filters = appliedFilters.value, pageNumber = page.value) {
    request?.abort()
    const controller = new AbortController()
    request = controller
    appliedFilters.value = { ...filters }
    page.value = pageNumber
    loading.value = true
    loadError.value = ''

    const load = async (number) => {
      const response = await loadPage(
        { ...filters, page: number, page_size: pageSize },
        { signal: controller.signal, silentError: true }
      )
      return response.data || {}
    }

    try {
      let data = await load(pageNumber)
      if (controller.signal.aborted) return
      const lastPage = Math.max(1, Math.ceil((data.pagination?.total ?? data[listKey]?.length ?? 0) / pageSize))
      if (pageNumber > lastPage) {
        data = await load(lastPage)
        if (controller.signal.aborted) return
        page.value = lastPage
      }
      items.value = data[listKey] || []
      total.value = data.pagination?.total ?? items.value.length
      summary.value = data.summary || {}
      if (data.categories) categories.value = data.categories
    } catch (error) {
      if (!controller.signal.aborted) {
        loadError.value = error.response?.data?.message || '列表加载失败，请重试。'
      }
    } finally {
      if (request === controller) {
        request = undefined
        loading.value = false
      }
    }
  }

  onBeforeUnmount(() => request?.abort())

  return { items, page, pageSize, total, summary, categories, loading, loadError, appliedFilters, fetchPage }
}
