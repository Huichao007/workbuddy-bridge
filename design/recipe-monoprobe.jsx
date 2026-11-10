(() => {
  const bg = designVar("color/bg");
  const t1 = designVar("color/text-1");
  const t3 = designVar("color/text-3");
  const fonts = [
    "JetBrains Mono",
    "Cascadia Mono",
    "Cascadia Code",
    "Consolas",
    "Courier New",
    "Roboto Mono",
    "DejaVu Sans Mono",
    "Menlo",
    "SF Mono",
  ];
  return (
    <Frame name="monoprobe" w={620} h={420} bg={bg} p={24} flex="col" gap={10}>
      {fonts.map((f, i) => (
        <Frame key={i} w="fill" flex="col" gap={2}>
          <Text size={10} color={t3} font="Inter">
            {f}
          </Text>
          <Text size={14} color={t1} font={f}>
            $ opencode run -m workbuddy 0123456789 中文
          </Text>
        </Frame>
      ))}
    </Frame>
  );
})();
