export const landingSeo = {
  siteUrl: "https://xiaoliuhua2.github.io/ravenholt/",
  siteName: "Ravenholt",
  title: "Ravenholt · 开源红队智能体协作平台",
  description:
    "Ravenholt 是面向授权安全工作的开源红队协作平台，提供多智能体编排、WorkProject 证据记录、本地沙箱执行、受控出口与可回放时间线。",
  imagePath: "assets/ravenholt-logo.svg",
  imageAlt: "Ravenholt Logo",
  keywords: [
    "Ravenholt",
    "红队协作平台",
    "多智能体红队平台",
    "授权渗透测试",
    "漏洞挖掘",
    "漏洞验证",
    "红队编排",
    "攻击路径分析",
    "攻击路径回放",
    "沙箱化安全工具",
    "受控出口",
    "代理出口",
    "证据记录",
    "资产关系图",
    "WorkProject 记录",
    "代码审计自动化",
    "源码安全审计",
    "依赖审查",
    "漏洞发现管理",
    "智能体编排",
    "逆向分析自动化",
    "密码学审查",
  ],
};

export const structuredData = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: landingSeo.siteName,
    applicationCategory: "SecurityApplication",
    operatingSystem: "Linux, Docker",
    url: landingSeo.siteUrl,
    image: new URL(landingSeo.imagePath, landingSeo.siteUrl).toString(),
    description: landingSeo.description,
    softwareRequirements: "Docker Engine、Docker Compose、PostgreSQL、模型供应商凭据",
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
    },
    sameAs: ["https://github.com/xiaoliuhua2/ravenholt"],
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "Ravenholt 是什么？",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Ravenholt 是面向授权渗透测试、漏洞挖掘、代码审计与安全研究的开源红队协作平台。",
        },
      },
      {
        "@type": "Question",
        name: "Ravenholt 面向哪些使用者？",
        acceptedAnswer: {
          "@type": "Answer",
          text: "面向获得授权的红队、渗透测试工程师、漏洞研究人员、企业内安全团队、代码审计人员、逆向工程师、密码学审查人员以及受控的研究环境。",
        },
      },
      {
        "@type": "Question",
        name: "Ravenholt 如何运行安全工具？",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Ravenholt 把智能体工具与人工审查流程绑定到可控的沙箱容器上，支持命令执行、文件访问、终端访问、浏览器流程与 noVNC 远程画面。",
        },
      },
      {
        "@type": "Question",
        name: "应该在什么环境中使用 Ravenholt？",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Ravenholt 只应在合法、明确授权、可信且隔离的环境中使用，并将 Docker 访问权限、模型凭据、终端访问与沙箱容器视为高权限资产进行管控。",
        },
      },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: "Ravenholt",
        item: landingSeo.siteUrl,
      },
    ],
  },
];

export function getRobotsTxt() {
  return [
    "User-agent: *",
    "Allow: /",
    "",
    `Sitemap: ${new URL("sitemap.xml", landingSeo.siteUrl).toString()}`,
    "",
  ].join("\n");
}

export function getSitemapXml() {
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    "  <url>",
    `    <loc>${landingSeo.siteUrl}</loc>`,
    "    <changefreq>weekly</changefreq>",
    "    <priority>1.0</priority>",
    "  </url>",
    "</urlset>",
    "",
  ].join("\n");
}

export function getWebManifest(iconSrc: string) {
  return JSON.stringify(
    {
      name: "Ravenholt",
      short_name: "Ravenholt",
      description: landingSeo.description,
      start_url: "/",
      display: "standalone",
      background_color: "#f7f8fa",
      theme_color: "#d92d3a",
      icons: [
        {
          src: iconSrc,
          sizes: "any",
          type: "image/svg+xml",
          purpose: "any",
        },
      ],
    },
    null,
    2,
  );
}
