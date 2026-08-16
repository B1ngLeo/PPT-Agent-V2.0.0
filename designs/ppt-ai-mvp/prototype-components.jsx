function Brand({ onHome }) {
  return (
    <button className="brand" onClick={onHome} aria-label="返回即刻AI-PPT首页" style={{ background: "transparent", cursor: "pointer", padding: 0 }}>
      <span className="brand-mark" aria-hidden="true">即</span>
      <span className="brand-word">即刻AI-PPT</span>
    </button>
  );
}

function Topbar({ onHome, onHistory, onTemplate, screen }) {
  return (
    <header className="topbar">
      <Brand onHome={onHome} />
      <nav className="topnav" aria-label="主导航">
        <button className="nav-btn desktop-only" onClick={onTemplate} aria-label="上传模板">
          <span className="nav-glyph" aria-hidden="true">＋</span>
          <span className="nav-text">上传模板</span>
        </button>
        <button className="nav-btn" onClick={onHistory} aria-label="历史创作">
          <span className="nav-glyph" aria-hidden="true">◫</span>
          <span className="nav-text">历史创作</span>
        </button>
        {screen === "home" && (
          <div className="quota-pill" title="原型占位：实际额度待商品方案确认">
            <span className="quota-dot"></span>
            本月可生成 42 页
          </div>
        )}
        <div className="avatar" aria-label="用户头像">YL</div>
      </nav>
    </header>
  );
}

function ModeSegment({ modes, value, onChange }) {
  return (
    <div className="mode-segment" aria-label="生成模式">
      {modes.map((mode) => (
        <button
          key={mode.id}
          className={value === mode.id ? "active" : ""}
          onClick={() => onChange(mode.id)}
          title={mode.note}
          aria-pressed={value === mode.id}
        >
          {mode.label}
        </button>
      ))}
    </div>
  );
}

function TemplateVisual({ template, compact = false }) {
  return (
    <div className={`template-visual tv-${template.tone}`} aria-hidden="true">
      {template.tone === "paper" && <span className="tv-stripe"></span>}
      <span className="tv-rule"></span>
      <span className="tv-title">{template.name}<br />演示模板</span>
      {!compact && <span className="tv-meta">STRATEGY · 2026</span>}
    </div>
  );
}

function TemplateCard({ template, selected, onSelect }) {
  return (
    <button className={`template-card ${selected ? "selected" : ""}`} onClick={() => onSelect(template.id)} aria-pressed={selected}>
      {selected && <span className="selected-badge">已选择</span>}
      <TemplateVisual template={template} />
      <span className="template-meta">
        <strong>{template.name}</strong>
        <span>{template.description}</span>
      </span>
    </button>
  );
}

function Stepper({ active = 2 }) {
  const steps = [
    ["01", "内容输入"],
    ["02", "意图与大纲"],
    ["03", "模式与模板"],
    ["04", "生成与导出"],
  ];
  return (
    <div className="stepper" aria-label="创作步骤">
      {steps.map((step, index) => (
        <div key={step[0]} className={`step ${index + 1 < active ? "done" : ""} ${index + 1 === active ? "active" : ""}`} aria-current={index + 1 === active ? "step" : undefined}>
          <strong>{step[0]}</strong>
          {step[1]}
        </div>
      ))}
    </div>
  );
}

function OutlineCard({ item, index, total, onChange, onMove, onDelete }) {
  return (
    <article className="outline-card">
      <div className="slide-number">{String(index + 1).padStart(2, "0")}</div>
      <div className="outline-copy">
        <input
          aria-label={`第 ${index + 1} 页标题`}
          value={item.title}
          onChange={(event) => onChange(item.id, "title", event.target.value)}
        />
        <textarea
          aria-label={`第 ${index + 1} 页要点`}
          value={item.body}
          onChange={(event) => onChange(item.id, "body", event.target.value)}
        ></textarea>
        <span className="badge">{item.type}</span>
      </div>
      <div className="outline-actions" aria-label={`第 ${index + 1} 页操作`}>
        <button onClick={() => onMove(index, -1)} disabled={index === 0} aria-label="上移一页">↑</button>
        <button onClick={() => onMove(index, 1)} disabled={index === total - 1} aria-label="下移一页">↓</button>
        <button onClick={() => onDelete(item.id)} aria-label="删除此页">×</button>
      </div>
    </article>
  );
}

function SlideMini({ item, index, status = "ready", active = false, onRetry, onClick, compact = false }) {
  const labels = {
    waiting: "等待生成",
    content: "正在生成内容",
    rendering: "正在排版",
    qa: "质量检查",
    ready: "已完成",
    failed: "排版失败",
  };
  const statusClass = status === "ready" ? "status-ready" : status === "failed" ? "status-failed" : ["content", "rendering", "qa"].includes(status) ? "status-active" : "";
  return (
    <div className="slide-item">
      <div
        className={`slide-canvas ${status === "waiting" ? "waiting" : ""} ${status === "failed" ? "failed" : ""} ${active ? "active" : ""}`}
        onClick={onClick}
        role={onClick ? "button" : undefined}
        tabIndex={onClick ? 0 : undefined}
        onKeyDown={onClick ? (event) => { if (event.key === "Enter" || event.key === " ") onClick(); } : undefined}
        aria-label={onClick ? `打开第 ${index + 1} 页` : undefined}
      >
        <div className="slide-mini-kicker">{item.type || "CHAPTER"}</div>
        <div className="slide-mini-title">{item.title}</div>
        <div className="slide-mini-rule"></div>
        <div className="slide-mini-lines"><i></i><i></i><i></i></div>
        <div className="slide-mini-number">{String(index + 1).padStart(2, "0")}</div>
      </div>
      {!compact && (
        <div className={`slide-status ${statusClass}`}>
          <span className="status-label"><i className="status-dot"></i>{labels[status] || status}</span>
          {status === "failed" && <button className="retry-link" onClick={() => onRetry(index)}>重试</button>}
        </div>
      )}
    </div>
  );
}

function HistoryDrawer({ open, items, onClose, onOpenItem }) {
  if (!open) return null;
  return (
    <div className="drawer-scrim" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="drawer" aria-modal="true" role="dialog" aria-labelledby="history-title">
        <div className="drawer-head">
          <div>
            <div className="card-eyebrow">Workspace</div>
            <h2 id="history-title">历史创作</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="关闭历史创作">×</button>
        </div>
        <div className="history-list">
          {items.map((item) => (
            <button className="history-item" key={item.id} onClick={() => onOpenItem(item)}>
              <span className="history-item-top">
                <strong>{item.title}</strong>
                <span className={`badge ${item.tone}`}>{item.status}</span>
              </span>
              <p>{item.meta}</p>
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}

function TemplateModal({ open, onClose, phase, progress, fileName, mappings, onStartUpload, onMappingChange, onSave }) {
  if (!open) return null;
  const ready = phase === "ready";
  const parsing = phase === "parsing";
  const previews = [
    { title: "年度经营复盘", role: "封面" },
    { title: "报告目录", role: "目录" },
    { title: "01 / 市场回顾", role: "章节" },
    { title: "核心指标变化", role: "正文" },
    { title: "谢谢", role: "结束" },
  ];
  return (
    <div className="modal-scrim" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="template-modal-title" data-screen-label="上传模板">
        <header className="modal-head">
          <div>
            <div className="card-eyebrow">Private template</div>
            <h2 id="template-modal-title">上传并解析模板</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="关闭上传模板">×</button>
        </header>
        <div className="modal-body">
          <div className="template-upload-pane">
            <h3>让 AI 先识别版式角色</h3>
            <p className="pane-intro">支持 PPTX/PPT，建议 16:9、50MB 内。原型会模拟解析；生产版本还会进行安全扫描、字体与可编辑性检查。</p>
            {phase === "idle" ? (
              <div className="dropzone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); onStartUpload(event.dataTransfer.files?.[0]?.name || "品牌汇报模板.pptx"); }}>
                <div>
                  <strong>拖拽 PPT 模板到这里</strong>
                  <p>或选择本地文件；上传后不会立即保存</p>
                  <div className="dropzone-actions">
                    <label role="button" tabIndex="0">
                      选择本地 PPTX
                      <input type="file" accept=".ppt,.pptx" onChange={(event) => onStartUpload(event.target.files?.[0]?.name || "品牌汇报模板.pptx")} />
                    </label>
                    <button className="soft-btn" onClick={() => onStartUpload("品牌汇报模板.pptx")}>使用示例模板</button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="parse-block">
                <div className="parse-file">
                  <div><strong>{fileName}</strong><span>16:9 · 24 页 · 8.6 MB</span></div>
                  <span className={`badge ${ready ? "green" : "blue"}`}>{ready ? "解析完成" : "解析中"}</span>
                </div>
                <div className="linear-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progress}>
                  <i style={{ width: `${progress}%` }}></i>
                </div>
                <div className="parse-copy" aria-live="polite">
                  {parsing ? `正在识别字体、配色与页面角色 · ${progress}%` : "已识别 5 类关键版式；请在右侧校正后保存。"}
                </div>
              </div>
            )}

            <div className="layout-guide">
              <h3>推荐包含的五类页面</h3>
              <p className="pane-intro">缺少某类页面时仍可继续，但系统会使用默认版式补齐。</p>
              <div className="layout-role-grid">
                {["封面", "目录", "章节", "正文", "结束"].map((role) => (
                  <div className="layout-role" key={role}><div className="role-mini"></div><span>{role}</span></div>
                ))}
              </div>
            </div>
          </div>
          <aside className="preview-pane">
            <h3>页面预览与映射</h3>
            <p className="pane-intro">{ready ? "自动识别并非最终答案，你可以修正每页角色。" : "解析完成后在这里显示真实页面预览。"}</p>
            <div className="preview-stack">
              {previews.map((preview, index) => (
                <div className="preview-card" key={index} style={{ opacity: ready ? 1 : .45 }}>
                  <select
                    className="role-select"
                    aria-label={`第 ${index + 1} 个版式角色`}
                    value={mappings[index] || preview.role}
                    onChange={(event) => onMappingChange(index, event.target.value)}
                    disabled={!ready}
                  >
                    {["封面", "目录", "章节", "正文", "结束", "忽略"].map((role) => <option key={role}>{role}</option>)}
                  </select>
                  <strong>{ready ? preview.title : "等待模板解析"}</strong>
                </div>
              ))}
            </div>
            {ready && <div className="compatibility"><strong>兼容性通过</strong><br />5 类关键版式齐全；19/24 页可直接填充，5 页可作为品牌参考。</div>}
          </aside>
        </div>
        <footer className="modal-footer">
          <button className="ghost-btn" onClick={onClose}>取消</button>
          <button className="primary-btn" onClick={onSave} disabled={!ready}>保存模板并选用</button>
        </footer>
      </section>
    </div>
  );
}

function Toast({ message }) {
  if (!message) return null;
  return <div className="toast" role="status"><span className="toast-dot"></span>{message}</div>;
}

Object.assign(window, {
  Brand,
  Topbar,
  ModeSegment,
  TemplateVisual,
  TemplateCard,
  Stepper,
  OutlineCard,
  SlideMini,
  HistoryDrawer,
  TemplateModal,
  Toast,
});
