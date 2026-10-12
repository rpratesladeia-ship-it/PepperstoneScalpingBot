# PepperstoneScalpingBot — projeto inicial

Projeto experimental para o cTrader Automate/cBots, preparado para ser enviado a um repositório GitHub pelo Android.

## Arquivos
- `PepperstoneScalpingBot.cs`: código-fonte inicial.
- `PepperstoneScalpingBot.csproj`: projeto .NET com referência ao pacote cTrader Automate.
- `.github/workflows/build-cbot.yml`: workflow manual/automático para tentar compilar com a imagem Linux oficial do cTrader CLI e publicar o `.algo` como artefato do GitHub Actions.

## Como enviar pelo celular
1. No GitHub, crie um repositório novo chamado `PepperstoneScalpingBot`.
2. Envie todos os arquivos e pastas deste pacote, mantendo o caminho `.github/workflows/build-cbot.yml`.
3. Abra a aba **Actions** do repositório e habilite Actions, se solicitado.
4. Execute **Build cTrader cBot (experimental)** com **Run workflow**.
5. Abra a execução concluída e verifique os logs. Se falhar, copie a mensagem de erro; não coloque senhas nem tokens no chat.
6. Se concluir, baixe o artefato `PepperstoneScalpingBot-algo` e confirme que contém um `.algo`.

## Limitações importantes
- Este projeto ainda NÃO foi compilado ou executado nesta sessão.
- O workflow é experimental; a imagem oficial/CLI e o layout do output podem mudar. O primeiro run deve ser tratado como diagnóstico.
- Mesmo que compile, isso não valida a estratégia nem o dimensionamento de volume. Revisar o código, executar backtests e testar em conta demo antes de operar.
- Nunca salve senha, token, cTrader ID, chaves de API ou credenciais de conta no repositório.
- O limite diário implementado é uma proteção de software e não garante que a perda real nunca ultrapasse o limite (gaps, slippage, falhas, comissões e execução podem afetar o resultado).
