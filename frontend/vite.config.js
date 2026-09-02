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
      // 注意 target 必须用 127.0.0.1 而非 localhost：
      // uvicorn 仅绑定 IPv4 127.0.0.1，本机 localhost 会优先解析到 ::1，
      // IPv6 环回连接会被静默丢弃、约 2 秒后才超时回退 IPv4，
      // 导致偶发"加载中卡 1-2 秒"（连接重建时命中该黑洞）
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
