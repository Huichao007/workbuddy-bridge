(() => {
  const bg = designVar("color/bg");
  const surface = designVar("color/surface");
  const s2 = designVar("color/surface-2");
  const line = designVar("color/line");
  const t1 = designVar("color/text-1");
  const t2 = designVar("color/text-2");
  const t3 = designVar("color/text-3");
  const t4 = designVar("color/text-4");
  const brand = designVar("color/brand");
  const brandInk = designVar("color/brand-ink");
  const ok = designVar("color/ok");
  const rMd = designVar("radius/md");
  const rLg = designVar("radius/lg");
  const rFull = designVar("radius/full");

  const CN = "Noto Sans SC";
  const NUM = "Inter";

  const dot = (c, s) => <Frame w={s} h={s} rounded={rFull} bg={c} />;
  const tick = (h, c) => <Frame w={2} h={h} rounded={1} bg={c} />;

  // 一个"终端里跑过"的卡片
  const runCard = (cmd, model, answer) => (
    <Frame w="fill" bg={surface} rounded={rMd} p={14} flex="col" gap={8}>
      <Frame flex="row" gap={6} items="center">
        <Text size={11} color={t3} font={NUM}>
          $
        </Text>
        <Text size={11} color={t2} font={NUM}>
          {cmd}
        </Text>
      </Frame>
      <Text size={11} color={brandInk} font={NUM}>
        {model}
      </Text>
      <Frame w="fill" h={1} bg={line} />
      <Frame flex="row" items="center" gap={6}>
        <Text size={10} color={t3} font={CN}>
          ›
        </Text>
        <Text size={12} weight="bold" color={t1} font={CN}>
          {answer}
        </Text>
      </Frame>
    </Frame>
  );

  const client = (name, proto, note, card) => (
    <Frame w={336} flex="col" gap={12}>
      <Frame flex="row" items="center" gap={8}>
        {dot(ok, 7)}
        <Text
          size={20}
          weight="bold"
          color={t1}
          font={NUM}
          letterSpacing={-0.5}
        >
          {name}
        </Text>
      </Frame>
      <Text size={11} color={t3} font={NUM} letterSpacing={0.5}>
        {proto}
      </Text>
      {card}
      <Text size={11} color={t3} font={CN}>
        {note}
      </Text>
    </Frame>
  );

  return (
    <Frame
      name="03 Hero 图"
      w={1200}
      h={520}
      bg={bg}
      flex="col"
      p={56}
      gap={24}
      justify="between"
    >
      {/* 顶部标题条 */}
      <Frame w="fill" flex="row" justify="between" items="start">
        <Frame flex="col" gap={8}>
          <Text
            size={10}
            weight="bold"
            color={brand}
            font={NUM}
            letterSpacing={2.2}
          >
            ONE SUBSCRIPTION
          </Text>
          <Text
            size={30}
            weight="bold"
            color={t1}
            font={CN}
            letterSpacing={-0.7}
          >
            一份积分，两个客户端
          </Text>
        </Frame>
        <Frame flex="row" gap={32} items="start">
          <Frame flex="col" gap={1} items="end">
            <Text
              size={24}
              weight="bold"
              color={t1}
              font={NUM}
              letterSpacing={-1}
            >
              25
            </Text>
            <Text size={10} color={t3} font={CN}>
              个模型
            </Text>
          </Frame>
          <Frame flex="col" gap={1} items="end">
            <Text
              size={24}
              weight="bold"
              color={t1}
              font={NUM}
              letterSpacing={-1}
            >
              0
            </Text>
            <Text size={10} color={t3} font={CN}>
              个 API key
            </Text>
          </Frame>
        </Frame>
      </Frame>

      <Frame w="fill" h={1} bg={line} />

      {/* 三段：客户端 · 桥接 · 客户端 */}
      <Frame w="fill" grow={1} flex="row" items="center" justify="center">
        {client(
          "OpenCode",
          "/v1/chat/completions",
          "模型选择器里多出一组 WorkBuddy",
          runCard(
            "opencode run -m",
            "workbuddy/deepseek-v4.1-flash",
            "OpenCode 已连通",
          ),
        )}

        {/* 左管线 */}
        <Frame w={72} flex="col" justify="center">
          <Frame w="fill" flex="row" items="center" gap={3}>
            <Frame w={50} h={2} bg={brand} />
            {tick(9, brandInk)}
            {tick(15, brandInk)}
            {tick(7, brandInk)}
          </Frame>
        </Frame>

        {/* 桥接：中央主角 */}
        <Frame w={296} bg={s2} rounded={rLg} p={20} flex="col" gap={12}>
          {" "}
          <Frame w="fill" flex="row" items="center" justify="between">
            <Text
              size={10}
              weight="bold"
              color={t3}
              font={NUM}
              letterSpacing={1.5}
            >
              BRIDGE
            </Text>
            <Frame flex="row" items="center" gap={5}>
              {dot(ok, 6)}
              <Text size={10} color={t3} font={NUM}>
                live
              </Text>
            </Frame>
          </Frame>
          <Frame w="fill" flex="col" gap={3}>
            <Text
              size={26}
              weight="bold"
              color={t1}
              font={NUM}
              letterSpacing={-1}
            >
              18490
            </Text>
            <Text size={10} color={t3} font={NUM}>
              127.0.0.1 · 仅回环
            </Text>
          </Frame>
          <Frame w="fill" h={1} bg={line} />
          <Frame w="fill" flex="col" gap={9}>
            <Frame flex="row" justify="between" items="center">
              <Text size={11} color={t2} font={CN}>
                桌面端登录态
              </Text>
              <Text size={11} weight="bold" color={ok} font={CN}>
                已接入
              </Text>
            </Frame>
            <Frame flex="row" justify="between" items="center">
              <Text size={11} color={t2} font={CN}>
                积分归属
              </Text>
              <Text size={11} weight="bold" color={t1} font={CN}>
                原账户
              </Text>
            </Frame>
            <Frame flex="row" justify="between" items="center">
              <Text size={11} color={t2} font={CN}>
                第三方依赖
              </Text>
              <Text size={11} weight="bold" color={t1} font={NUM}>
                0
              </Text>
            </Frame>
          </Frame>
        </Frame>

        {/* 右管线 */}
        <Frame w={72} flex="col" justify="center">
          <Frame w="fill" flex="row" items="center" gap={3}>
            {tick(7, brandInk)}
            {tick(15, brandInk)}
            {tick(9, brandInk)}
            <Frame w={50} h={2} bg={brand} />
          </Frame>
        </Frame>

        {client(
          "Codex CLI",
          "/v1/responses",
          "provider 直接可跑，不用占位 key",
          runCard(
            "codex -c provider=workbuddy",
            'exec "写个快排"',
            "Codex 已连通",
          ),
        )}
      </Frame>

      <Frame w="fill" h={1} bg={line} />

      {/* 底部结论条 */}
      <Frame w="fill" flex="row" justify="between" items="center">
        <Text size={11} color={t3} font={CN}>
          不新建账号 · 不转发 token · 一条计费通道
        </Text>
        <Frame flex="row" items="center" gap={8}>
          <Frame w={24} h={1} bg={line} />
          <Text size={9} color={t3} font={NUM} letterSpacing={1}>
            SAME POOL
          </Text>
          <Frame w={24} h={1} bg={line} />
        </Frame>
      </Frame>
    </Frame>
  );
})();
