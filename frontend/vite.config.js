import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    rollupOptions: {
      output: {
        // 供应商依赖拆独立 chunk：
        // - element-plus（含图标库，二者存在内部相互引用，须同 chunk 避免循环）
        //   体积大但极少变化，拆出后业务代码迭代不会改变其文件指纹，
        //   用户浏览器可长期命中缓存，不发请求；
        // - 多 chunk 并行下载，缩短首屏等待。
        // （总量不变；进一步压缩需改 unplugin 按需引入，回归面大暂不采用）
        manualChunks(id) {
          if (
            id.includes('node_modules/element-plus') ||
            id.includes('node_modules/@element-plus/icons-vue')
          ) return 'element-plus'
          if (id.includes('node_modules/marked') || id.includes('node_modules/dompurify')) return 'markdown-vendor'
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',      // 监听全部网卡，允许局域网访问
    port: 3000,
    allowedHosts: true,   // 开发环境放行ngrok随机域名，解决Blocked报错
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
