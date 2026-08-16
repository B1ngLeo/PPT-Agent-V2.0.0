import { SourceUploader } from "./source-uploader";

export default function HomePage() {
  return (
    <main id="main-content" className="shell">
      <header className="topbar" aria-label="产品导航">
        <a className="brand" href="#main-content" aria-label="即刻AI-PPT 首页">
          <span className="brand-mark" aria-hidden="true">
            即
          </span>
          <span>即刻AI-PPT</span>
        </a>
        <span className="phase-pill">安全来源工作台</span>
      </header>
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="eyebrow">DOCUMENT TO DECK · P1</p>
          <h1 id="hero-title">
            先读懂你的材料，<span>再让想法即刻成片。</span>
          </h1>
          <p className="hero-description">
            上传 DOCX、PDF、PPTX 或
            HTML。文件会经过私有隔离、病毒扫描和格式校验，
            只有安全内容才会进入解析流程。
          </p>
          <div className="trust-row" aria-label="安全能力">
            <span>私有对象存储</span>
            <span>三重格式校验</span>
            <span>可恢复解析</span>
          </div>
        </div>
        <SourceUploader />
      </section>
      <section className="process" aria-labelledby="process-title">
        <div>
          <p className="eyebrow">SECURITY PIPELINE</p>
          <h2 id="process-title">每一步都有持久状态</h2>
        </div>
        <ol>
          <li>
            <b>01</b>
            <span>隔离上传</span>
            <small>固定大小、类型与 SHA-256</small>
          </li>
          <li>
            <b>02</b>
            <span>安全扫描</span>
            <small>病毒、magic、归档和外链检查</small>
          </li>
          <li>
            <b>03</b>
            <span>内容解析</span>
            <small>发布不可变 Markdown 与素材</small>
          </li>
        </ol>
      </section>
    </main>
  );
}
