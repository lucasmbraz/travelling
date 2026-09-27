# ✈️ Radar de Passagens

Um radar pessoal que roda sozinho, de graça, no GitHub, e faz três coisas:

1. **Quando é mais barato ir para Maceió (ou Recife)?** Olha o mês inteiro, ida e volta
   separadas, e monta as melhores combinações respeitando quantas noites você quer ficar,
   em **reais** e em **pontos Azul**. Mostra um calendário colorido (verde = barato) e já
   diz se vale mais a pena usar pontos ou pagar em dinheiro. A opção "Recife + carro" já
   soma o custo da estrada.
2. **Para onde dá pra ir barato?** Lista as passagens de ida e volta mais baratas saindo de
   Belém para *qualquer* destino nos próximos meses (Lima, Fortaleza, São Luís...).
3. **Me avisa das promoções.** Lê os blogs de milhas (Passageiro de Primeira, Melhores
   Destinos, Pontos pra Voar) e manda no seu **Telegram** quando aparece bônus de
   transferência Livelo/Inter → Azul, promoção saindo de Belém ou quando o preço cai /
   fica abaixo do alvo que você definiu.

Tudo aparece num painel web (funciona bem no celular) e os alertas chegam no Telegram.

## Como funciona

```
GitHub Actions (3x por dia)
   ├─ Travelpayouts/Aviasales → preços em R$ por dia, qualquer destino
   ├─ Seats.aero (opcional)   → resgates reais em pontos Azul Fidelidade
   └─ RSS dos blogs de milhas → promoções e bônus de transferência
        ↓
   calcula melhores datas, plano de pontos, compara com o histórico
        ↓
   painel no GitHub Pages  +  alertas no Telegram
```

## Configurar (uns 20 minutos, uma vez só)

### 1. Token de preços (grátis)
Crie uma conta em [travelpayouts.com](https://www.travelpayouts.com/), vá em
**Perfil → API token** e copie o token.

### 2. Bot do Telegram (grátis)
1. No Telegram, fale com **@BotFather** → `/newbot` → escolha um nome. Ele te dá o **token**.
2. Mande qualquer mensagem para o seu bot novo.
3. Abra `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates` no navegador e copie o número
   em `"chat":{"id": ...}` — esse é o **chat id**.

### 3. Pontos Azul reais (opcional, pago)
Sem isso, o radar **estima** os pontos a partir do preço em reais (configurável em
`valor_milheiro_azul`). Para ver a disponibilidade real de resgate da Azul Fidelidade,
assine o [Seats.aero Pro](https://seats.aero/) (~US$ 10/mês, dá pra assinar só nos meses
em que estiver planejando) e pegue a chave da API nas configurações.

### 4. Colocar no GitHub
No repositório: **Settings → Secrets and variables → Actions → New repository secret**:

| Segredo | Valor |
|---|---|
| `TRAVELPAYOUTS_TOKEN` | token do passo 1 |
| `TELEGRAM_BOT_TOKEN` | token do BotFather |
| `TELEGRAM_CHAT_ID` | chat id do passo 2 |
| `SEATS_AERO_KEY` | (opcional) chave do Seats.aero |
| `SALDOS` | (opcional) ex.: `azul=12000,livelo=45000,cartao=20000` — assim seus saldos não ficam públicos |

Depois: **Settings → Pages → Source: GitHub Actions**. Em **Actions → Radar de passagens →
Run workflow** você roda na hora; depois ele roda sozinho 3x por dia. O endereço do painel
aparece no resultado do job (algo como `https://SEU_USUARIO.github.io/travelling/`). Se
quiser o link do painel nas mensagens do Telegram, crie a *variable* `DASHBOARD_URL` com ele.

> **Privacidade:** o GitHub Pages é público mesmo com o repositório privado em contas
> gratuitas. O painel não tem nada sensível além dos saldos — por isso a opção `SALDOS`
> como segredo em vez de colocar no `config.yaml`.

### 5. Ajustar ao seu gosto
Tudo fica em [`config.yaml`](config.yaml): destinos, janelas de viagem (ex.: "Fim de ano,
de 12/12 a 15/01, de 7 a 21 noites"), preço-alvo de cada rota, custo do carro
Recife→Maceió, preço máximo para avisar de oportunidades, proporção e bônus de cada
programa de pontos.

## Usar no computador (opcional)

```bash
pip install -e .

# painel com dados fictícios, sem precisar de nenhuma chave
python -m radar --demo painel --sem-alertas      # abre site/index.html

# com dados reais
export TRAVELPAYOUTS_TOKEN=...   # e SEATS_AERO_KEY=... se tiver
python -m radar painel --sem-alertas

# "quero ir pra Maceió entre 10/12 e 15/01, ficando de 7 a 20 noites"
python -m radar datas MCZ --de 2026-12-10 --ate 2027-01-15 --min 7 --max 20

# "preciso de 32 mil pontos, de onde tiro? (Livelo com 100% de bônus)"
python -m radar pontos 32000 --bonus livelo=100
```

Testes: `pip install -e '.[dev]' && pytest`.

## Limitações honestas

- **Preços em reais** vêm do cache de buscas da Aviasales (últimos dias). Para rotas menos
  buscadas alguns dias ficam sem preço (cinza no calendário) e o valor pode ter mudado —
  por isso cada linha tem link para conferir no Google Voos e na Azul.
- **Pontos Azul** só são reais com o Seats.aero; sem ele é estimativa.
- **Promoções** são detectadas pelo título dos posts. O percentual mostrado é o "até X%"
  anunciado — o bônus que você recebe depende do Clube Azul e das regras de cada campanha.
- Transferência de pontos é **irreversível**: sempre confira a passagem antes de transferir.
