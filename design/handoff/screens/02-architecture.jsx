<div data-name="02 架构图 Architecture" className="flex pt-16 px-22 pb-12 flex-col items-start gap-10 w-310 h-162 bg-bg box-border">
  <div data-name="Frame" className="flex flex-col items-start self-stretch gap-[14px]">
    <p data-name="Text" className="text-[11px] font-bold text-brand font-[Inter] tracking-[1.600000023841858px] whitespace-pre-wrap">ONE SUBSCRIPTION · TWO CLIENTS</p>
    <p data-name="Text" className="text-7 font-bold text-text-1 font-[Noto_Sans_SC] tracking-[-0.4000000059604645px] whitespace-pre-wrap">一份积分，两个客户端，一条账单</p>
    <p data-name="Text" className="w-175 text-[15px] font-normal leading-[1.7000000476837158px] text-text-2 font-[Noto_Sans_SC] whitespace-pre-wrap">WorkBuddy 桌面端的登录态留在原地，桥接只在本机回环上开一个端口。</p>
    <p data-name="Text" className="w-175 text-[15px] font-normal leading-[1.7000000476837158px] text-text-2 font-[Noto_Sans_SC] whitespace-pre-wrap">不新建账号，不转发 token，积分仍然只从这一个池子扣。</p>
  </div>
  <div data-name="Diagram" className="flex items-center self-stretch h-85">
    <div data-name="Frame" className="flex p-[22px] flex-col justify-between items-start gap-4 w-75 h-85 bg-surface box-border rounded-lg">
      <div data-name="Frame" className="flex flex-col items-start self-stretch gap-2">
        <p data-name="Text" className="text-[11px] font-bold text-text-3 font-[Inter] tracking-[1.2000000476837158px] whitespace-pre-wrap">WORKBUDDY DESKTOP</p>
        <p data-name="Text" className="text-[17px] font-bold text-text-1 font-[Noto_Sans_SC] tracking-[-0.20000000298023224px] whitespace-pre-wrap">订阅积分池</p>
        <p data-name="Text" className="text-[13px] font-normal leading-[1.7000000476837158px] text-text-2 font-[Noto_Sans_SC] whitespace-pre-wrap">已经在付的那一份。已登录，桥接只是借道。</p>
      </div>
      <div data-name="Frame" className="flex flex-col items-start self-stretch gap-2">
        <p data-name="Text" className="text-xs font-normal text-text-3 font-[Noto_Sans_SC] whitespace-pre-wrap">桌面端开着管道就通，关掉会按需拉起</p>
        <p data-name="Text" className="text-xs font-normal text-text-3 font-[Noto_Sans_SC] whitespace-pre-wrap">模型清单每次启动从桌面端现读，不写死</p>
      </div>
      <div data-name="Frame" className="flex flex-col items-start self-stretch gap-3">
        <div data-name="Frame" className="self-stretch h-px bg-line" />
        <div data-name="Frame" className="flex justify-between items-end self-stretch">
          <div data-name="Frame" className="flex flex-col items-start gap-[2px]">
            <p data-name="Text" className="text-7 font-bold text-text-1 font-[Inter] tracking-[-1.2000000476837158px] whitespace-pre-wrap">25</p>
            <p data-name="Text" className="text-[11px] font-normal text-text-3 font-[Noto_Sans_SC] whitespace-pre-wrap">个模型 · 本机现读</p>
          </div>
          <div data-name="Frame" className="flex flex-col items-end gap-[2px]">
            <p data-name="Text" className="text-7 font-bold text-text-1 font-[Inter] tracking-[-1.2000000476837158px] whitespace-pre-wrap">0</p>
            <p data-name="Text" className="text-[11px] font-normal text-text-3 font-[Noto_Sans_SC] whitespace-pre-wrap">个 API key</p>
          </div>
        </div>
        <div data-name="Frame" className="flex justify-center items-center self-stretch h-7 bg-brand-dim rounded-sm">
          <p data-name="Text" className="text-[11px] font-bold text-brand-ink font-[Noto_Sans_SC] tracking-[0.4000000059604645px] whitespace-pre-wrap">计费通道 · 只有这一条</p>
        </div>
      </div>
    </div>
    <div data-name="Frame" className="flex items-center w-16 h-85">
      <div data-name="Frame" className="w-16 h-px bg-brand" />
    </div>
    <div data-name="Frame" className="flex p-5 flex-col justify-center items-start gap-[10px] w-68 h-49 bg-surface-2 box-border rounded-lg">
      <p data-name="Text" className="text-[11px] font-bold text-text-3 font-[Inter] tracking-[1.2000000476837158px] whitespace-pre-wrap">BRIDGE · 仅回环</p>
      <p data-name="Text" className="text-[17px] font-bold text-text-1 font-[Inter] tracking-[-0.30000001192092896px] whitespace-pre-wrap">127.0.0.1:18490</p>
      <p data-name="Text" className="text-xs font-normal leading-[1.7000000476837158px] text-text-2 font-[Noto_Sans_SC] whitespace-pre-wrap">OpenAI 兼容 /v1 · 纯标准库</p>
      <div data-name="Frame" className="flex items-center self-stretch gap-[6px]">
        <div data-name="Frame" className="w-[6px] h-[6px] bg-ok rounded-full" />
        <p data-name="Text" className="text-[11px] font-normal text-text-3 font-[Inter] whitespace-pre-wrap">wbipc · available</p>
      </div>
    </div>
    <div data-name="Frame" className="flex flex-col items-start w-18 h-85">
      <div data-name="Frame" className="flex items-end self-stretch h-[46px]">
        <div data-name="Frame" className="w-9 h-px" />
        <div data-name="Frame" className="w-9 h-px bg-line" />
      </div>
      <div data-name="Frame" className="flex items-center self-stretch h-62">
        <div data-name="Frame" className="flex flex-col items-start w-9 h-62">
          <div data-name="Frame" className="w-px h-[46px]" />
          <div data-name="Frame" className="w-9 h-px bg-brand" />
          <div data-name="Frame" className="w-px h-[201px]" />
        </div>
        <div data-name="Frame" className="w-px h-62 bg-line" />
        <div data-name="Frame" className="w-[35px] h-px" />
      </div>
      <div data-name="Frame" className="flex items-start self-stretch h-[46px]">
        <div data-name="Frame" className="w-9 h-px" />
        <div data-name="Frame" className="w-9 h-px bg-line" />
      </div>
    </div>
    <div data-name="Frame" className="flex flex-col justify-between items-start w-73 h-85">
      <div data-name="Frame" className="flex flex-col items-start gap-2 w-73 h-23 bg-surface-2 py-[14px] px-4 box-border rounded-md">
        <div data-name="Frame" className="flex justify-between items-center self-stretch">
          <div data-name="Frame" className="flex items-center gap-2">
            <div data-name="Frame" className="w-[6px] h-[6px] bg-ok rounded-full" />
            <p data-name="Text" className="text-[15px] font-bold text-text-1 font-[Inter] tracking-[-0.20000000298023224px] whitespace-pre-wrap">OpenCode</p>
          </div>
          <p data-name="Text" className="text-[11px] font-normal text-text-3 font-[Inter] tracking-[0.4000000059604645px] whitespace-pre-wrap">chat/completions</p>
        </div>
        <p data-name="Text" className="text-xs font-normal text-text-2 font-[Noto_Sans_SC] whitespace-pre-wrap">模型选择器里多出一组 WorkBuddy</p>
      </div>
      <div data-name="Frame" className="flex flex-col items-start gap-2 w-73 h-23 bg-surface-2 py-[14px] px-4 box-border rounded-md">
        <div data-name="Frame" className="flex justify-between items-center self-stretch">
          <div data-name="Frame" className="flex items-center gap-2">
            <div data-name="Frame" className="w-[6px] h-[6px] bg-ok rounded-full" />
            <p data-name="Text" className="text-[15px] font-bold text-text-1 font-[Inter] tracking-[-0.20000000298023224px] whitespace-pre-wrap">Codex CLI</p>
          </div>
          <p data-name="Text" className="text-[11px] font-normal text-text-3 font-[Inter] tracking-[0.4000000059604645px] whitespace-pre-wrap">responses</p>
        </div>
        <p data-name="Text" className="text-xs font-normal text-text-2 font-[Noto_Sans_SC] whitespace-pre-wrap">provider workbuddy 直接可跑</p>
      </div>
    </div>
  </div>
</div>