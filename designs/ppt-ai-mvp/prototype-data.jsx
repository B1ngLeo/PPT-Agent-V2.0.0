const prototypeTemplates = [
  { id: "signal", name: "经营信号", category: "总结汇报", tone: "blue", description: "数据复盘 · 18页 · 原生图表" },
  { id: "field", name: "城市田野", category: "企业宣讲", tone: "paper", description: "品牌叙事 · 14页 · 编辑友好" },
  { id: "night", name: "深夜策略室", category: "商业计划", tone: "ink", description: "高管汇报 · 16页 · 强对比" },
  { id: "pulse", name: "增长脉冲", category: "营销推广", tone: "coral", description: "增长提案 · 12页 · 轻量图形" },
  { id: "clear", name: "清洁能源", category: "教育培训", tone: "mint", description: "知识讲解 · 20页 · 信息图" },
  { id: "harbor", name: "港口观察", category: "竞政民生", tone: "slate", description: "研究报告 · 22页 · 图文混排" },
];

const prototypeInitialOutline = [
  { id: 1, type: "封面", title: "2026 新能源区域增长策略", body: "从装机规模走向高质量增长：华东市场机会、产品组合与行动路线。" },
  { id: 2, type: "摘要", title: "一页读懂：增长来自三个结构性机会", body: "工商业储能放量；渠道下沉；存量客户的运维与升级需求。" },
  { id: 3, type: "章节", title: "01 / 市场窗口", body: "用需求、政策与竞争三组证据定义当下窗口期。" },
  { id: 4, type: "数据", title: "新增需求正在从单一装机转向系统价值", body: "拆解光伏、储能、能管平台的增长贡献和客户决策变化。" },
  { id: 5, type: "对比", title: "华东六省机会并不均匀", body: "按市场容量、进入难度和毛利潜力建立优先级矩阵。" },
  { id: 6, type: "章节", title: "02 / 产品与渠道", body: "从产品清单转向场景化解决方案。" },
  { id: 7, type: "方案", title: "三条产品线对应三类核心客户", body: "园区、连锁商业与高耗能制造，分别定义主张、配置和收益模型。" },
  { id: 8, type: "路径", title: "渠道模型：伙伴覆盖与直销突破并行", body: "明确伙伴分层、赋能机制和重点客户直销边界。" },
  { id: 9, type: "指标", title: "从签约额转向可复利的经营指标", body: "线索转化、交付周期、软件附着率、续费与推荐率。" },
  { id: 10, type: "章节", title: "03 / 九十天行动", body: "把策略压缩成可交付的季度作战地图。" },
  { id: 11, type: "计划", title: "未来 90 天：验证、复制、放大", body: "三个波次、六项负责人明确的关键动作。" },
  { id: 12, type: "结束", title: "让每一度电，产生更高价值", body: "决策请求：确认试点区域、资源投入与阶段性目标。" },
];

const prototypeHistory = [
  { id: "h1", title: "2026 新能源区域增长策略", status: "生成中", tone: "blue", meta: "12 页 · 原生专业 · 2 分钟前" },
  { id: "h2", title: "二季度经营复盘与行动计划", status: "已完成", tone: "green", meta: "18 页 · 经营信号 · 今天 09:42" },
  { id: "h3", title: "工业园区零碳解决方案", status: "草稿", tone: "", meta: "大纲 9 页 · 昨天 18:20" },
  { id: "h4", title: "渠道伙伴大会开场演讲", status: "需处理", tone: "red", meta: "第 7 页生成失败 · 8 月 12 日" },
];

const prototypeModes = [
  { id: "native", label: "原生专业", note: "可编辑对象优先" },
  { id: "visual", label: "视觉创意", note: "强视觉表达" },
  { id: "template", label: "模板复用", note: "严格跟随模板" },
];

const prototypeCategories = ["精品推荐", "总结汇报", "教育培训", "营销推广", "企业宣讲", "商业计划", "竞政民生"];

Object.assign(window, {
  PROTOTYPE_DATA: {
    templates: prototypeTemplates,
    initialOutline: prototypeInitialOutline,
    history: prototypeHistory,
    modes: prototypeModes,
    categories: prototypeCategories,
  },
});
