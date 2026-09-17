<template>
  <div class="page-shell seller-page">
    <common-header />

    <main class="dashboard-main page-main">
      <section class="dashboard-head section-card">
        <div>
          <h1>我的商品中心</h1>
          <p>对齐后端 seller_id 逻辑：你只能查看、编辑和上下架自己的商品。</p>
        </div>
        <div class="head-actions">
          <el-tag type="success">卖家视图</el-tag>
          <el-button type="primary" round icon="el-icon-plus" @click="handleAddProduct">发布商品</el-button>
        </div>
      </section>

      <section class="summary-grid">
        <div class="summary-card section-card">
          <span>我的商品总数</span>
          <strong>{{ productList.length }}</strong>
        </div>
        <div class="summary-card section-card">
          <span>在售商品</span>
          <strong>{{ onSaleCount }}</strong>
        </div>
        <div class="summary-card section-card">
          <span>已下架</span>
          <strong>{{ offShelfCount }}</strong>
        </div>
        <div class="summary-card section-card">
          <span>总库存</span>
          <strong>{{ totalStock }}</strong>
        </div>
      </section>

      <section class="toolbar-card section-card">
        <div class="toolbar-row">
          <el-input v-model="searchParams.product_id" placeholder="输入商品ID" class="search-input" clearable />
          <el-input v-model="searchParams.name" placeholder="输入商品名称" class="search-input" clearable />
          <el-select v-model="searchParams.status" clearable class="search-input" placeholder="商品状态">
            <el-option label="在售" value="on_sale" />
            <el-option label="已下架" value="off_shelf" />
          </el-select>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </div>
      </section>

      <app-loading v-if="loading" />

      <section v-else class="table-card section-card">
        <el-table :data="productList" border stripe style="width: 100%">
          <el-table-column label="商品ID" prop="id" width="90" align="center" />
          <el-table-column label="商品名称" prop="name" min-width="180" />
          <el-table-column label="分类" prop="category" min-width="120" />
          <el-table-column label="状态" width="110" align="center">
            <template slot-scope="scope">
              <el-tag :type="scope.row.status === 'on_sale' ? 'success' : 'info'">
                {{ scope.row.status === 'on_sale' ? '在售' : '已下架' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="价格（元）" width="120" align="center">
            <template slot-scope="scope">{{ formatPrice(scope.row.price) }}</template>
          </el-table-column>
          <el-table-column label="库存" prop="stock" width="100" align="center" />
          <el-table-column label="封面" width="120" align="center">
            <template slot-scope="scope">
              <div class="table-media-wrap">
                <el-image
                  v-if="getCoverImage(scope.row)"
                  :src="getCoverImage(scope.row)"
                  fit="cover"
                  class="table-image-preview"
                  :preview-src-list="scope.row.image_urls || []"
                />
                <span v-else class="table-media-empty">无媒体</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" min-width="170">
            <template slot-scope="scope">{{ formatTime(scope.row.updated_at || scope.row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="240" align="center">
            <template slot-scope="scope">
              <el-button type="text" @click="handleEditProduct(scope.row)">编辑</el-button>
              <el-button type="text" @click="handleViewProduct(scope.row)">详情</el-button>
              <el-button
                type="text"
                :style="{ color: scope.row.status === 'on_sale' ? '#ef4444' : '#10b981' }"
                @click="handleToggleStatus(scope.row)"
              >
                {{ scope.row.status === 'on_sale' ? '下架' : '重新上架' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="empty-wrap" v-if="!productList.length">
          <el-empty description="当前还没有自己的商品，点击上方按钮发布第一个商品吧" />
        </div>
      </section>
    </main>

    <el-dialog
      :title="isEdit ? '编辑商品' : '发布商品'"
      :visible.sync="dialogVisible"
      width="820px"
      @closed="resetFormState"
    >
      <el-form ref="formRef" :model="formData" :rules="formRules" label-width="90px">
        <el-form-item label="商品名称" prop="name">
          <el-input v-model="formData.name" />
        </el-form-item>
        <el-form-item label="商品分类" prop="category">
          <el-input v-model="formData.category" placeholder="例如：电子产品 / 图书 / 食品" />
        </el-form-item>
        <el-form-item label="商品介绍" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="4" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="价格" prop="price">
              <el-input v-model.number="formData.price" type="number" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="库存" prop="stock">
              <el-input v-model.number="formData.stock" type="number" min="0" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item v-if="isEdit" label="状态" prop="status">
          <el-radio-group v-model="formData.status">
            <el-radio-button label="on_sale">在售</el-radio-button>
            <el-radio-button label="off_shelf">下架</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="商品图片">
          <input ref="imageInput" type="file" accept="image/*" multiple @change="handleImagesChange" />
          <div class="upload-tip">最多 6 张，支持 jpg / jpeg / png / gif / webp。重新选择会替换原图片组。</div>

          <div v-if="selectedImagePreviews.length" class="preview-grid">
            <div v-for="(src, index) in selectedImagePreviews" :key="`new-${index}`" class="preview-card">
              <img :src="src" alt="preview" />
              <span class="preview-badge">新图片 {{ index + 1 }}</span>
            </div>
          </div>

          <div v-else-if="formData.image_urls.length" class="preview-grid">
            <div v-for="(src, index) in formData.image_urls" :key="`old-${index}`" class="preview-card">
              <img :src="src" alt="old-preview" />
              <span class="preview-badge">原图片 {{ index + 1 }}</span>
            </div>
          </div>

          <el-checkbox
            v-if="isEdit && formData.image_urls.length && !selectedImagePreviews.length"
            v-model="formData.remove_all_images"
          >
            删除原图片组
          </el-checkbox>
        </el-form-item>

        <el-form-item label="商品视频">
          <input ref="videoInput" type="file" accept="video/*" @change="handleVideoChange" />
          <div class="upload-tip">支持 mp4 / webm / ogg / mov。重新选择会替换原视频。</div>
          <div v-if="selectedVideoPreview || formData.video_url" class="video-preview-wrap">
            <video :src="selectedVideoPreview || formData.video_url" class="dialog-video-preview" controls></video>
          </div>
          <el-checkbox v-if="isEdit && formData.video_url && !selectedVideoPreview" v-model="formData.remove_video">
            删除原视频
          </el-checkbox>
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitForm">保存</el-button>
      </span>
    </el-dialog>

    <el-dialog title="商品详情" :visible.sync="detailVisible" width="760px">
      <div v-if="selectedProduct" class="detail-panel">
        <div class="detail-preview-grid">
          <el-carousel v-if="(selectedProduct.image_urls || []).length" height="320px" :autoplay="false">
            <el-carousel-item v-for="(img, index) in selectedProduct.image_urls" :key="`detail-img-${index}`">
              <img :src="img" class="dialog-image" alt="detail-image" />
            </el-carousel-item>
          </el-carousel>
          <video
            v-if="selectedProduct.video_url"
            :src="selectedProduct.video_url"
            class="dialog-video-preview"
            controls
          ></video>
        </div>
        <div class="detail-rows">
          <div>
            <span>商品名称</span><strong>{{ selectedProduct.name }}</strong>
          </div>
          <div>
            <span>分类</span><strong>{{ selectedProduct.category || '未分类' }}</strong>
          </div>
          <div>
            <span>价格</span><strong>{{ formatPrice(selectedProduct.price) }}</strong>
          </div>
          <div>
            <span>库存</span><strong>{{ selectedProduct.stock }}</strong>
          </div>
          <div>
            <span>状态</span><strong>{{ selectedProduct.status === 'on_sale' ? '在售' : '已下架' }}</strong>
          </div>
        </div>
        <p class="detail-description">{{ selectedProduct.description || '暂无商品介绍' }}</p>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import CommonHeader from '@/components/CommonHeader'
import AppLoading from '@/components/AppLoading'
import { mapActions, mapState } from 'vuex'

const createDefaultForm = () => ({
  id: null,
  name: '',
  category: '',
  description: '',
  price: 0,
  stock: 0,
  status: 'on_sale',
  image_urls: [],
  video_url: '',
  remove_all_images: false,
  remove_video: false
})

export default {
  name: 'ProductList',
  components: { CommonHeader, AppLoading },
  data() {
    return {
      loading: true,
      dialogVisible: false,
      detailVisible: false,
      isEdit: false,
      searchParams: {
        product_id: '',
        name: '',
        status: ''
      },
      formData: createDefaultForm(),
      selectedProduct: null,
      selectedImageFiles: [],
      selectedImagePreviews: [],
      selectedVideoFile: null,
      selectedVideoPreview: '',
      formRules: {
        name: [{ required: true, message: '请输入商品名称', trigger: 'blur' }],
        price: [
          { required: true, message: '请输入商品价格', trigger: 'blur' },
          {
            validator: (rule, value, callback) => {
              if (Number(value) <= 0) {
                callback(new Error('价格必须大于0'))
                return
              }
              callback()
            },
            trigger: 'blur'
          }
        ],
        stock: [
          { required: true, message: '请输入库存数量', trigger: 'blur' },
          {
            validator: (rule, value, callback) => {
              if (Number(value) < 0) {
                callback(new Error('库存不能小于0'))
                return
              }
              callback()
            },
            trigger: 'blur'
          }
        ]
      }
    }
  },
  computed: {
    ...mapState('productModule', ['productList', 'currentProduct']),
    onSaleCount() {
      return this.productList.filter((item) => item.status === 'on_sale').length
    },
    offShelfCount() {
      return this.productList.filter((item) => item.status === 'off_shelf').length
    },
    totalStock() {
      return this.productList.reduce((total, item) => total + Number(item.stock || 0), 0)
    }
  },
  mounted() {
    this.fetchProductListData()
  },
  methods: {
    ...mapActions('productModule', [
      'fetchProductList',
      'addProduct',
      'updateProduct',
      'deleteProduct',
      'fetchProductDetail'
    ]),
    async fetchProductListData(params = {}) {
      this.loading = true
      try {
        await this.fetchProductList({ mine: true, ...params })
      } finally {
        this.loading = false
      }
    },
    async handleSearch() {
      await this.fetchProductListData({
        product_id: this.searchParams.product_id || undefined,
        name: this.searchParams.name || undefined,
        status: this.searchParams.status || undefined
      })
    },
    handleReset() {
      this.searchParams = { product_id: '', name: '', status: '' }
      this.fetchProductListData()
    },
    getCoverImage(product) {
      return (product.image_urls && product.image_urls[0]) || product.image_url || ''
    },
    handleAddProduct() {
      this.isEdit = false
      this.dialogVisible = true
      this.formData = createDefaultForm()
    },
    async handleEditProduct(product) {
      this.isEdit = true
      this.dialogVisible = true
      await this.fetchProductDetail(product.id)
      this.formData = {
        id: this.currentProduct.id,
        name: this.currentProduct.name,
        category: this.currentProduct.category || '',
        description: this.currentProduct.description || '',
        price: Number(this.currentProduct.price),
        stock: Number(this.currentProduct.stock),
        status: this.currentProduct.status,
        image_urls: this.currentProduct.image_urls || [],
        video_url: this.currentProduct.video_url || '',
        remove_all_images: false,
        remove_video: false
      }
    },
    async handleViewProduct(product) {
      await this.fetchProductDetail(product.id)
      this.selectedProduct = this.currentProduct
      this.detailVisible = true
    },
    clearImagePreviews() {
      this.selectedImagePreviews.forEach((src) => URL.revokeObjectURL(src))
      this.selectedImagePreviews = []
    },
    handleImagesChange(event) {
      const files = Array.from((event.target && event.target.files) || [])
      if (files.length > 6) {
        this.$message.error('最多只能选择 6 张图片')
        event.target.value = ''
        return
      }
      this.clearImagePreviews()
      this.selectedImageFiles = files
      this.formData.remove_all_images = false
      this.selectedImagePreviews = files.map((file) => URL.createObjectURL(file))
    },
    handleVideoChange(event) {
      const file = event.target.files && event.target.files[0]
      this.selectedVideoFile = file || null
      this.formData.remove_video = false
      if (this.selectedVideoPreview) {
        URL.revokeObjectURL(this.selectedVideoPreview)
        this.selectedVideoPreview = ''
      }
      if (file) {
        this.selectedVideoPreview = URL.createObjectURL(file)
      }
    },
    buildFormData() {
      const formData = new FormData()
      formData.append('name', this.formData.name)
      formData.append('category', this.formData.category || '')
      formData.append('description', this.formData.description || '')
      formData.append('price', this.formData.price)
      formData.append('stock', this.formData.stock)
      formData.append('status', this.formData.status || 'on_sale')
      formData.append('remove_all_images', this.formData.remove_all_images ? 'true' : 'false')
      formData.append('remove_video', this.formData.remove_video ? 'true' : 'false')
      this.selectedImageFiles.forEach((file) => {
        formData.append('images', file)
      })
      if (this.selectedVideoFile) {
        formData.append('video', this.selectedVideoFile)
      }
      return formData
    },
    handleSubmitForm() {
      this.$refs.formRef.validate(async (valid) => {
        if (!valid) return
        try {
          const payload = this.buildFormData()
          if (this.isEdit) {
            await this.updateProduct({
              productId: this.formData.id,
              productData: payload
            })
            this.$message.success('商品更新成功')
          } else {
            await this.addProduct(payload)
            this.$message.success('商品发布成功')
          }
          this.dialogVisible = false
          this.fetchProductListData({ status: this.searchParams.status || undefined })
        } catch (error) {
          // handled by interceptor
        }
      })
    },
    async handleToggleStatus(product) {
      try {
        if (product.status === 'on_sale') {
          await this.$confirm('确定要下架该商品吗？', '下架商品', {
            confirmButtonText: '下架',
            cancelButtonText: '取消',
            type: 'warning'
          })
          await this.deleteProduct(product.id)
          this.$message.success('商品已下架')
        } else {
          const payload = new FormData()
          payload.append('status', 'on_sale')
          await this.updateProduct({ productId: product.id, productData: payload })
          this.$message.success('商品已重新上架')
        }
        this.fetchProductListData({ status: this.searchParams.status || undefined })
      } catch (error) {
        if (error !== 'cancel' && error.message !== 'cancel') {
          // handled by interceptor
        }
      }
    },
    resetFormState() {
      this.formData = createDefaultForm()
      this.selectedImageFiles = []
      this.clearImagePreviews()
      this.selectedVideoFile = null
      if (this.selectedVideoPreview) {
        URL.revokeObjectURL(this.selectedVideoPreview)
        this.selectedVideoPreview = ''
      }
      if (this.$refs.imageInput) this.$refs.imageInput.value = ''
      if (this.$refs.videoInput) this.$refs.videoInput.value = ''
    },
    formatPrice(price) {
      return `¥${Number(price || 0).toFixed(2)}`
    },
    formatTime(timeStr) {
      if (!timeStr) return '--'
      return new Date(timeStr).toLocaleString('zh-CN', { hour12: false })
    }
  }
}
</script>

<style scoped lang="scss">
.dashboard-head,
.toolbar-card,
.table-card {
  padding: 24px;
}

.dashboard-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.dashboard-head h1 {
  margin: 0 0 10px;
  font-size: 30px;
  color: #111827;
}

.dashboard-head p {
  margin: 0;
  color: #6b7280;
}

.head-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 18px;
}

.summary-card {
  padding: 24px;
}

.summary-card span {
  display: block;
  color: #6b7280;
  margin-bottom: 8px;
}

.summary-card strong {
  font-size: 28px;
  color: #111827;
}

.toolbar-card {
  margin-bottom: 18px;
}

.toolbar-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.search-input {
  width: 220px;
}

.table-media-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
}

.table-image-preview {
  width: 88px;
  height: 88px;
  border-radius: 12px;
  object-fit: cover;
  overflow: hidden;
}

.table-media-empty {
  color: #9ca3af;
  font-size: 12px;
}

.upload-tip {
  margin-top: 6px;
  color: #6b7280;
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.preview-card {
  position: relative;
  border-radius: 16px;
  overflow: hidden;
  height: 96px;
}

.preview-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-badge {
  position: absolute;
  left: 8px;
  bottom: 8px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(17, 24, 39, 0.76);
  color: #fff;
  font-size: 12px;
}

.video-preview-wrap,
.detail-preview-grid {
  margin-top: 12px;
}

.dialog-video-preview,
.dialog-image {
  width: 100%;
  border-radius: 16px;
  object-fit: cover;
}

.detail-panel {
  display: grid;
  gap: 18px;
}

.detail-preview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.detail-rows {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.detail-rows div {
  background: #f8fbff;
  border-radius: 16px;
  padding: 14px;
}

.detail-rows span {
  display: block;
  color: #6b7280;
  font-size: 12px;
  margin-bottom: 6px;
}

.detail-rows strong {
  color: #111827;
}

.detail-description {
  margin: 0;
  color: #6b7280;
  line-height: 1.8;
}

@media screen and (max-width: 1024px) {
  .summary-grid,
  .detail-preview-grid,
  .detail-rows {
    grid-template-columns: 1fr 1fr;
  }
}

@media screen and (max-width: 768px) {
  .dashboard-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .summary-grid,
  .detail-preview-grid,
  .detail-rows {
    grid-template-columns: 1fr;
  }

  .search-input {
    width: 100%;
  }
}
</style>
