function TitleOption({ className, code, name, note }) {
  return (
    <div className={`title-option ${className}`} data-screen-label={code}>
      <header className="option-header">
        <div className="option-brand">
          <span className="option-mark" aria-hidden="true">
            即
          </span>
          <span>
            即刻<strong>AI-PPT</strong>
          </span>
        </div>
        <div className="option-account">
          <span>历史创作</span>
          <span>YL</span>
        </div>
      </header>
      <main className="option-main">
        <h1 className="option-title">
          让想法<span>即刻成片</span>
        </h1>
        <section className="option-composer" aria-label="AI 创作输入预览">
          <div className="option-placeholder">
            帮我生成一份 PPT，例如：面向管理层的 2027 年产品增长策略……
          </div>
          <div className="option-toolbar">
            <div className="option-tools">
              <button className="option-upload" type="button">
                ＋&nbsp; 上传文档
              </button>
              <div className="option-modes">
                <span>自由设计</span>
                <span>模板复用</span>
              </div>
            </div>
            <button className="option-generate" type="button">
              立即生成
            </button>
          </div>
        </section>
        <div className="option-signature">
          <span>{note}</span>
          <strong>{code} · {name}</strong>
        </div>
      </main>
    </div>
  );
}

function TitleFontOptionsApp() {
  return (
    <DesignCanvas minScale={0.2} maxScale={3}>
      <DCSection
        id="title-font-options"
        title="首页标题字体 · 三版方案"
        subtitle="点击卡片上方的展开按钮可全屏查看；真实首页代码尚未修改。"
        gap={34}
      >
        <DCArtboard
          id="option-a"
          label="A · 新中式雅宋"
          width={360}
          height={300}
        >
          <TitleOption
            className="option-a"
            code="A"
            name="新中式雅宋"
            note="稳重、克制、与暖纸色最协调"
          />
        </DCArtboard>
        <DCArtboard
          id="option-b"
          label="B · 现代品牌黑体"
          width={360}
          height={300}
        >
          <TitleOption
            className="option-b"
            code="B"
            name="现代品牌黑体"
            note="清晰、有力量、AI 产品感更强"
          />
        </DCArtboard>
        <DCArtboard
          id="option-c"
          label="C · 清雅手写楷体"
          width={360}
          height={300}
        >
          <TitleOption
            className="option-c"
            code="C"
            name="清雅手写楷体"
            note="轻松、有人文感、辨识度最高"
          />
        </DCArtboard>
      </DCSection>
    </DesignCanvas>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <TitleFontOptionsApp />,
);
