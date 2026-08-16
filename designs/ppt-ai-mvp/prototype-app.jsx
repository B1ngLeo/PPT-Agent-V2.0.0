const {
  Topbar,
  ModeSegment,
  TemplateCard,
  Stepper,
  OutlineCard,
  SlideMini,
  HistoryDrawer,
  TemplateModal,
  Toast,
} = window;

const {
  templates: appTemplates,
  initialOutline: appInitialOutline,
  history: appHistory,
  modes: appModes,
  categories: appCategories,
} = window.PROTOTYPE_DATA;

function HomeScreen({
  prompt,
  setPrompt,
  attachment,
  setAttachment,
  mode,
  setMode,
  selectedTemplate,
  setSelectedTemplate,
  activeCategory,
  setActiveCategory,
  onCreate,
  onTemplate,
  onNotify,
}) {
  const filteredTemplates = activeCategory === "精品推荐"
    ? appTemplates
    : appTemplates.filter((template) => template.category === activeCategory);

  return (
    <main className="home" data-screen-label="首页">
      <section className="home-hero">
        <div className="hero-kicker">From source to native slides</div>
        <h1 className="hero-title">输入清晰的idea,<br /><em>获得即刻可用的PPT</em></h1>
        <p className="hero-sub">即刻AI-PPT会先确认目标、受众和大纲，再逐页生成可编辑的原生演示文稿。你随时可以修改、撤销或从历史恢复。</p>

        <section className="composer" aria-label="创建 PPT">
          <textarea
            aria-label="描述你想制作的演示文稿"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="例如：为董事会准备一份华东新能源业务增长策略，重点分析市场机会与未来90天行动"
          ></textarea>
          {attachment && (
            <div className="attachment-row">
              <span className="file-chip">DOC · {attachment}<button onClick={() => setAttachment("")} aria-label="移除附件">×</button></span>
            </div>
          )}
          <div className="composer-footer">
            <div className="composer-tools">
              <label className="upload-label" role="button" tabIndex="0">
                <span aria-hidden="true">＋</span> 添加文档
                <input
                  type="file"
                  accept=".doc,.docx,.pdf,.ppt,.pptx,.html,.md"
                  onChange={(event) => {
                    const fileName = event.target.files?.[0]?.name;
                    if (fileName) setAttachment(fileName);
                  }}
                />
              </label>
              <ModeSegment modes={appModes} value={mode} onChange={setMode} />
            </div>
            <button className="primary-btn" disabled={!prompt.trim() && !attachment} onClick={onCreate}>
              生成大纲 <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>

        <div className="quick-actions" aria-label="快捷创作入口">
          <button className="quick-card" onClick={() => onNotify("选择文档后，会进入同一套意图与大纲流程") }>
            <span className="quick-index">01</span>
            <span className="quick-copy"><strong>文档生成 PPT</strong><span>DOCX / PDF / PPTX / HTML，先解析再确认大纲</span></span>
          </button>
          <button className="quick-card" onClick={() => onNotify("旧 PPT 一键美化计划放在 P2，不纳入首版 MVP") }>
            <span className="quick-index">02</span>
            <span className="quick-copy"><strong>美化已有 PPT</strong><span>保留为下一阶段能力，避免首版范围过大</span></span>
          </button>
          <button className="quick-card" onClick={onTemplate}>
            <span className="quick-index">03</span>
            <span className="quick-copy"><strong>复用品牌模板</strong><span>解析封面、目录、章节、正文和结束页角色</span></span>
          </button>
        </div>
      </section>

      <section className="template-section" aria-labelledby="template-heading">
        <div className="section-head">
          <div>
            <div className="card-eyebrow">Template library</div>
            <h2 id="template-heading">选择一套表达系统</h2>
            <p>模板不只是一张封面，它定义字体、配色、页面角色与信息密度。</p>
          </div>
          <button className="ghost-btn" onClick={onTemplate}>＋ 上传我的模板</button>
        </div>
        <div className="filter-row" aria-label="模板分类">
          {appCategories.map((category) => (
            <button key={category} className={activeCategory === category ? "active" : ""} onClick={() => setActiveCategory(category)}>{category}</button>
          ))}
        </div>
        <div className="template-grid">
          {filteredTemplates.length > 0 ? filteredTemplates.map((template) => (
            <TemplateCard key={template.id} template={template} selected={selectedTemplate === template.id} onSelect={setSelectedTemplate} />
          )) : (
            <div className="intent-card">当前分类暂无模板，请切换分类或上传自定义模板。</div>
          )}
        </div>
      </section>
    </main>
  );
}

function WorkspaceScreen({
  prompt,
  attachment,
  intent,
  setIntent,
  outline,
  onOutlineChange,
  onOutlineMove,
  onOutlineDelete,
  onOutlineAdd,
  onBack,
  onGenerate,
  chatInput,
  setChatInput,
  chatMessages,
  onSendChat,
}) {
  return (
    <main className="workspace" data-screen-label="意图与大纲">
      <div className="workspace-top">
        <button className="ghost-btn back-btn" onClick={onBack}>← 返回</button>
        <div className="workspace-title">{intent.title || "未命名演示文稿"}</div>
        <div className="autosave"><span aria-hidden="true">●</span> 已自动保存</div>
      </div>
      <div className="workspace-body">
        <section className="work-main">
          <div className="work-column">
            <Stepper active={2} />
            <article className="story-card">
              <div className="card-eyebrow">Storyline</div>
              <div className="story-line">市场窗口 → 产品与渠道 → 九十天行动</div>
              <div className="story-note">递进式故事：先证明机会，再给出打法，最后落到资源与行动。</div>
            </article>

            <section className="intent-card" aria-labelledby="intent-heading">
              <div className="intent-head">
                <div><div className="card-eyebrow">Intent spec</div><h2 id="intent-heading">确认创作意图</h2></div>
                <span className="badge blue">AI 已根据输入补全</span>
              </div>
              <div className="intent-grid">
                <label className="field"><span>演示标题</span><input value={intent.title} onChange={(event) => setIntent({ ...intent, title: event.target.value })} /></label>
                <label className="field"><span>目标受众</span><select value={intent.audience} onChange={(event) => setIntent({ ...intent, audience: event.target.value })}><option>董事会 / 高管</option><option>业务团队</option><option>客户 / 合作伙伴</option><option>公开演讲</option></select></label>
                <label className="field"><span>建议页数</span><select value={intent.pages} onChange={(event) => setIntent({ ...intent, pages: event.target.value })}><option>8 页</option><option>12 页</option><option>16 页</option><option>智能适配</option></select></label>
                <label className="field"><span>制作目标</span><select value={intent.goal} onChange={(event) => setIntent({ ...intent, goal: event.target.value })}><option>策略决策</option><option>经营复盘</option><option>培训讲解</option><option>客户提案</option></select></label>
                <label className="field"><span>内容深度</span><select value={intent.depth} onChange={(event) => setIntent({ ...intent, depth: event.target.value })}><option>结论优先</option><option>平衡</option><option>研究型</option></select></label>
                <label className="field"><span>配图偏好</span><select value={intent.visual} onChange={(event) => setIntent({ ...intent, visual: event.target.value })}><option>数据图表优先</option><option>照片与插画</option><option>少配图</option></select></label>
              </div>
              <label className="field" style={{ marginTop: 12 }}><span>补充要求</span><textarea value={intent.notes} onChange={(event) => setIntent({ ...intent, notes: event.target.value })}></textarea></label>
              {(prompt || attachment) && <div className="inspector-note">来源：{attachment ? attachment : "主题描述"} · 原始要求已保留，可随时回看。</div>}
            </section>

            <section className="outline-section" aria-labelledby="outline-heading">
              <div className="outline-section-head">
                <div><div className="card-eyebrow">Editable outline</div><h2 id="outline-heading">逐页大纲 · {outline.length} 页</h2></div>
                <button className="ghost-btn" onClick={() => onSendChat("把大纲改得更适合高管阅读")}>让 AI 优化结构</button>
              </div>
              <div className="outline-list">
                {outline.map((item, index) => (
                  <OutlineCard key={item.id} item={item} index={index} total={outline.length} onChange={onOutlineChange} onMove={onOutlineMove} onDelete={onOutlineDelete} />
                ))}
                <button className="add-slide" onClick={onOutlineAdd}>＋ 添加一页</button>
              </div>
            </section>
          </div>
        </section>

        <aside className="assistant" aria-label="AI 创作助手">
          <div className="assistant-head">
            <div><h2>与 AI 一起创作</h2><p>修改会生成新版本，可撤销</p></div>
            <span className="badge green">在线</span>
          </div>
          <div className="assistant-feed" aria-live="polite">
            {chatMessages.map((message, index) => (
              <div key={index} className={`message ${message.role === "user" ? "user" : ""}`}>
                {message.role === "ai" && <div className="thinking">即刻AI-PPT · 已完成</div>}
                {message.text}
              </div>
            ))}
            <div className="suggestions">
              <button onClick={() => onSendChat("控制在 12 页")}>控制在 12 页</button>
              <button onClick={() => onSendChat("加强数据证据")}>加强数据证据</button>
              <button onClick={() => onSendChat("让结论更适合董事会")}>更适合董事会</button>
            </div>
          </div>
          <form className="chat-box" onSubmit={(event) => { event.preventDefault(); if (chatInput.trim()) onSendChat(chatInput); }}>
            <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="说出你想修改的地方" aria-label="输入创作要求" />
            <button aria-label="发送创作要求">↑</button>
          </form>
        </aside>
      </div>
      <div className="sticky-action">
        <div className="action-note">生成将固定当前意图与大纲版本，后续修改不会悄悄影响本次任务。</div>
        <button className="primary-btn" onClick={onGenerate}>确认大纲并开始生成 <span aria-hidden="true">→</span></button>
      </div>
    </main>
  );
}

function GeneratingScreen({
  outline,
  progress,
  cancelled,
  failedSlides,
  retryingSlides,
  onBack,
  onCancel,
  onResume,
  onRetry,
  onEditor,
}) {
  const getStatus = (index) => {
    if (retryingSlides.includes(index)) return "rendering";
    if (failedSlides.includes(index) && progress >= 70) return "failed";
    const threshold = ((index + 1) / outline.length) * 94;
    if (progress >= threshold + 2) return "ready";
    if (progress >= threshold - 2) return "qa";
    if (progress >= threshold - 7) return "rendering";
    if (progress >= threshold - 13) return "content";
    return "waiting";
  };
  const readyCount = outline.filter((_, index) => getStatus(index) === "ready").length;
  const displayProgress = Math.round(progress);
  const hasPartial = progress >= 94 && failedSlides.length > 0;

  return (
    <main className="generate-layout" data-screen-label="生成监控">
      <section className="generate-main">
        <div className="generate-head">
          <div>
            <button className="ghost-btn" onClick={onBack}>← 返回工作台</button>
            <h1>正在把大纲变成原生 PPT</h1>
            <p>{cancelled ? "任务已暂停，已完成页面会保留" : hasPartial ? "大部分页面已完成，1 页需要处理" : `已完成 ${readyCount}/${outline.length} 页；离开此页任务仍会继续`}</p>
          </div>
          <span className={`badge ${cancelled ? "red" : hasPartial ? "red" : "blue"}`}>{cancelled ? "已暂停" : hasPartial ? "部分完成" : "服务端任务运行中"}</span>
        </div>
        <div className="slide-grid">
          {outline.map((item, index) => (
            <SlideMini key={item.id} item={item} index={index} status={getStatus(index)} onRetry={onRetry} />
          ))}
        </div>
      </section>
      <aside className="progress-panel">
        <div className="card-eyebrow">Job progress</div>
        <h2>{hasPartial ? "等待处理失败页面" : cancelled ? "任务已暂停" : "逐页生成与质量检查"}</h2>
        <p>任务 ID · JOB-26A7 · 原生专业模式 · 经营信号模板</p>
        <div className="progress-ring" style={{ "--progress": `${displayProgress}%` }} role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={displayProgress}>
          <strong>{displayProgress}%</strong>
        </div>
        <div className="phase-list">
          <div className={`phase-row ${progress >= 26 ? "done" : "active"}`}><span className="phase-check">{progress >= 26 ? "✓" : "1"}</span><span>内容规划</span><small>{progress >= 26 ? "完成" : "进行中"}</small></div>
          <div className={`phase-row ${progress >= 76 ? "done" : progress >= 26 ? "active" : ""}`}><span className="phase-check">{progress >= 76 ? "✓" : "2"}</span><span>页面渲染</span><small>{progress >= 76 ? "完成" : progress >= 26 ? "进行中" : "等待"}</small></div>
          <div className={`phase-row ${progress >= 96 && failedSlides.length === 0 ? "done" : progress >= 70 ? "active" : ""}`}><span className="phase-check">{progress >= 96 && failedSlides.length === 0 ? "✓" : "3"}</span><span>质量检查</span><small>{progress >= 70 ? `${readyCount} 页通过` : "等待"}</small></div>
        </div>
        <div className="qa-summary">
          <strong>质量摘要</strong>
          <ul>
            <li>{readyCount} 页已通过版式与字体检查</li>
            <li>{Math.max(0, Math.min(3, Math.floor(progress / 28)))} 页已自动修复文本溢出</li>
            <li>{failedSlides.length} 页需要单独重试</li>
          </ul>
        </div>
        <div className="progress-actions">
          {cancelled ? (
            <button className="ghost-btn" onClick={onResume}>继续生成</button>
          ) : (
            <button className="ghost-btn danger-btn" onClick={onCancel}>暂停任务</button>
          )}
          <button className="primary-btn" disabled={progress < 92} onClick={onEditor}>{hasPartial ? "查看已完成结果" : "进入编辑"}</button>
        </div>
      </aside>
    </main>
  );
}

function EditorScreen({ outline, currentSlide, setCurrentSlide, onOutlineChange, onMove, onDelete, onBack, onNotify }) {
  const item = outline[currentSlide] || outline[0];
  return (
    <main className="editor-layout" data-screen-label="结果编辑与导出">
      <aside className="thumb-rail">
        <h2>Pages · {outline.length}</h2>
        <div className="thumb-list">
          {outline.map((slide, index) => (
            <button className={`thumb-btn ${currentSlide === index ? "active" : ""}`} key={slide.id} onClick={() => setCurrentSlide(index)}>
              <SlideMini item={slide} index={index} compact status="ready" />
              <span>第 {index + 1} 页 · {slide.type}</span>
            </button>
          ))}
        </div>
      </aside>
      <section className="editor-stage">
        <div className="editor-toolbar">
          <div className="tool-group">
            <button onClick={onBack}>← 返回生成</button>
            <button onClick={() => onMove(currentSlide, -1)} disabled={currentSlide === 0}>上移</button>
            <button onClick={() => onMove(currentSlide, 1)} disabled={currentSlide === outline.length - 1}>下移</button>
            <button onClick={() => { onDelete(item.id); setCurrentSlide(Math.max(0, currentSlide - 1)); }} disabled={outline.length <= 1}>删除</button>
          </div>
          <div className="tool-group">
            <button onClick={() => onNotify("已创建单页重生成任务，原页面会作为可恢复版本保留")}>单页重生成</button>
            <button className="primary-btn" onClick={() => onNotify("正在导出原生 PPTX；完成后将生成有时效下载链接")}>导出 PPTX</button>
          </div>
        </div>
        <div className="main-slide">
          <div className="slide-large-kicker">{item.type} · PAGE {String(currentSlide + 1).padStart(2, "0")}</div>
          <h1>{item.title}</h1>
          <p>{item.body}</p>
          <div className="big-number">{String(currentSlide + 1).padStart(2, "0")}</div>
        </div>
      </section>
      <aside className="editor-inspector">
        <h2>快速编辑</h2>
        <label className="field"><span>页面类型</span><select value={item.type} onChange={(event) => onOutlineChange(item.id, "type", event.target.value)}><option>封面</option><option>摘要</option><option>章节</option><option>数据</option><option>对比</option><option>方案</option><option>路径</option><option>计划</option><option>结束</option></select></label>
        <label className="field"><span>标题</span><textarea value={item.title} onChange={(event) => onOutlineChange(item.id, "title", event.target.value)}></textarea></label>
        <label className="field"><span>正文</span><textarea value={item.body} onChange={(event) => onOutlineChange(item.id, "body", event.target.value)}></textarea></label>
        <button className="soft-btn" onClick={() => onNotify("AI 建议：标题可以改为“增长不再只看装机规模”")}>让 AI 精炼本页</button>
        <div className="inspector-note">MVP 只提供文本、排序、删除与单页重生成。完整元素级画布编辑放在后续阶段，避免重做 PowerPoint。</div>
      </aside>
    </main>
  );
}

function App() {
  const [screen, setScreen] = React.useState("home");
  const [prompt, setPrompt] = React.useState("为董事会制作一份 2026 年华东新能源业务增长策略，重点分析市场机会、产品与渠道打法，以及未来 90 天行动计划。");
  const [attachment, setAttachment] = React.useState("");
  const [mode, setMode] = React.useState("native");
  const [selectedTemplate, setSelectedTemplate] = React.useState("signal");
  const [activeCategory, setActiveCategory] = React.useState("精品推荐");
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [templateOpen, setTemplateOpen] = React.useState(false);
  const [templatePhase, setTemplatePhase] = React.useState("idle");
  const [templateProgress, setTemplateProgress] = React.useState(0);
  const [templateFile, setTemplateFile] = React.useState("");
  const [templateMappings, setTemplateMappings] = React.useState(["封面", "目录", "章节", "正文", "结束"]);
  const [outline, setOutline] = React.useState(appInitialOutline.map((item) => ({ ...item })));
  const [intent, setIntent] = React.useState({
    title: "2026 新能源区域增长策略",
    audience: "董事会 / 高管",
    pages: "12 页",
    goal: "策略决策",
    depth: "结论优先",
    visual: "数据图表优先",
    notes: "避免空泛趋势；每个关键结论注明证据来源；结束页明确需要董事会确认的三项决策。",
  });
  const [chatInput, setChatInput] = React.useState("");
  const [chatMessages, setChatMessages] = React.useState([
    { role: "ai", text: "我已从你的主题中识别出“市场机会—打法—行动”的决策链，并把受众暂定为董事会。" },
    { role: "ai", text: "建议用 12 页完成：3 页证明窗口，4 页讲产品与渠道，3 页落到行动，其余用于开场和决策请求。" },
  ]);
  const [generationProgress, setGenerationProgress] = React.useState(0);
  const [failedSlides, setFailedSlides] = React.useState([7]);
  const [retryingSlides, setRetryingSlides] = React.useState([]);
  const [cancelled, setCancelled] = React.useState(false);
  const [currentSlide, setCurrentSlide] = React.useState(0);
  const [toast, setToast] = React.useState("");
  const toastTimer = React.useRef(null);

  const notify = React.useCallback((message) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 3200);
  }, []);

  React.useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  React.useEffect(() => {
    if (templatePhase !== "parsing") return undefined;
    const timer = window.setInterval(() => {
      setTemplateProgress((value) => {
        const next = Math.min(100, value + 8);
        if (next >= 100) {
          window.clearInterval(timer);
          window.setTimeout(() => setTemplatePhase("ready"), 220);
        }
        return next;
      });
    }, 180);
    return () => window.clearInterval(timer);
  }, [templatePhase]);

  React.useEffect(() => {
    if (screen !== "generating" || cancelled || generationProgress >= 96) return undefined;
    const timer = window.setInterval(() => {
      setGenerationProgress((value) => Math.min(96, value + 2.4));
    }, 260);
    return () => window.clearInterval(timer);
  }, [screen, cancelled, generationProgress]);

  React.useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        if (templateOpen) setTemplateOpen(false);
        else if (historyOpen) setHistoryOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [templateOpen, historyOpen]);

  const updateOutline = (id, key, value) => {
    setOutline((items) => items.map((item) => item.id === id ? { ...item, [key]: value } : item));
  };

  const moveOutline = (index, direction) => {
    setOutline((items) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= items.length) return items;
      const copy = [...items];
      [copy[index], copy[nextIndex]] = [copy[nextIndex], copy[index]];
      return copy;
    });
    setCurrentSlide((value) => Math.max(0, Math.min(outline.length - 1, value + direction)));
  };

  const deleteOutline = (id) => {
    if (outline.length <= 1) return;
    setOutline((items) => items.filter((item) => item.id !== id));
    notify("页面已移入可撤销记录");
  };

  const addOutline = () => {
    const nextId = Math.max(...outline.map((item) => item.id)) + 1;
    setOutline((items) => [...items, { id: nextId, type: "正文", title: "新页面标题", body: "补充这一页想表达的核心结论与证据。" }]);
    notify("已添加一页，大纲版本已更新");
  };

  const sendChat = (text) => {
    const clean = text.trim();
    if (!clean) return;
    setChatInput("");
    setChatMessages((messages) => [...messages, { role: "user", text: clean }]);
    if (clean.includes("12")) setIntent((value) => ({ ...value, pages: "12 页" }));
    window.setTimeout(() => {
      const reply = clean.includes("数据")
        ? "已把第 4、5、9 页调整为证据优先，并建议用市场容量矩阵和经营指标看板呈现。"
        : clean.includes("董事会") || clean.includes("高管")
          ? "已收紧铺垫：每一章先给结论，再展示证据；结束页会明确三项决策请求。"
          : "已基于当前意图生成一个新大纲版本。原版本仍可恢复，本次原型用提示表达版本机制。";
      setChatMessages((messages) => [...messages, { role: "ai", text: reply }]);
      notify("大纲已生成新版本，可继续编辑");
    }, 650);
  };

  const startTemplateUpload = (fileName) => {
    setTemplateFile(fileName || "品牌汇报模板.pptx");
    setTemplateProgress(0);
    setTemplatePhase("parsing");
  };

  const retrySlide = (index) => {
    if (retryingSlides.includes(index)) return;
    setRetryingSlides((items) => [...items, index]);
    notify(`第 ${index + 1} 页已进入单页重试队列`);
    window.setTimeout(() => {
      setFailedSlides((items) => items.filter((item) => item !== index));
      setRetryingSlides((items) => items.filter((item) => item !== index));
      setGenerationProgress(100);
      notify(`第 ${index + 1} 页已重新生成并通过质量检查`);
    }, 1400);
  };

  const createDraft = () => {
    setScreen("workspace");
    window.scrollTo(0, 0);
    notify("草稿已创建，正在显示可编辑意图与大纲");
  };

  const startGeneration = () => {
    setGenerationProgress(0);
    setFailedSlides([7]);
    setRetryingSlides([]);
    setCancelled(false);
    setScreen("generating");
    window.scrollTo(0, 0);
  };

  const openHistoryItem = (item) => {
    setHistoryOpen(false);
    if (item.status === "已完成") setScreen("editor");
    else if (item.status === "生成中" || item.status === "需处理") setScreen("generating");
    else setScreen("workspace");
    window.scrollTo(0, 0);
  };

  const saveTemplate = () => {
    setTemplateOpen(false);
    setSelectedTemplate("custom");
    setMode("template");
    notify("模板已保存为私有模板，并绑定到当前草稿");
  };

  return (
    <div className="app">
      <Topbar
        screen={screen}
        onHome={() => { setScreen("home"); window.scrollTo(0, 0); }}
        onHistory={() => setHistoryOpen(true)}
        onTemplate={() => setTemplateOpen(true)}
      />

      {screen === "home" && (
        <HomeScreen
          prompt={prompt}
          setPrompt={setPrompt}
          attachment={attachment}
          setAttachment={setAttachment}
          mode={mode}
          setMode={setMode}
          selectedTemplate={selectedTemplate}
          setSelectedTemplate={setSelectedTemplate}
          activeCategory={activeCategory}
          setActiveCategory={setActiveCategory}
          onCreate={createDraft}
          onTemplate={() => setTemplateOpen(true)}
          onNotify={notify}
        />
      )}

      {screen === "workspace" && (
        <WorkspaceScreen
          prompt={prompt}
          attachment={attachment}
          intent={intent}
          setIntent={setIntent}
          outline={outline}
          onOutlineChange={updateOutline}
          onOutlineMove={moveOutline}
          onOutlineDelete={deleteOutline}
          onOutlineAdd={addOutline}
          onBack={() => { setScreen("home"); window.scrollTo(0, 0); }}
          onGenerate={startGeneration}
          chatInput={chatInput}
          setChatInput={setChatInput}
          chatMessages={chatMessages}
          onSendChat={sendChat}
        />
      )}

      {screen === "generating" && (
        <GeneratingScreen
          outline={outline}
          progress={generationProgress}
          cancelled={cancelled}
          failedSlides={failedSlides}
          retryingSlides={retryingSlides}
          onBack={() => { setScreen("workspace"); window.scrollTo(0, 0); }}
          onCancel={() => { setCancelled(true); notify("已提交暂停请求；当前页面完成后安全停止"); }}
          onResume={() => { setCancelled(false); notify("任务已恢复，将从上一个检查点继续"); }}
          onRetry={retrySlide}
          onEditor={() => { setCurrentSlide(0); setScreen("editor"); window.scrollTo(0, 0); }}
        />
      )}

      {screen === "editor" && (
        <EditorScreen
          outline={outline}
          currentSlide={currentSlide}
          setCurrentSlide={setCurrentSlide}
          onOutlineChange={updateOutline}
          onMove={moveOutline}
          onDelete={deleteOutline}
          onBack={() => { setScreen("generating"); window.scrollTo(0, 0); }}
          onNotify={notify}
        />
      )}

      <HistoryDrawer open={historyOpen} items={appHistory} onClose={() => setHistoryOpen(false)} onOpenItem={openHistoryItem} />
      <TemplateModal
        open={templateOpen}
        onClose={() => setTemplateOpen(false)}
        phase={templatePhase}
        progress={templateProgress}
        fileName={templateFile}
        mappings={templateMappings}
        onStartUpload={startTemplateUpload}
        onMappingChange={(index, value) => setTemplateMappings((items) => items.map((item, itemIndex) => itemIndex === index ? value : item))}
        onSave={saveTemplate}
      />
      <Toast message={toast} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
