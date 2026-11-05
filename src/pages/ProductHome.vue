<template>
  <div class="page-shell mall-home-page">
    <common-header />

    <main class="home-main page-main">
      <nav class="category-nav" aria-label="商品分类">
        <button :class="{ active: !selectedCategory }" @click="selectedCategory = ''">全部商品</button>
        <button
          v-for="category in categories"
          :key="category"
          :class="{ active: selectedCategory === category }"
          @click="selectedCategory = category"
        >
          {{ category }}
        </button>
        <span class="category-promise"><i class="el-icon-lock"></i> 国密加密交易</span>
      </nav>

      <section class="hero-section">
        <div class="hero-copy section-card">
          <span class="hero-tag">秋日生活焕新</span>
          <h1>好物认真挑<br /><em>交易安心购</em></h1>
          <p>精选日常好物，价格与库存一目了然。身份验证、订单提交和支付请求均由安全机制全程守护。</p>
          <div class="hero-search">
            <el-input
              v-model="searchParams.name"
              prefix-icon="el-icon-search"
              placeholder="搜索你想要的商品"
              @keyup.enter.native="handleSearch"
            />
            <el-button type="primary" @click="handleSearch">搜索</el-button>
          </div>
          <div class="hero-actions">
            <button class="text-action" @click="scrollToGoods">浏览本期精选 <i class="el-icon-right"></i></button>
            <button v-if="canManageProducts" class="text-action" @click="$router.push('/my-products')">
              进入商家工作台
            </button>
          </div>
        </div>

        <div class="hero-panel">
          <div class="feature-visual">
            <span class="visual-kicker">MEMBER PICKS</span>
            <strong>会员精选</strong>
            <p>{{ inStockCount }} 件现货好物，随时加入购物车</p>
            <el-button v-if="!isAuthenticated" size="small" round @click="$router.push('/user-register')"
              >免费注册</el-button
            >
            <el-button v-else-if="canShop" size="small" round @click="$router.push('/cart')">查看购物车</el-button>
          </div>
          <div class="security-note">
            <i class="el-icon-medal"></i>
            <div><strong>可信交易保障</strong><span>应用层密文传输 · 操作全程可追溯</span></div>
          </div>
        </div>
      </section>

      <section class="service-strip">
        <div>
          <i class="el-icon-truck"></i><span><strong>快速履约</strong><small>清晰订单进度</small></span>
        </div>
        <div>
          <i class="el-icon-circle-check"></i><span><strong>品质好物</strong><small>商户实名发布</small></span>
        </div>
        <div>
          <i class="el-icon-refresh-left"></i><span><strong>放心选购</strong><small>订单状态可追踪</small></span>
        </div>
        <div>
          <i class="el-icon-lock"></i><span><strong>安全支付</strong><small>国密算法保护</small></span>
        </div>
      </section>

      <section class="search-section section-card" ref="goodsSection">
        <div class="search-bar">
          <span class="filter-label">精确查找</span>
          <el-input v-model="searchParams.product_id" placeholder="商品 ID" class="search-input" clearable />
          <el-input v-model="searchParams.name" placeholder="商品名称" class="search-input" clearable />
          <el-button type="primary" @click="handleSearch">搜索商品</el-button>
          <el-button @click="handleReset">重置</el-button>
        </div>
      </section>

      <app-loading v-if="loading" />

      <section v-else class="goods-section">
        <div class="section-head">
          <div>
            <span class="section-kicker">CURATED FOR YOU</span>
            <h2>{{ selectedCategory || '本期精选' }}</h2>
            <p>真实库存与商户信息同步展示，选中喜欢的商品即可加入购物车。</p>
          </div>
          <div class="head-actions">
            <span class="goods-count">{{ displayedProducts.length }} 件商品</span>
            <el-button v-if="canShop" plain @click="$router.push('/cart')">购物车 · {{ cartCount }}</el-button>
          </div>
        </div>

        <div v-if="displayedProducts.length" class="goods-grid">
          <article class="goods-card" v-for="item in displayedProducts" :key="item.id">
            <div class="goods-cover">
              <span class="goods-badge" :class="{ soldout: Number(item.stock) <= 0 }">
                {{ Number(item.stock) > 0 ? '现货' : '缺货' }}
              </span>
              <el-carousel
                v-if="(item.image_urls || []).length"
                height="220px"
                indicator-position="none"
                :autoplay="false"
              >
                <el-carousel-item v-for="(img, index) in item.image_urls" :key="`${item.id}-img-${index}`">
                  <img :src="img" class="goods-cover-image" alt="product-image" />
                </el-carousel-item>
              </el-carousel>
              <video v-else-if="item.video_url" :src="item.video_url" class="goods-cover-video" controls></video>
              <div v-else class="cover-icon"><i class="el-icon-goods"></i></div>
            </div>
            <div class="goods-body">
              <div class="goods-meta">
                <span>{{ item.category || '品质精选' }}</span>
                <span>商户 {{ item.seller_id }}</span>
              </div>
              <h3>{{ item.name }}</h3>
              <p>{{ formatDescription(item.description) }}</p>
              <div class="goods-tags">
                <el-tag size="mini" v-if="item.category">{{ item.category }}</el-tag>
                <el-tag size="mini" type="success" v-if="(item.image_urls || []).length"
                  >{{ item.image_urls.length }} 张图</el-tag
                >
                <el-tag size="mini" type="warning" v-if="item.video_url">含视频</el-tag>
              </div>
              <div class="goods-footer">
                <div>
                  <strong>{{ formatPrice(item.price) }}</strong>
                  <span>库存 {{ item.stock }}</span>
                </div>
                <div class="goods-actions">
                  <el-button type="primary" plain size="mini" @click="openDetail(item)">查看详情</el-button>
                  <el-button
                    v-if="canShop"
                    type="primary"
                    size="mini"
                    :disabled="Number(item.stock) <= 0"
                    @click="handleQuickAddToCart(item)"
                  >
                    加入购物车
                  </el-button>
                </div>
              </div>
            </div>
          </article>
        </div>

        <div class="empty-wrap" v-else>
          <el-empty description="暂无匹配商品，换个关键词试试" />
        </div>
      </section>
    </main>

    <el-dialog title="商品详情" :visible.sync="detailVisible" width="820px">
      <div v-if="selectedProduct" class="detail-dialog">
        <div class="detail-media-grid">
          <el-carousel v-if="(selectedProduct.image_urls || []).length" height="360px" trigger="click">
            <el-carousel-item v-for="(img, index) in selectedProduct.image_urls" :key="`detail-${index}`">
              <div class="detail-image-wrap">
                <img :src="img" class="detail-image" alt="detail-image" />
              </div>
            </el-carousel-item>
          </el-carousel>
          <div v-if="selectedProduct.video_url" class="detail-video-wrap">
            <video :src="selectedProduct.video_url" class="detail-video" controls></video>
          </div>
          <el-empty
            v-if="!(selectedProduct.image_urls || []).length && !selectedProduct.video_url"
            description="该商品暂无媒体内容"
          />
        </div>
        <div class="detail-info">
          <div class="detail-head">
            <div>
              <h3>{{ selectedProduct.name }}</h3>
              <p class="detail-desc">{{ selectedProduct.description || '暂无商品介绍' }}</p>
            </div>
            <el-tag type="success">{{ selectedProduct.status === 'on_sale' ? '在售' : '已下架' }}</el-tag>
          </div>
          <div class="detail-meta-grid">
            <div class="meta-item">
              <span>商品ID</span><strong>{{ selectedProduct.id }}</strong>
            </div>
            <div class="meta-item">
              <span>卖家ID</span><strong>{{ selectedProduct.seller_id }}</strong>
            </div>
            <div class="meta-item">
              <span>分类</span><strong>{{ selectedProduct.category || '未分类' }}</strong>
            </div>
            <div class="meta-item">
              <span>库存</span><strong>{{ selectedProduct.stock }}</strong>
            </div>
          </div>
          <div class="detail-bottom">
            <strong class="detail-price">{{ formatPrice(selectedProduct.price) }}</strong>
            <div class="buy-bar">
              <el-input-number
                v-model="selectedQuantity"
                :min="1"
                :max="Math.max(1, Number(selectedProduct.stock || 1))"
              />
              <el-button
                v-if="canShop"
                type="primary"
                :disabled="Number(selectedProduct.stock) <= 0"
                @click="handleAddToCart(selectedProduct)"
              >
                加入购物车
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader'
import AppLoading from '@/components/AppLoading'
import { mapActions, mapState, mapGetters } from 'vuex'

export default {
  name: 'ProductHome',
  components: { CommonHeader, AppLoading },
  data() {
    return {
      loading: true,
      detailVisible: false,
      selectedProduct: null,
      selectedQuantity: 1,
      selectedCategory: '',
      searchParams: {
        product_id: '',
        name: ''
      }
    }
  },
  computed: {
    ...mapState('productModule', ['productList']),
    ...mapState('authModule', ['isAuthenticated']),
    ...mapGetters('authModule', ['userId', 'canManageProducts', 'canShop']),
    ...mapGetters('cartModule', ['cartCount']),
    inStockCount() {
      return this.productList.filter((item) => Number(item.stock) > 0).length
    },
    mediaCount() {
      return this.productList.filter((item) => (item.image_urls || []).length || item.video_url).length
    },
    categories() {
      return [...new Set(this.productList.map((item) => item.category).filter(Boolean))].slice(0, 7)
    },
    displayedProducts() {
      if (!this.selectedCategory) return this.productList
      return this.productList.filter((item) => item.category === this.selectedCategory)
    }
  },
  mounted() {
    this.fetchProductListData()
    if (this.isAuthenticated) {
      this.fetchCart().catch(() => {})
    }
  },
  methods: {
    ...mapActions('productModule', ['fetchProductList']),
    ...mapActions('cartModule', ['addToCart', 'fetchCart']),
    async fetchProductListData(params = {}) {
      this.loading = true
      try {
        await this.fetchProductList({ status: 'on_sale', ...params })
      } finally {
        this.loading = false
      }
    },
    async handleSearch() {
      const params = {
        product_id: this.searchParams.product_id || undefined,
        name: this.searchParams.name ? this.searchParams.name.trim() : undefined
      }
      await this.fetchProductListData(params)
    },
    handleReset() {
      this.searchParams = { product_id: '', name: '' }
      this.fetchProductListData()
    },
    openDetail(item) {
      this.selectedProduct = item
      this.selectedQuantity = 1
      this.detailVisible = true
    },
    async handleQuickAddToCart(item) {
      this.selectedProduct = item
      this.selectedQuantity = 1
      await this.handleAddToCart(item, false)
    },
    async handleAddToCart(item, closeAfterAdd = true) {
      if (!this.isAuthenticated || !this.canShop) {
        this.$message.warning(this.isAuthenticated ? '当前角色没有购物权限' : '加入购物车前请先完成安全登录')
        this.$router.push('/user-login')
        return
      }
      try {
        await this.addToCart({
          product_id: item.id,
          quantity: this.selectedQuantity
        })
        this.$message.success('已加入购物车')
        if (closeAfterAdd && this.detailVisible) {
          this.detailVisible = false
        }
      } catch (error) {
        // handled by interceptor
      }
    },
    formatPrice(price) {
      return `¥${Number(price || 0).toFixed(2)}`
    },
    formatDescription(text) {
      if (!text) return '暂无商品介绍'
      return text.length > 60 ? `${text.slice(0, 60)}...` : text
    },
    scrollToGoods() {
      if (this.$refs.goodsSection && this.$refs.goodsSection.scrollIntoView) {
        this.$refs.goodsSection.scrollIntoView({ behavior: 'smooth' })
      }
    }
  }
}
</script>

<style scoped lang="scss">
.home-main {
  max-width: 1280px;
}

.category-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 52px;
  overflow-x: auto;
  padding: 0 4px;

  button {
    flex-shrink: 0;
    border: 0;
    background: transparent;
    color: #4c5f6e;
    padding: 9px 13px;
    border-radius: 10px;
    cursor: pointer;
    font-size: 14px;
  }

  button:hover,
  button.active {
    color: #c2412d;
    background: #fff1ed;
  }
}

.category-promise {
  margin-left: auto;
  flex-shrink: 0;
  color: #177f6b;
  font-size: 13px;
}

.hero-section {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(300px, 0.7fr);
  gap: 16px;
  margin-bottom: 16px;
}

.hero-copy {
  padding: 44px;
  min-height: 390px;
  background: radial-gradient(circle at 82% 22%, rgba(249, 172, 95, 0.35), transparent 25%),
    linear-gradient(125deg, #fff8ef, #f9eee2 72%, #f3dac8);
  border: 1px solid #f2e1d4;
  position: relative;
  overflow: hidden;
}

.hero-copy h1 {
  margin: 15px 0;
  font-size: clamp(40px, 5vw, 62px);
  line-height: 1.08;
  letter-spacing: -2px;
  color: #28342e;

  em {
    color: #bd4b36;
    font-style: normal;
  }
}

.hero-copy p {
  color: #6b665d;
  line-height: 1.75;
  max-width: 600px;
}

.hero-tag {
  display: inline-block;
  background: #2f3e35;
  color: #fff7ea;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
}

.hero-actions {
  margin-top: 18px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-search {
  max-width: 610px;
  margin-top: 24px;
  display: flex;
  padding: 5px;
  border-radius: 15px;
  background: #fff;
  box-shadow: 0 12px 28px rgba(72, 48, 31, 0.12);

  ::v-deep .el-input__inner {
    border: 0;
    height: 44px;
  }

  .el-button {
    min-width: 92px;
    border-radius: 11px;
    background: #c14e38;
    border-color: #c14e38;
  }
}

.text-action {
  border: 0;
  background: transparent;
  padding: 0;
  color: #8b3f31;
  font-weight: 600;
  cursor: pointer;
}

.hero-panel {
  border-radius: 28px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #173d42;
  color: #fff;
}

.feature-visual {
  min-height: 290px;
  padding: 34px;
  flex: 1;
  background: radial-gradient(circle at 80% 25%, rgba(116, 211, 183, 0.4), transparent 24%),
    linear-gradient(145deg, #153b40, #1a5a58);

  .visual-kicker {
    display: block;
    color: #81dfc6;
    font-size: 11px;
    letter-spacing: 1.5px;
    margin-bottom: 18px;
  }

  > strong {
    display: block;
    font-size: 34px;
    margin-bottom: 10px;
  }

  p {
    color: rgba(255, 255, 255, 0.72);
    line-height: 1.7;
  }
}

.security-note {
  min-height: 100px;
  padding: 22px 26px;
  display: flex;
  align-items: center;
  gap: 14px;
  background: #102e33;

  > i {
    font-size: 29px;
    color: #74d3b7;
  }

  strong,
  span {
    display: block;
  }

  span {
    margin-top: 5px;
    color: rgba(255, 255, 255, 0.6);
    font-size: 12px;
  }
}

.service-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  border-radius: 18px;
  overflow: hidden;
  background: #e7e5df;
  border: 1px solid #e7e5df;
  margin-bottom: 22px;

  > div {
    padding: 17px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    background: #fff;
  }

  i {
    color: #b84a36;
    font-size: 24px;
  }

  strong,
  small {
    display: block;
  }

  strong {
    color: #273832;
    font-size: 14px;
  }

  small {
    margin-top: 3px;
    color: #8a938e;
  }
}

.search-section {
  padding: 18px 22px;
  margin-bottom: 20px;
}

.search-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.filter-label {
  color: #354a40;
  font-weight: 700;
  margin-right: 4px;
}

.search-input {
  width: 220px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.section-head h2 {
  margin: 0 0 8px;
  font-size: 28px;
  color: #111827;
}

.section-kicker {
  display: block;
  color: #b34b37;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.2px;
  margin-bottom: 7px;
}

.goods-count {
  color: #728078;
  font-size: 13px;
}

.section-head p {
  margin: 0;
  color: #6b7280;
}

.head-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.goods-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}

.goods-card {
  background: #fff;
  border-radius: 24px;
  overflow: hidden;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  border: 1px solid #edf0ed;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.goods-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 22px 48px rgba(38, 53, 47, 0.13);
}

.goods-cover {
  position: relative;
  height: 220px;
  background: #eef5ff;
}

.goods-badge {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 2;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.78);
  color: #fff;
  font-size: 12px;
}

.goods-badge.soldout {
  background: rgba(239, 68, 68, 0.86);
}

.goods-cover-image,
.goods-cover-video,
.detail-image,
.detail-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-icon {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 42px;
  color: #8ea8d2;
}

.goods-body {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.goods-meta {
  display: flex;
  justify-content: space-between;
  color: #94a3b8;
  font-size: 12px;
  gap: 8px;
}

.goods-body h3 {
  margin: 0;
  color: #111827;
  font-size: 20px;
}

.goods-body p {
  margin: 0;
  color: #6b7280;
  line-height: 1.7;
  min-height: 48px;
}

.goods-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.goods-footer {
  margin-top: auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.goods-footer strong,
.detail-price {
  display: block;
  font-size: 26px;
  color: #c44732;
}

.goods-footer span {
  color: #6b7280;
  font-size: 13px;
}

.goods-actions {
  display: flex;
  gap: 8px;
}

.detail-dialog {
  display: grid;
  gap: 20px;
}

.detail-media-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.detail-image-wrap,
.detail-video-wrap {
  border-radius: 18px;
  overflow: hidden;
  background: #edf4ff;
  min-height: 240px;
}

.detail-info {
  padding-top: 8px;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.detail-head h3 {
  margin: 0 0 8px;
  font-size: 28px;
}

.detail-desc {
  margin: 0;
  color: #6b7280;
  line-height: 1.8;
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin: 20px 0;
}

.meta-item {
  background: #f8fbff;
  border-radius: 18px;
  padding: 14px;
}

.meta-item span {
  display: block;
  color: #6b7280;
  font-size: 12px;
  margin-bottom: 6px;
}

.meta-item strong {
  color: #111827;
}

.detail-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.buy-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

@media screen and (max-width: 1024px) {
  .hero-section,
  .detail-media-grid,
  .detail-meta-grid {
    grid-template-columns: 1fr;
  }

  .service-strip {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media screen and (max-width: 768px) {
  .hero-copy,
  .search-section {
    padding: 22px;
  }

  .hero-copy h1 {
    font-size: 30px;
  }

  .search-input {
    width: 100%;
  }

  .hero-search,
  .service-strip {
    grid-template-columns: 1fr;
  }

  .hero-search {
    display: flex;
  }

  .section-head,
  .goods-footer,
  .detail-bottom,
  .detail-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
