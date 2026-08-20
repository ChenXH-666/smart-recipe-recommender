import { defineStore } from 'pinia'

/**
 * AI 对话抽屉全局状态
 * ====================
 * 让「AI 对话记录」页面的"继续对话"能打开抽屉并载入指定历史会话，
 * 也让导航栏悬浮按钮打开抽屉时自动续接最近一次对话。
 * 由 MainLayout 中的 AiChatDialog 消费 visible / openConversationId。
 */
export const useAiChatStore = defineStore('aiChat', {
  state: () => ({
    visible: false,
    // 待抽屉打开时载入的历史会话 ID（为 null 表示新建/自动续接最近会话）
    openConversationId: null,
  }),
  actions: {
    /** 打开 AI 抽屉；传入 conversationId 则载入指定历史会话 */
    open(conversationId = null) {
      this.openConversationId = conversationId
      this.visible = true
    },
    close() {
      this.visible = false
      // 不清空 openConversationId，由 AiChatDialog 载入后消费，避免重复触发
    },
    /** 取出并清空待载入的会话 ID（AiChatDialog 打开时调用一次） */
    consumeConversationId() {
      const id = this.openConversationId
      this.openConversationId = null
      return id
    },
  },
})