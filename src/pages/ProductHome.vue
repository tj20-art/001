<template>
  <div class="page-shell">
    <CommonHeader />

    <main class="page-main storefront">
      <section class="storefront-hero">
        <div class="hero-content">
          <h1>发现日常好物</h1>
          <p>选购日用、数码和家居好物。价格与库存，随时可查。</p>
          <form class="catalog-search" role="search" @submit.prevent="handleSearch">
            <el-icon aria-hidden="true"><Search /></el-icon>
            <input v-model="searchName" type="search" aria-label="搜索商品名称" placeholder="搜索商品名称" />
            <button type="submit">搜索</button>
          </form>
        </div>
        <img class="hero-image" :src="heroImage" alt="" width="1536" height="1024" fetchpriority="high" />
      </section>

      <section ref="catalog" class="catalog" aria-labelledby="catalog-heading">
        <div class="catalog-heading">
          <div>
            <h2 id="catalog-heading">{{ appliedFilters.category || '全部商品' }}</h2>
            <p v-if="!loadError" class="muted-text">{{ total }} 件在售商品</p>
          </div>
          <RouterLink v-if="isAuthenticated && canManageProducts" class="catalog-link" to="/my-products">
            {{ isAdmin ? '管理全部商品' : '我的商品' }}
            <el-icon aria-hidden="true"><ArrowRight /></el-icon>
          </RouterLink>
        </div>

        <div class="filter-bar">
          <nav class="categories" aria-label="商品分类">
            <button type="button" :aria-pressed="!appliedFilters.category" @click="selectCategory()">全部</button>
            <button
              v-for="category in categories"
              :key="category"
              type="button"
              :aria-pressed="appliedFilters.category === category"
              @click="selectCategory(category)"
            >
              {{ category }}
            </button>
          </nav>
          <div class="filter-actions">
            <button
              class="link-button"
              type="button"
              :aria-expanded="advancedOpen"
              aria-controls="product-id-filter"
              @click="advancedOpen = !advancedOpen"
            >
              按 ID 查找
            </button>
            <button
              v-if="appliedFilters.name || appliedFilters.product_id || appliedFilters.category"
              class="link-button"
              type="button"
              @click="handleReset"
            >
              清除筛选
            </button>
          </div>
        </div>
        <form v-show="advancedOpen" id="product-id-filter" class="advanced-filter" @submit.prevent="handleSearch">
          <label for="product-id">商品 ID</label>
          <input
            id="product-id"
            v-model.trim="searchId"
            inputmode="numeric"
            pattern="[0-9]*"
            placeholder="输入商品编号"
          />
          <el-button native-type="submit" plain>查找</el-button>
        </form>

        <AppLoading v-if="loading" />
        <ListError v-else-if="loadError" :message="loadError" @retry="fetchPage()" />
        <div v-else-if="items.length" class="goods-grid">
          <article v-for="(item, index) in items" :key="item.id" class="goods-card section-card">
            <button class="goods-cover" type="button" :aria-label="'查看 ' + item.name" @click="openDetail(item)">
              <ProductCover :src="coverOf(item)" :loading="index < 4 ? 'eager' : 'lazy'" />
            </button>
            <div class="goods-content">
              <span v-if="item.category" class="goods-category">{{ item.category }}</span>
              <h3>{{ item.name }}</h3>
              <div class="product-price">
                <strong>{{ money(item.price) }}</strong>
                <span>{{ item.stock > 0 ? '库存 ' + item.stock : '暂时缺货' }}</span>
              </div>
              <el-button
                v-if="canLoadCart"
                plain
                type="primary"
                :loading="addingProduct === item.id"
                :disabled="!!addingProduct || item.stock < 1"
                @click="addProduct(item)"
                >加入购物车</el-button
              >
              <el-button v-else plain @click="openDetail(item)">查看详情</el-button>
            </div>
          </article>
        </div>
        <el-empty v-else description="没有找到符合条件的商品">
          <el-button
            v-if="appliedFilters.name || appliedFilters.product_id || appliedFilters.category"
            plain
            @click="handleReset"
            >清除筛选</el-button
          >
        </el-empty>
        <div v-if="!loading && !loadError && total > pageSize" class="pagination-bar">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            :pager-count="5"
            layout="prev, pager, next"
            @current-change="goToPage"
          />
        </div>
      </section>

      <aside class="trust-strip" aria-label="交易保障">
        <span
          ><el-icon aria-hidden="true"><Lock /></el-icon> 加密交易</span
        >
        <span
          ><el-icon aria-hidden="true"><CircleCheck /></el-icon> 商户实名发布</span
        >
        <span
          ><el-icon aria-hidden="true"><Tickets /></el-icon> 订单进度可查</span
        >
      </aside>
    </main>

    <el-dialog v-model="detailVisible" title="商品详情" width="760px" destroy-on-close @close="closeDetail">
      <AppLoading v-if="detailLoading" />
      <ListError v-else-if="detailError" :message="detailError" @retry="openDetail(detailTarget)" />
      <div v-else-if="detail" class="detail-grid">
        <div class="detail-media">
          <el-carousel v-if="detail.image_urls.length > 1" :autoplay="false" height="230px" trigger="click">
            <el-carousel-item v-for="(image, index) in detail.image_urls" :key="image + index">
              <img :src="mediaUrl(image)" :alt="detail.name" />
            </el-carousel-item>
          </el-carousel>
          <div v-else-if="detail.image_urls.length" class="detail-single">
            <ProductCover :src="coverOf(detail)" :alt="detail.name" loading="eager" />
          </div>
          <video v-if="detail.video_url" :src="mediaUrl(detail.video_url)" preload="metadata" controls></video>
          <div v-if="!detail.image_urls.length && !detail.video_url" class="detail-single"><ProductCover /></div>
        </div>
        <div class="detail-copy">
          <p v-if="detail.category" class="goods-category">{{ detail.category }}</p>
          <h2>{{ detail.name }}</h2>
          <p class="detail-price">{{ money(detail.price) }}</p>
          <p class="muted-text">库存 {{ detail.stock }} · 商户 {{ detail.seller_id }}</p>
          <p class="detail-description">{{ detail.description || '暂无商品介绍' }}</p>
          <div v-if="canLoadCart && detail.stock > 0" class="detail-order">
            <el-input-number v-model="quantity" :min="1" :max="detail.stock" aria-label="购买数量" />
            <el-button
              type="primary"
              :loading="addingProduct === detail.id"
              :disabled="!!addingProduct"
              @click="addProduct(detail, quantity)"
            >
              加入购物车
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import { markRaw } from 'vue'
import { mapActions, mapGetters, mapState } from 'vuex'
import CommonHeader from '@/components/CommonHeader.vue'
import AppLoading from '@/components/AppLoading.vue'
import ListError from '@/components/ListError.vue'
import ProductCover from '@/components/ProductCover.vue'
import heroImage from '@/assets/storefront-homewares.jpg'
import { getProductDetail, getProductList } from '@/services/productService'
import { coverOf, mediaUrl, money } from '@/utils/productDisplay'
import { usePagedList } from '@/utils/usePagedList'

export default {
  name: 'ProductHome',
  components: { CommonHeader, AppLoading, ListError, ProductCover },
  setup() {
    const list = usePagedList(
      (params, config) => getProductList({ ...params, status: 'on_sale', view: 'summary', overview: true }, config),
      'product_list'
    )
    return { ...list, heroImage }
  },
  data() {
    return {
      searchName: '',
      searchId: '',
      advancedOpen: false,
      detailVisible: false,
      detailLoading: false,
      detailError: '',
      detail: null,
      detailTarget: null,
      detailRequest: null,
      quantity: 1,
      addingProduct: null
    }
  },
  computed: {
    ...mapState('authModule', ['isAuthenticated']),
    ...mapGetters('authModule', ['isAdmin', 'canManageProducts', 'canShop']),
    canLoadCart() {
      return this.isAuthenticated && this.canShop
    }
  },
  watch: {
    canLoadCart: {
      immediate: true,
      handler(enabled) {
        if (enabled) this.fetchCart({ silentError: true }).catch(() => {})
      }
    }
  },
  mounted() {
    this.fetchPage()
  },
  beforeUnmount() {
    this.closeDetail()
  },
  methods: {
    ...mapActions('cartModule', ['addToCart', 'fetchCart']),
    coverOf,
    mediaUrl,
    money,
    async handleSearch() {
      this.scrollToCatalog()
      await this.fetchPage(
        {
          name: this.searchName.trim() || undefined,
          product_id: this.searchId || undefined,
          category: this.appliedFilters.category
        },
        1
      )
    },
    handleReset() {
      this.searchName = ''
      this.searchId = ''
      this.advancedOpen = false
      return this.fetchPage({}, 1)
    },
    selectCategory(category) {
      return this.fetchPage({ ...this.appliedFilters, category }, 1)
    },
    goToPage(page) {
      this.scrollToCatalog()
      return this.fetchPage(this.appliedFilters, page)
    },
    scrollToCatalog() {
      this.$refs.catalog?.scrollIntoView({ block: 'start' })
    },
    closeDetail() {
      this.detailRequest?.abort()
      this.detailRequest = null
    },
    async openDetail(item) {
      this.closeDetail()
      const controller = markRaw(new AbortController())
      this.detailRequest = controller
      this.detailTarget = item
      this.detail = null
      this.detailVisible = true
      this.detailLoading = true
      this.detailError = ''
      this.quantity = 1
      try {
        const response = await getProductDetail(item.id, { signal: controller.signal, silentError: true })
        if (!controller.signal.aborted) this.detail = response.data?.product_info
      } catch (error) {
        if (!controller.signal.aborted) this.detailError = error.response?.data?.message || '商品详情加载失败。'
      } finally {
        if (this.detailRequest === controller) this.detailLoading = false
      }
    },
    async addProduct(item, quantity = 1) {
      if (!this.canLoadCart || this.addingProduct || !Number.isInteger(quantity) || quantity < 1) return
      this.addingProduct = item.id
      try {
        await this.addToCart({ product_id: item.id, quantity })
        this.$message.success('已加入购物车')
        this.detailVisible = false
      } catch {
        // The API client reports unavailable stock and other errors.
      } finally {
        this.addingProduct = null
      }
    }
  }
}
</script>

<style scoped>
.storefront {
  padding-top: 20px;
}
.storefront-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.03fr) minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid #e5d7c6;
  border-radius: 20px;
  background: #f0e4d6;
}
.hero-content {
  display: grid;
  align-content: center;
  padding: clamp(24px, 4.2vw, 64px);
  min-height: 290px;
}
.hero-content h1 {
  margin: 0;
  letter-spacing: -0.055em;
  font-size: clamp(30px, 4.2vw, 56px);
  line-height: 1.15;
}
.hero-content p {
  margin: 16px 0 24px;
  color: var(--mall-muted);
  line-height: 1.65;
}
.hero-image {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 0;
  object-fit: cover;
  max-height: 330px;
  object-position: 50% 53%;
}
.catalog-search {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 5px 5px 5px 14px;
  border: 1px solid var(--mall-border);
  border-radius: 10px;
  background: white;
}
.catalog-search .el-icon {
  color: var(--mall-muted);
  flex: none;
}
.catalog-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--mall-ink);
  padding: 7px 0;
}
.catalog-search input:focus-visible {
  outline-offset: 0;
  border-radius: 3px;
}
.catalog-search button {
  flex: none;
  height: 40px;
  padding-inline: 18px;
  border: 0;
  border-radius: 7px;
  background: var(--mall-accent);
  color: white;
  cursor: pointer;
}
.catalog {
  margin-top: 28px;
  scroll-margin-top: 128px;
}
.catalog-heading,
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.catalog-heading h2 {
  margin: 0;
  font-size: 28px;
  overflow-wrap: anywhere;
}
.catalog-heading p {
  margin: 5px 0 0;
  font-size: 13px;
}
.catalog-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--mall-accent);
  font-weight: 600;
  font-size: 14px;
  flex: none;
}
.filter-bar {
  margin-block: 16px;
  flex-wrap: wrap;
}
.categories,
.filter-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.categories button,
.link-button {
  min-height: 35px;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 7px;
  padding: 5px 11px;
  cursor: pointer;
  color: var(--mall-muted);
}
.categories button:hover,
.categories button[aria-pressed='true'] {
  border-color: #e3c6b8;
  background: var(--mall-accent-soft);
  color: var(--mall-accent);
}
.link-button:hover {
  color: var(--mall-accent);
}
.advanced-filter {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 0 16px;
  color: var(--mall-muted);
}
.advanced-filter input {
  min-width: 0;
  max-width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--mall-border);
  border-radius: 6px;
}
.goods-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.goods-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: none;
  transition: box-shadow 150ms ease, border-color 150ms ease;
}
.goods-card:hover {
  border-color: #d4b8a9;
  box-shadow: var(--mall-shadow);
}
.goods-cover {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  padding: 0;
  border: 0;
  background: #eee9e0;
  overflow: hidden;
  cursor: pointer;
}
.goods-cover:focus-visible {
  outline-offset: -3px;
}
.goods-content {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  flex: 1;
  padding: 14px;
  gap: 8px;
}
.goods-category {
  color: var(--mall-muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.goods-content h3 {
  margin: 0;
  font-size: 16px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.product-price {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: auto;
}
.product-price strong,
.detail-price {
  color: var(--mall-accent);
  font-size: 21px;
  font-weight: 700;
}
.product-price span {
  color: var(--mall-muted);
  font-size: 12px;
}
.goods-content .el-button {
  width: 100%;
  margin-top: 4px;
  min-height: 36px;
}
.trust-strip {
  display: flex;
  justify-content: center;
  gap: 12px 32px;
  flex-wrap: wrap;
  padding: 20px 0 4px;
  margin-top: 28px;
  border-top: 1px solid var(--mall-border);
  color: var(--mall-muted);
  font-size: 13px;
}
.trust-strip span {
  display: flex;
  gap: 6px;
  align-items: center;
}
.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.88fr);
  gap: 20px;
}
.detail-media img,
.detail-media video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #eee9e0;
}
.detail-single {
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: 10px;
}
.detail-media video {
  max-height: 260px;
  margin-top: 8px;
}
.detail-copy h2 {
  margin: 0 0 8px;
  overflow-wrap: anywhere;
}
.detail-price {
  margin: 0;
}
.detail-description {
  line-height: 1.7;
  overflow-wrap: anywhere;
  white-space: pre-line;
}
.detail-order {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 1024px) {
  .goods-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .storefront-hero {
    grid-template-columns: 1fr;
  }
  .hero-content {
    min-height: 0;
    padding: 22px;
  }
  .hero-content p {
    margin: 9px 0 15px;
  }
  .hero-image {
    aspect-ratio: 3 / 1;
    height: auto;
  }
  .catalog {
    margin-top: 20px;
  }
  .catalog-heading h2 {
    font-size: 22px;
  }
  .goods-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }
  .goods-content {
    padding: 10px;
  }
  .goods-content h3 {
    font-size: 14px;
  }
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 350px) {
  .goods-grid {
    grid-template-columns: 1fr;
  }
  .catalog-heading {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}
</style>
