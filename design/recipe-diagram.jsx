(() => {
  const bg = designVar("color/bg");
  const surface = designVar("color/surface");
  const s2 = designVar("color/surface-2");
  const line = designVar("color/line");
  const t1 = designVar("color/text-1");
  const t2 = designVar("color/text-2");
  const t3 = designVar("color/text-3");
  const brand = designVar("color/brand");
  const brandDim = designVar("color/brand-dim");
  const brandInk = designVar("color/brand-ink");
  const ok = designVar("color/ok");
  const rSm = designVar("radius/sm");
  const rMd = designVar("radius/md");
  const rLg = designVar("radius/lg");
  const rFull = designVar("radius/full");

  const CN = "Noto Sans SC";
  const NUM = "Inter";

  const H = 340;
  const CARD = 92;
  const TOPC = CARD / 2;
  const BOTC = H - CARD / 2;
  const RAILX = 36;
  const MIDS = TOPC;
  const MIDE = BOTC - TOPC;

  const barH = (w, c) => <Frame w={w} h={1} bg={c} />;
  const barV = (h, c) => <Frame w={1} h={h} bg={c} />;

  const fan = () => (
    <Frame w={72} h={H} flex="col">
      <Frame w="fill" h={TOPC} flex="row" items="end">
        <Frame w={RAILX} h={1} />
        {barH(RAILX, line)}
      </Frame>
      <Frame w="fill" h={MIDE} flex="row" items="center">
        <Frame w={RAILX} h={MIDE} flex="col">
          <Frame h={MIDS} w={1} />
          {barH(RAILX, brand)}
          <Frame h={MIDE - MIDS - 1} w={1} />
        </Frame>
        {barV(MIDE, line)}
        <Frame w={RAILX - 1} h={1} />
      </Frame>
      <Frame w="fill" h={H - BOTC} flex="row" items="start">
        <Frame w={RAILX} h={1} />
        {barH(RAILX, line)}
      </Frame>
    </Frame>
  );

  const client = (name, proto, note) => (
    <Frame
      w={292}
      h={CARD}
      bg={s2}
      rounded={rMd}
      px={16}
      py={14}
      flex="col"
      gap={8}
    >
      <Frame w="fill" flex="row" items="center" justify="between">
        <Frame flex="row" items="center" gap={8}>
          <Frame w={6} h={6} rounded={rFull} bg={ok} />
          <Text
            size={15}
            weight="bold"
            color={t1}
            font={NUM}
            letterSpacing={-0.2}
          >
            {name}
          </Text>
        </Frame>
        <Text size={11} color={t3} font={NUM} letterSpacing={0.4}>
          {proto}
        </Text>
      </Frame>
      <Text size={12} color={t2} font={CN}>
        {note}
      </Text>
    </Frame>
  );

  return (
    <Frame
      name="02 架构图 Architecture"
      w={1240}
      h={648}
      bg={bg}
      flex="col"
      gap={40}
      px={88}
      pt={64}
      pb={48}
    >
      <Frame w="fill" flex="col" gap={14}>
        <Text
          size={11}
          weight="bold"
          color={brand}
          font={NUM}
          letterSpacing={1.6}
        >
          ONE SUBSCRIPTION · TWO CLIENTS
        </Text>
        <Text size={28} weight="bold" color={t1} font={CN} letterSpacing={-0.4}>
          一份积分，两个客户端，一条账单
        </Text>
        <Text size={15} color={t2} font={CN} w={700} lineHeight={1.7}>
          WorkBuddy 桌面端的登录态留在原地，桥接只在本机回环上开一个端口。
        </Text>
        <Text size={15} color={t2} font={CN} w={700} lineHeight={1.7}>
          不新建账号，不转发 token，积分仍然只从这一个池子扣。
        </Text>
      </Frame>

      <Frame name="Diagram" w="fill" h={H} flex="row" items="center">
        <Frame
          w={300}
          h={H}
          bg={surface}
          rounded={rLg}
          p={22}
          flex="col"
          justify="between"
          gap={16}
        >
          <Frame w="fill" flex="col" gap={8}>
            <Text
              size={11}
              weight="bold"
              color={t3}
              font={NUM}
              letterSpacing={1.2}
            >
              WORKBUDDY DESKTOP
            </Text>
            <Text
              size={17}
              weight="bold"
              color={t1}
              font={CN}
              letterSpacing={-0.2}
            >
              订阅积分池
            </Text>
            <Text size={13} color={t2} font={CN} lineHeight={1.7}>
              已经在付的那一份。已登录，桥接只是借道。
            </Text>
          </Frame>

          <Frame w="fill" flex="col" gap={8}>
            <Text size={12} color={t3} font={CN}>
              桌面端开着管道就通，关掉会按需拉起
            </Text>
            <Text size={12} color={t3} font={CN}>
              模型清单每次启动从桌面端现读，不写死
            </Text>
          </Frame>

          <Frame w="fill" flex="col" gap={12}>
            <Frame w="fill" h={1} bg={line} />
            <Frame w="fill" flex="row" items="end" justify="between">
              <Frame flex="col" gap={2}>
                <Text
                  size={28}
                  weight="bold"
                  color={t1}
                  font={NUM}
                  letterSpacing={-1.2}
                >
                  25
                </Text>
                <Text size={11} color={t3} font={CN}>
                  个模型 · 本机现读
                </Text>
              </Frame>
              <Frame flex="col" gap={2} items="end">
                <Text
                  size={28}
                  weight="bold"
                  color={t1}
                  font={NUM}
                  letterSpacing={-1.2}
                >
                  0
                </Text>
                <Text size={11} color={t3} font={CN}>
                  个 API key
                </Text>
              </Frame>
            </Frame>
            <Frame
              w="fill"
              h={28}
              rounded={rSm}
              bg={brandDim}
              flex="row"
              items="center"
              justify="center"
            >
              <Text
                size={11}
                weight="bold"
                color={brandInk}
                font={CN}
                letterSpacing={0.4}
              >
                计费通道 · 只有这一条
              </Text>
            </Frame>
          </Frame>
        </Frame>

        <Frame w={64} h={H} flex="row" items="center">
          {barH(64, brand)}
        </Frame>

        <Frame
          w={272}
          h={196}
          bg={s2}
          rounded={rLg}
          p={20}
          flex="col"
          justify="center"
          gap={10}
        >
          <Text
            size={11}
            weight="bold"
            color={t3}
            font={NUM}
            letterSpacing={1.2}
          >
            BRIDGE · 仅回环
          </Text>
          <Text
            size={17}
            weight="bold"
            color={t1}
            font={NUM}
            letterSpacing={-0.3}
          >
            127.0.0.1:18490
          </Text>
          <Text size={12} color={t2} font={CN} lineHeight={1.7}>
            OpenAI 兼容 /v1 · 纯标准库
          </Text>
          <Frame w="fill" flex="row" items="center" gap={6}>
            <Frame w={6} h={6} rounded={rFull} bg={ok} />
            <Text size={11} color={t3} font={NUM}>
              wbipc · available
            </Text>
          </Frame>
        </Frame>

        {fan()}

        <Frame w={292} h={H} flex="col" justify="between">
          {client(
            "OpenCode",
            "chat/completions",
            "模型选择器里多出一组 WorkBuddy",
          )}
          {client("Codex CLI", "responses", "provider workbuddy 直接可跑")}
        </Frame>
      </Frame>
    </Frame>
  );
})();
