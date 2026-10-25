# Valorant Dashboard & Tracker 🎮

Um painel web responsivo construído com **Python (Flask)** que permite aos jogadores de Valorant acompanhar suas estatísticas, histórico de partidas, métricas de desempenho e até mesmo assistir a streams da Twitch e ler as últimas notícias oficiais do jogo, tudo em um só lugar.

## 🌐 Acesso Online (Live Demo)

O projeto está atualmente hospedado e rodando ao vivo através do **Render**. Você pode acessar e testar o dashboard diretamente, sem precisar instalar nada, através do link abaixo:

🔗 **[https://dashboard-valorant.onrender.com](https://dashboard-valorant.onrender.com)**

---

## ✨ Funcionalidades

* **Perfil do Jogador:** Exibe Nível, Rank Atual, RR (Rank Rating), variação de RR na última partida e o Peak Rank (Elo Máximo).

* **Estatísticas Detalhadas:** Cálculo de Win Rate, K/D Médio, HS% e ACS baseados nas últimas 30 partidas competitivas.

* **Resumo All-Time (Lifetime):** Total de jogos, vitórias, derrotas e taxa de vitória geral da conta.

* **Top Agentes e Top Mapas:** Lista de desempenho com os agentes mais escolhidos e os mapas mais jogados, ordenados por taxa de vitórias.

* **Histórico de Partidas:** Tabela completa com as partidas recentes, incluindo placar pessoal e acesso aos detalhes.

* **Scoreboard Específico (Match):** Visão detalhada de uma partida (Time A vs Time B) com estatísticas de todos os 10 jogadores.

* **Integração com a Twitch:** Mostra os principais canais brasileiros transmitindo Valorant ao vivo no momento.

* **Últimas Notícias:** Web scraping automático que exibe os últimos artigos publicados no site oficial do Valorant.

* **Histórico de Pesquisa:** Salva localmente as últimas contas pesquisadas para acesso rápido.

## 🛠️ Tecnologias Utilizadas

* **Backend:** Python 3.x, Flask, Gunicorn (para deploy no Render)

* **Integrações/APIs:** `requests`

* **Web Scraping:** `beautifulsoup4`

* **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5, Fontes (Bebas Neue, Montserrat)

* **Variáveis de Ambiente:** `python-dotenv`

## 🔌 APIs e Fontes de Dados

Este projeto consome dados de três fontes principais:

1. [**HenrikDev API**](https://github.com/Henrik-3/unofficial-valorant-api): Usada para buscar dados do jogador, MMR e histórico de partidas.

2. [**Valorant-API (Comunidade)**](https://valorant-api.com/): Usada para buscar imagens oficiais (ícones de agentes, banners de mapas, ícones de elo).

3. [**Twitch API**](https://dev.twitch.tv/docs/api/): Usada para buscar os streamers ao vivo.

## 🚀 Como Rodar o Projeto Localmente

### 1. Pré-requisitos

* Python 3.8 ou superior instalado.

* Chaves de API da HenrikDev e da Twitch.

### 2. Clonar o Repositório

```bash
git clone https://github.com/kevenborges/dashboard-valorant.git
cd dashboard-valorant
```

### 3. Criar o Ambiente Virtual (Opcional, mas recomendado)

```bash
python -m venv venv
# Ativar no Windows:
venv\Scripts\activate
# Ativar no Linux/Mac:
source venv/bin/activate
```

### 4. Instalar as Dependências

```bash
pip install -r requirements.txt
```

### 5. Configurar as Variáveis de Ambiente

Crie um arquivo chamado `.env` na raiz do projeto e adicione suas credenciais:

```env
HENRIK_API_KEY=sua_chave_henrikdev_aqui
TWITCH_CLIENT_ID=seu_client_id_da_twitch
TWITCH_TOKEN=seu_token_da_twitch
```

*(Nota: Você pode usar o script `gerar_token_2.py` incluído no projeto para gerar um novo token da Twitch via Client Credentials).*

### 6. Iniciar o Servidor

```bash
python app.py
```

O servidor será iniciado. Abra o navegador e acesse: `http://127.0.0.1:5000/`

## 📝 Estrutura do Projeto

* `app.py`: Servidor backend principal com todas as rotas e lógicas de chamadas de API.

* `gerar_token_2.py`: Script auxiliar para gerar tokens de autenticação da Twitch.

* `templates/index.html`: Página inicial com o formulário de busca e histórico salvo no navegador.

* `templates/dashboard.html`: Página principal contendo o painel completo do usuário.

* `templates/match.html`: Página de detalhes (Scoreboard) de uma partida específica.

## 🤝 Contribuição

Sinta-se à vontade para abrir *Issues* ou enviar *Pull Requests*. Toda contribuição para melhorar a interface ou a lógica de tratamento da API é bem-vinda!

## 📄 Licença

Este projeto é de uso livre. As marcas Valorant e Riot Games são propriedades da Riot Games, Inc. Este projeto não é endossado pela Riot Games.