import { defineConfig } from 'vitepress'

const base = '/ravenholt/'

const enNav = [
  { text: 'Home', link: '/en/' },
  { text: 'Quick Start', link: '/en/guide/quick-start' },
  { text: 'Join Community', link: '/en/guide/community' }
]

const zhNav = [
  { text: '首页', link: '/zh/' },
  { text: '快速开始', link: '/zh/guide/quick-start' },
  { text: '组建社群', link: '/zh/guide/community' }
]

const enSidebar = {
  '/en/guide/': [
    {
      text: 'Guide',
      items: [
        { text: 'Overview', link: '/en/guide/overview' },
        { text: 'Quick Start', link: '/en/guide/quick-start' },
        { text: 'First Use', link: '/en/guide/first-use' },
        { text: 'Join Community', link: '/en/guide/community' }
      ]
    }
  ]
}

const zhSidebar = {
  '/zh/guide/': [
    {
      text: '说明文档',
      items: [
        { text: '概览', link: '/zh/guide/overview' },
        { text: '快速开始', link: '/zh/guide/quick-start' },
        { text: '首次使用', link: '/zh/guide/first-use' },
        { text: '组建社群', link: '/zh/guide/community' }
      ]
    }
  ]
}

export default defineConfig({
  base,
  title: 'Ravenholt 文档',
  description: '面向授权渗透测试与漏洞挖掘的多智能体协作平台，提供专家智能体、沙箱工具链、证据记录与可回放时间线。',
  appearance: 'force-dark',
  lastUpdated: true,
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: `${base}ravenholt-logo-light.svg` }],
    ['link', { rel: 'apple-touch-icon', href: `${base}ravenholt-logo.png` }]
  ],
  markdown: {
    config(md) {
      const fence = md.renderer.rules.fence
      md.renderer.rules.fence = (tokens, idx, options, env, self) => {
        const token = tokens[idx]
        const lang = token.info.trim().split(/\s+/)[0]
        if (lang === 'mermaid') {
          return `<MermaidDiagram code="${encodeURIComponent(token.content)}" />`
        }
        return fence ? fence(tokens, idx, options, env, self) : self.renderToken(tokens, idx, options)
      }
    }
  },
  themeConfig: {
    logo: '/ravenholt-logo-light.svg',
    outline: { level: [2, 3], label: 'On this page' },
    socialLinks: [{ icon: 'github', link: 'https://github.com/xiaoliuhua2/ravenholt' }]
  },
  locales: {
    en: {
      label: 'English',
      lang: 'en-US',
      link: '/en/',
      themeConfig: {
        nav: enNav,
        sidebar: enSidebar,
        outline: { level: [2, 3], label: 'Contents' }
      }
    },
    zh: {
      label: '简体中文',
      lang: 'zh-CN',
      link: '/zh/',
      themeConfig: {
        nav: zhNav,
        sidebar: zhSidebar,
        outline: { level: [2, 3], label: '目录' }
      }
    }
  }
})
