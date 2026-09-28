# ✈️ Radar de Passagens

Um radar pessoal que roda sozinho, de graça, no GitHub, e faz três coisas:

1. **Quando é mais barato ir para Maceió (ou Recife)?** Olha o mês inteiro, ida e volta
   separadas, e monta as melhores combinações respeitando quantas noites você quer ficar,
   em **reais** e em **pontos Azul**. Mostra um calendário colorido (verde = barato) e já
   diz se vale mais a pena usar pontos ou pagar em dinheiro.
2. **Para onde dá pra ir barato?** Lista as passagens de ida e volta mais baratas saindo de
   Belém para *qualquer* destino nos próximos meses (Lima, Fortaleza, São Luís...).
3. **Me avisa das promoções.** Lê os blogs de milhas (Passageiro de Primeira, Melhores
   Destinos, Pontos pra Voar) e manda uma **notificação no celular** quando aparece bônus de
   transferência Livelo/Inter → Azul, promoção saindo de Belém ou quando o preço cai /
   fica abaixo do alvo que você definiu.

Tudo aparece num painel web (funciona bem no celular) e os alertas chegam como notificação
push no Android, pelo app gratuito [ntfy](https://ntfy.sh).

## Como funciona

```
GitHub Actions (3x por dia)
   ├─ Google Voos             → menor preço em R$ de cada dia (calendário completo)
   ├─ Travelpayouts/Aviasales → cache de buscas: preços e destinos que outras pessoas acharam
   │     (as duas fontes são combinadas: em cada dia vale a mais barata)
   ├─ Seats.aero (opcional)   → resgates reais em pontos Azul Fidelidade
   └─ RSS dos blogs de milhas → promoções e bônus de transferência
        ↓
   calcula melhores datas, plano de pontos, compara com o histórico
        ↓
   painel (branch "painel", aberto pelo raw.githack.com)  +  notificação push (ntfy)
```

## Configurar (uns 20 minutos, uma vez só)

### 1. Token de preços (grátis, recomendado)
Os preços do Google Voos não precisam de chave. A Travelpayouts é uma segunda fonte que
complementa o Google e descobre destinos baratos: crie uma conta em
[travelpayouts.com](https://www.travelpayouts.com/), vá em **Perfil → API token** e copie o token.

### 2. Notificações no Android (grátis, sem cadastro)
1. Instale o **ntfy** pela [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   (ou F-Droid).
2. Invente um nome secreto e difícil de adivinhar para o seu canal, por exemplo
   `radar-passagens-k7q2m9xw4t`. **Quem souber esse nome consegue ler seus avisos**, então
   não use algo óbvio.
3. No app, toque em **+** → digite o nome → **Subscribe**.
4. Teste: abra `https://ntfy.sh/SEU_NOME` no navegador do computador, escreva uma mensagem e
   envie — ela deve aparecer no celular.
5. Para não perder alertas: em *Configurações do Android → Apps → ntfy → Bateria*, escolha
   **Sem restrições**.

Os avisos chegam com prioridade diferente:

| Aviso | Como chega |
|---|---|
| Bônus de transferência para a Azul · preço abaixo do seu alvo | **Urgente** (toca e vibra mais) |
| Queda de preço · destino barato | Normal |
| Outras promoções de passagem | Discreta |

Se houver muitos avisos de uma vez, chegam os 5 mais importantes e um resumo com o resto.
Tocar na notificação abre o link da passagem ou da promoção.

### 3. Pontos Azul
**Grátis (estimativa calibrada):** o radar busca o preço **só da Azul** em R$ e converte
em pontos. Para a conta ficar boa, anote de vez em quando no arquivo
[`pontos_azul.yaml`](pontos_azul.yaml) alguns preços em pontos que você viu no site da Azul
(data, trecho e pontos; o preço em R$ do mesmo voo é opcional). O radar aprende quantos
pontos vale cada real nas suas rotas. Sem anotações, usa a régua `valor_milheiro_azul`.

**Pago (valor exato):** assine o [Seats.aero Pro](https://seats.aero/) (~US$ 10/mês, dá
para assinar só nos meses em que estiver planejando) e cadastre a chave no segredo
`SEATS_AERO_KEY`.

### 4. Colocar no GitHub
No repositório: **Settings → Secrets and variables → Actions → New repository secret**:

| Segredo | Valor |
|---|---|
| `TRAVELPAYOUTS_TOKEN` | token do passo 1 |
| `NTFY_TOPIC` | o nome secreto do passo 2 |
| `SEATS_AERO_KEY` | (opcional) chave do Seats.aero |
| `SALDOS` | (opcional) ex.: `azul=12000,livelo=45000,cartao=20000` — assim seus saldos não ficam públicos |

Depois: em **Actions → Radar de passagens → Run workflow** você roda na hora; depois ele
roda sozinho 3x por dia.

O painel fica salvo no branch `painel` do repositório e abre em:

**https://raw.githack.com/SEU_USUARIO/travelling/painel/index.html**

(O [raw.githack.com](https://raw.githack.com/) é um serviço gratuito que mostra como página
um arquivo HTML guardado no GitHub. Depois de cada atualização, pode levar alguns minutos
para a versão nova aparecer.) O endereço também aparece no resumo de cada execução da Action e
no botão "Ver painel" das notificações. Para usar outro endereço (por exemplo, um subdomínio
seu no GitHub Pages), crie a *variable* `DASHBOARD_URL` em **Settings → Secrets and variables →
Actions → Variables**.

> **Privacidade:** o repositório é público, então o painel também é (quem souber o endereço
> consegue abrir). Os tokens e o canal de notificação ficam nos segredos e nunca aparecem. Os
> saldos de pontos, se configurados no segredo `SALDOS`, não ficam no código, mas aparecem no
> painel.

### 5. Ajustar ao seu gosto
Tudo fica em [`config.yaml`](config.yaml):
- **quem viaja** (`viajantes`): hoje Família (2 adultos + 3 crianças) e Casal. Os preços
  são buscados já para o grupo inteiro e o painel mostra total e por pessoa. O primeiro
  grupo é o usado em "Oportunidades" e nos alertas;
- destinos, janelas de viagem (ex.: "Fim de ano, de 12/12 a 15/01, de 7 a 21 noites");
- preço-alvo **por pessoa** de cada rota (e, se quiser, um custo extra somado ao total,
  com `custo_extra_reais`);
- a lista de destinos candidatos para "Oportunidades" (conferidos em rodízio, 15 por
  rodada) e o preço máximo por pessoa para avisar;
- proporção e bônus de cada programa de pontos.

## Usar no computador (opcional)

```bash
pip install -e .

# painel com dados fictícios, sem precisar de nenhuma chave
python -m radar --demo painel --sem-alertas      # abre site/index.html

# com dados reais
export TRAVELPAYOUTS_TOKEN=...   # e SEATS_AERO_KEY=... se tiver
python -m radar painel --sem-alertas

# "quero ir pra Maceió entre 10/12 e 15/01, ficando de 7 a 20 noites" (família: 2 + 3)
python -m radar datas MCZ --de 2026-12-10 --ate 2027-01-15 --min 7 --max 20 --adultos 2 --criancas 3

# "preciso de 32 mil pontos, de onde tiro? (Livelo com 100% de bônus)"
python -m radar pontos 32000 --bonus livelo=100
```

Testes: `pip install -e '.[dev]' && pytest`.

## Limitações honestas

- **Preços em reais** combinam duas fontes. O Google Voos traz o menor preço de cada dia, mas
  é acessado por uma biblioteca não oficial ([fli](https://github.com/punitarani/fli)): se o
  Google mudar algo, pode parar até a biblioteca ser atualizada. A Travelpayouts é oficial,
  mas só tem o que outras pessoas buscaram nos últimos dias (para Belém–Maceió quase nada).
  Se uma fonte falhar, o radar segue com a outra e mostra o problema em "Avisos" no painel.
  Para investigar, rode a Action **Diagnóstico de preços**: ela mostra quantos preços cada
  fonte trouxe para cada trecho.
- **Pontos Azul** só são exatos com o Seats.aero; sem ele é estimativa (melhor quanto mais
  anotações houver em `pontos_azul.yaml`).
- **Preços da Travelpayouts** são sempre de 1 adulto; para grupos o radar multiplica e
  marca a fonte como "estimado". Os do Google Voos já vêm para o grupo inteiro.
- **Promoções** são detectadas pelo título dos posts. O percentual mostrado é o "até X%"
  anunciado — o bônus que você recebe depende do Clube Azul e das regras de cada campanha.
- Transferência de pontos é **irreversível**: sempre confira a passagem antes de transferir.
