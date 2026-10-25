# =============================================================================
# app.py — Servidor Flask do Valorant Dashboard
# Descrição: Aplicação web que consome as APIs da HenrikDev, Valorant-API e Twitch,
# além de fazer web scraping das notícias oficiais do Valorant.
# =============================================================================

import os
import time
from datetime import datetime
from collections import defaultdict
from functools import lru_cache

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request
from dotenv import load_dotenv

# Carrega as variáveis de ambiente contidas no arquivo .env
load_dotenv()

app = Flask(__name__)

# Resgata as chaves de API do ambiente (ou retorna string vazia se não existirem)
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID', '')
TWITCH_TOKEN     = os.getenv('TWITCH_TOKEN', '')
HENRIK_API_KEY   = os.getenv('HENRIK_API_KEY', '')

# URL base para a API oficial não-autenticada da Riot Games (fornecida pela comunidade)
VALORANT_API_URL = "https://valorant-api.com/v1"

# =============================================================================
# FUNÇÕES DE INTEGRAÇÃO COM VALORANT-API (ASSETS E IMAGENS)
# =============================================================================

@lru_cache(maxsize=20)
def consultar_valorant_api(endpoint):
    """
    Faz uma requisição para a Valorant-API.
    Utiliza @lru_cache para guardar em memória os últimos 20 resultados,
    evitando atrasos e requisições repetidas para imagens de mapas e agentes.
    """
    url = f"{VALORANT_API_URL}/{endpoint}"
    try:
        resposta = requests.get(url, timeout=10)
        resposta.raise_for_status()
        return resposta.json().get("data", [])
    except (requests.RequestException, ValueError) as erro:
        app.logger.warning(f"Erro na Valorant-API: {erro}")
        return []

def obter_agentes_api(): 
    """Busca a lista oficial de todos os agentes jogáveis e seus ícones em PT-BR."""
    return consultar_valorant_api("agents?language=pt-BR&isPlayableCharacter=true")

def obter_mapas_api():   
    """Busca a lista oficial de todos os mapas e suas miniaturas em PT-BR."""
    return consultar_valorant_api("maps?language=pt-BR")

# =============================================================================
# FUNÇÕES DE INTEGRAÇÃO COM HENRIKDEV API (ESTATÍSTICAS)
# =============================================================================

def _headers_henrik(): 
    """Retorna o cabeçalho de autenticação necessário para usar a API da HenrikDev."""
    return {'Authorization': HENRIK_API_KEY}

# Cache manual de memória para os ícones de Rank/Elo para evitar chamadas contínuas
_RANK_ICONS_CACHE = {'ts': 0, 'mapa': {}}

def obter_icone_elo(nome_rank):
    """
    Recebe o nome de um Elo (ex: 'Radiant', 'Diamond 1') e busca na 
    Valorant-API a imagem correspondente. Usa um cache local com tempo de 
    expiração de 24 horas.
    """
    if not nome_rank: return ''
    agora = time.time()
    
    # Se o cache existe e tem menos de 24h, retorna do cache
    if _RANK_ICONS_CACHE['mapa'] and agora - _RANK_ICONS_CACHE['ts'] < 24 * 60 * 60:
        return _RANK_ICONS_CACHE['mapa'].get(nome_rank.lower(), '')
    
    # Caso contrário, renova o cache consumindo a API
    try:
        resposta = requests.get('https://valorant-api.com/v1/competitivetiers', timeout=10)
        resposta.raise_for_status()
        mapa = {}
        # Navega pelas versões de tiers competitivos para encontrar os nomes e ícones
        for versao in resposta.json().get('data', []):
            for tier in versao.get('tiers', []):
                nome = (tier.get('tierName') or '').strip().lower()
                icone = tier.get('largeIcon') or tier.get('smallIcon') or ''
                if nome and icone: mapa[nome] = icone
        
        # Atualiza o cache global
        _RANK_ICONS_CACHE.update(ts=agora, mapa=mapa)
        return mapa.get(nome_rank.strip().lower(), '')
    except:
        # Em caso de erro, tenta retornar qualquer coisa residual do cache
        return _RANK_ICONS_CACHE['mapa'].get(nome_rank.strip().lower(), '')

def obter_dados_valorant(jogador, tag):
    """
    Busca os dados básicos da conta (Nível, Playercard, Região) no endpoint v1/account,
    e depois busca os dados de Elo atual e Peak Rating (Elo Máximo) no endpoint v2/mmr.
    Retorna um dicionário compilado.
    """
    headers = _headers_henrik()
    
    # 1. Requisição de Conta
    url_conta = f"https://api.henrikdev.xyz/valorant/v1/account/{jogador}/{tag}"
    resposta_conta = requests.get(url_conta, headers=headers, timeout=10)
    if resposta_conta.status_code != 200: return None

    dados_conta = resposta_conta.json()
    regiao = dados_conta['data']['region']

    # 2. Requisição de MMR (Elo e Histórico de Temporadas)
    url_mmr = f"https://api.henrikdev.xyz/valorant/v2/mmr/{regiao}/{jogador}/{tag}"
    resposta_mmr = requests.get(url_mmr, headers=headers, timeout=10)
    if resposta_mmr.status_code != 200: return None

    dados_mmr = resposta_mmr.json().get('data', {})
    atual = dados_mmr.get('current_data') or {}
    
    # Se o jogador não tem um rank válido, interrompe
    if not atual.get('currenttierpatched'): return None

    peak = dados_mmr.get('highest_rank') or {}
    
    # Dicionário com o compilado das informações do usuário
    return {
        "rank":          atual.get('currenttierpatched'),
        "pontos_rr":     atual.get('ranking_in_tier') or 0,
        "rr_change":     atual.get('mmr_change_to_last_game'),
        "imagem_rank":   (atual.get('images') or {}).get('large', ''),
        "avatar":        dados_conta['data']['card']['small'],
        "nivel":         dados_conta['data']['account_level'],
        "regiao":        regiao,
        "peak_rank":     peak.get('patched_tier') or '',
        "peak_imagem":   (peak.get('images') or {}).get('large', '') or obter_icone_elo(peak.get('patched_tier') or ''),
        "peak_season":   peak.get('season') or '',
        "by_season":     dados_mmr.get('by_season') or {}, # Contém os dados para calcular o All-Time stats
    }

def obter_historico_partidas(jogador, tag, regiao):
    """
    Busca as últimas 30 partidas competitivas jogadas pelo usuário.
    Gera as estatísticas médias (KD, ACS, HS%, Win Rate),
    lista a sequência recente e compila os Top Agentes e Top Mapas.
    """
    if not HENRIK_API_KEY:
        return [], {}, [], []

    headers = _headers_henrik()
    tamanho_pagina = 20
    # Busca até 2 páginas (40 partidas no total) para garantirmos ter pelo menos 30 competitivas
    max_paginas = 2  
    partidas_brutas = []
    ids_vistos = set() # Evita partidas duplicadas

    # Loop de paginação
    for pagina in range(max_paginas):
        inicio = pagina * tamanho_pagina
        url = (
            f"https://api.henrikdev.xyz/valorant/v4/matches/"
            f"{regiao}/pc/{requests.utils.quote(jogador, safe='')}/"
            f"{requests.utils.quote(tag, safe='')}"
        )
        try:
            # Requisita com filtro 'mode=competitive' para otimizar a resposta
            resposta = requests.get(
                url, headers=headers, params={'mode': 'competitive', 'size': tamanho_pagina, 'start': inicio}, timeout=15
            )
        except requests.RequestException:
            break
            
        # Tratamento de Rate Limit: Se a API der erro 429 (Muitas requisições), pausa 2s e tenta novamente
        if resposta.status_code == 429:
            time.sleep(2)
            try:
                resposta = requests.get(
                    url, headers=headers, params={'mode': 'competitive', 'size': tamanho_pagina, 'start': inicio}, timeout=15
                )
            except:
                break

        if resposta.status_code != 200:
            break

        try:
            lote = resposta.json().get('data') or []
        except ValueError:
            break
            
        if not lote:
            break

        # Processa as partidas que chegaram na página atual
        for match in lote:
            meta = match.get('metadata') or {}
            match_id = meta.get('match_id') or meta.get('matchid') or meta.get('id') or ''
            if match_id and match_id in ids_vistos: continue
            if match_id: ids_vistos.add(match_id)
            partidas_brutas.append(match)
            
        if len(lote) < tamanho_pagina:
            break
            
        # Pausa sutil entre as páginas para não ser banido pela API
        if pagina < max_paginas - 1:
            time.sleep(0.5)

    # Garante que só processaremos exatamente as últimas 30 partidas
    partidas_brutas = partidas_brutas[:30]

    partidas_completas = []
    agentes_stats = defaultdict(lambda: {'jogos': 0, 'vitorias': 0, 'icone': ''})
    mapas_stats = defaultdict(lambda: {'jogos': 0, 'vitorias': 0})
    
    # Carrega os assets oficiais para preencher imagens bonitas
    agentes_api = {a['displayName'].lower(): a['displayIcon'] for a in obter_agentes_api() if 'displayName' in a}
    mapas_api = {m['displayName'].lower(): m['listViewIcon'] for m in obter_mapas_api() if 'displayName' in m}

    # Helper function para extrair textos de chaves aninhadas json
    def texto(valor, padrao=''):
        if isinstance(valor, dict): return valor.get('name') or valor.get('value') or valor.get('id') or padrao
        return valor if valor not in (None, '') else padrao

    def normalizar_team(valor):
        valor = str(valor or '').strip().lower()
        if valor in ('red', 'blue'): return valor
        if valor.endswith('red'): return 'red'
        if valor.endswith('blue'): return 'blue'
        return valor

    # Loop principal processando estatísticas individuais de CADA partida
    for match in partidas_brutas:
        info = match.get('metadata') or {}
        players = match.get('players') or {}
        
        # Isola a lista de jogadores da partida
        if isinstance(players, dict): todos_jogadores = players.get('all_players') or players.get('players') or []
        elif isinstance(players, list): todos_jogadores = players
        else: todos_jogadores = []

        # Localiza o usuário específico no meio dos 10 jogadores
        jogador_dados = next((p for p in todos_jogadores
            if str(p.get('name') or p.get('game_name') or '').lower() == jogador.lower()
            and str(p.get('tag') or p.get('tag_line') or '').lower() == tag.lower()), None)
        if not jogador_dados: continue

        # Extração crua dos números
        stats_p = jogador_dados.get('stats') or {}
        kills = int(stats_p.get('kills') or 0)
        deaths = int(stats_p.get('deaths') or 0)
        assists = int(stats_p.get('assists') or 0)
        score = int(stats_p.get('score') or stats_p.get('combat_score') or 0)
        headshots = int(stats_p.get('headshots') or 0)
        bodyshots = int(stats_p.get('bodyshots') or 0)
        legshots = int(stats_p.get('legshots') or 0)
        total_tiros = headshots + bodyshots + legshots

        # Determinando total de rounds (necessário para calcular o ACS médio)
        rounds_jogados = info.get('rounds_played') or info.get('rounds')
        if isinstance(rounds_jogados, list): rounds_jogados = len(rounds_jogados)
        if not rounds_jogados: rounds_jogados = len(match.get('rounds') or [])
        if not rounds_jogados:
            teams_data = match.get('teams') or []
            if isinstance(teams_data, list): rounds_jogados = max([int(t.get('rounds_played') or 0) for t in teams_data] or [0])
            else: rounds_jogados = 0
        rounds_jogados = int(rounds_jogados or 0)

        # Filtro de segurança para ignorar deathmatches que a API tenha mandado sem querer
        modo = str(texto(info.get('mode') or info.get('queue'), 'Competitive'))
        if modo.lower() not in ('competitive', 'competitiva', 'ranked', 'competitivo'): continue
        
        # Cálculo de grandezas relativas da partida
        acs = round(score / rounds_jogados, 1) if rounds_jogados > 0 else None
        hs_pct = round((headshots / total_tiros) * 100, 1) if total_tiros > 0 else 0.0

        # Parseamento e formatação de Data
        inicio = info.get('game_start') or info.get('started_at') or info.get('game_start_patched')
        data_partida = ''
        if inicio:
            try:
                if isinstance(inicio, (int, float)) or str(inicio).isdigit():
                    data_partida = datetime.fromtimestamp(int(inicio)).strftime('%d/%m/%Y')
                else:
                    data_partida = datetime.fromisoformat(str(inicio).replace('Z', '+00:00')).strftime('%d/%m/%Y')
            except: data_partida = str(info.get('game_start_patched') or '')

        # Verifica qual time ganhou e se o jogador estava nele
        times_raw = match.get('teams') or []
        times_vencedores = set()
        if isinstance(times_raw, dict):
            for team_name, team_data in times_raw.items():
                if team_data.get('has_won') is True or team_data.get('won') is True:
                    times_vencedores.add(normalizar_team(team_name))
        elif isinstance(times_raw, list):
            for team_data in times_raw:
                if team_data.get('won') is True or team_data.get('has_won') is True:
                    times_vencedores.add(normalizar_team(team_data.get('team_id') or team_data.get('team') or team_data.get('name')))

        equipe_jogador = normalizar_team(jogador_dados.get('team') or jogador_dados.get('team_id'))
        venceu = equipe_jogador in times_vencedores if equipe_jogador else False

        mapa = str(texto(info.get('map'), 'N/A'))
        agente = str(texto(jogador_dados.get('character') or jogador_dados.get('agent'), 'N/A'))
        assets = jogador_dados.get('assets') or {}
        agent_assets = assets.get('agent') or assets.get('agent') or {}
        
        # Pega a imagem do agente na Riot, fallback para imagem da HenrikDev
        icone_henrik = (agent_assets.get('small') or agent_assets.get('bust') or '') if isinstance(agent_assets, dict) else ''
        icone = agentes_api.get(agente.lower(), icone_henrik)
        match_id = info.get('match_id') or info.get('matchid') or info.get('id') or ''

        # Incrementa os contadores dos cards "Top Agentes" e "Top Mapas"
        agentes_stats[agente]['jogos'] += 1
        agentes_stats[agente]['vitorias'] += int(venceu)
        agentes_stats[agente]['icone'] = icone
        mapas_stats[mapa]['jogos'] += 1
        mapas_stats[mapa]['vitorias'] += int(venceu)

        # Adiciona a partida processada ao array final
        partidas_completas.append({
            'match_id': match_id, 'mapa': mapa, 'modo': modo,
            'data': data_partida, 'agente': agente, 'agente_icone': icone,
            'kills': kills, 'deaths': deaths, 'assists': assists,
            'kd': round(kills / max(deaths, 1), 2), 'acs': acs,
            'hs_pct': hs_pct, 'resultado': equipe_jogador,
            'time_vencedor': next(iter(times_vencedores), ''), 'venceu': venceu,
            '_shots': total_tiros, '_headshots': headshots,
        })

    # Garante ordem decrescente (da mais nova pra mais velha)
    partidas_completas.sort(key=lambda p: datetime.strptime(p['data'], '%d/%m/%Y') if p.get('data') else datetime.min, reverse=True)

    if not partidas_completas:
        return [], {}, [], []

    # =========================================================================
    # CÁLCULOS DO RESUMO DE 30 PARTIDAS
    # =========================================================================
    total = len(partidas_completas)
    vitorias = sum(1 for p in partidas_completas if p['venceu'])
    kills_total = sum(p['kills'] for p in partidas_completas)
    deaths_total = sum(p['deaths'] for p in partidas_completas)
    assists_total = sum(p['assists'] for p in partidas_completas)
    total_tiros = sum(p['_shots'] for p in partidas_completas)
    total_headshots = sum(p['_headshots'] for p in partidas_completas)
    acs_validos = [p['acs'] for p in partidas_completas if p['acs'] is not None]

    stats_gerais = {
        'total': total,
        'vitorias': vitorias,
        'derrotas': total - vitorias,
        'win_rate': round((vitorias / total) * 100, 1),
        'kd_medio': round(kills_total / max(deaths_total, 1), 2),
        'hs_medio': round((total_headshots / total_tiros) * 100, 1) if total_tiros else 0.0,
        'acs_medio': round(sum(acs_validos) / len(acs_validos), 1) if acs_validos else 0.0,
        'kills_total': kills_total, 'deaths_total': deaths_total,
        'assists_total': assists_total,
        'sequencia': ['V' if p['venceu'] else 'D' for p in partidas_completas[:20]], # Pega sequência das mais recentes
    }

    # ── TOP AGENTES: Todos jogáveis ──
    # Primeiro transforma os que ele de fato jogou num dict mapeado
    agentes_jogados = {
        nome: {
            'agente':   nome,
            'jogos':    dados['jogos'],
            'vitorias': dados['vitorias'],
            'win_rate': round(dados['vitorias'] / dados['jogos'] * 100, 1),
            'icone':    dados['icone'],
        }
        for nome, dados in agentes_stats.items()
    }

    # E agora adiciona os agentes que ele NÃO jogou com 0W 0L vindos da Valorant-API
    for agente_api_dados in obter_agentes_api():
        nome_agente = agente_api_dados.get('displayName', '')
        if not nome_agente:
            continue
        if nome_agente not in agentes_jogados:
            agentes_jogados[nome_agente] = {
                'agente':   nome_agente,
                'jogos':    0,
                'vitorias': 0,
                'win_rate': 0.0,
                'icone':    agente_api_dados.get('displayIcon', ''),
            }
        else:
            # Caso a imagem da HenrikDev falhe, garante fallback pela Riot oficial
            if not agentes_jogados[nome_agente]['icone']:
                agentes_jogados[nome_agente]['icone'] = agente_api_dados.get('displayIcon', '')

    # Converte para array e ordena (Mais jogos no topo. Empates organizados alfabeticamente)
    top_agentes = sorted(
        agentes_jogados.values(),
        key=lambda item: (-item['jogos'], -item['win_rate'], item['agente'])
    )[:14]

    # ── TOP MAPAS: Todos competitivos ──
    # Mapas de tutorial ou modes de jogo zoeiros excluídos
    mapas_excluidos = {
        'the range', 'district', 'kasbah', 'piazza',
        'drift', 'glitch', 'foxtrot'
    }

    # Mapeia os mapas que o usuário jogou
    mapas_jogados = {
        nome: {
            'mapa':     nome,
            'jogos':    dados['jogos'],
            'vitorias': dados['vitorias'],
            'derrotas': dados['jogos'] - dados['vitorias'],
            'win_rate': round(dados['vitorias'] / dados['jogos'] * 100, 1),
            'icone':    mapas_api.get(nome.lower(), ''),
        }
        for nome, dados in mapas_stats.items()
    }

    # Injeta os mapas oficiais competitivos que ele não caiu na fila recente (Com 0% winrate)
    for mapa_api_dados in obter_mapas_api():
        nome_mapa = mapa_api_dados.get('displayName', '')
        if not nome_mapa or nome_mapa.lower() in mapas_excluidos:
            continue
        # Na Valorant API, mapas casuais não tem descrição tática. Removemos eles.
        if not mapa_api_dados.get('tacticalDescription'):
            continue
        
        if nome_mapa not in mapas_jogados:
            mapas_jogados[nome_mapa] = {
                'mapa':     nome_mapa,
                'jogos':    0,
                'vitorias': 0,
                'derrotas': 0,
                'win_rate': 0.0,
                'icone':    mapa_api_dados.get('listViewIcon', ''),
            }
        else:
            if not mapas_jogados[nome_mapa]['icone']:
                mapas_jogados[nome_mapa]['icone'] = mapa_api_dados.get('listViewIcon', '')

    # Converte e ordena (Mapas mais jogados no topo)
    top_mapas = sorted(
        mapas_jogados.values(),
        key=lambda item: (-item['jogos'], -item['win_rate'], item['mapa'])
    )[:14]

    # Limpa as variáveis sujas e escondidas usadas apenas para cálculos
    for partida in partidas_completas:
        partida.pop('_shots', None)
        partida.pop('_headshots', None)
        
    return partidas_completas, stats_gerais, top_agentes, top_mapas

def obter_scoreboard(match_id):
    """
    Quando o usuário clica em "Ver Partida", essa função busca a página específica do jogo
    para renderizar a tabela dividida entre Time A vs Time B com todos os 10 jogadores.
    """
    headers = {'Authorization': HENRIK_API_KEY}
    resposta = requests.get(f"https://api.henrikdev.xyz/valorant/v2/match/{match_id}", headers=headers, timeout=10)
    if resposta.status_code != 200: return None

    dados = resposta.json().get('data', {})
    info  = dados.get('metadata', {})
    modo  = info.get('mode', '')

    # O Deathmatch (Mata-Mata) não possui lógica de 2 times. Portanto bloqueamos.
    if modo.lower() == 'deathmatch': return None

    times = dados.get('teams', {})
    time_vencedor = ''
    for nome_time, dados_time in times.items():
        if dados_time.get('has_won'):
            time_vencedor = nome_time.lower()
            break
            
    # Mais uma vez, cache local para preencher os rostos no scoreboard
    agentes_api = {a['displayName'].lower(): a['displayIcon'] for a in obter_agentes_api() if 'displayName' in a}

    def tratar_jogador(p):
        """Mapeia os campos da API da Henrik em um dicionário simplificado para o HTML"""
        stats       = p.get('stats', {})
        kills       = stats.get('kills', 0)
        deaths      = stats.get('deaths', 0)
        assists     = stats.get('assists', 0)
        score       = stats.get('score', 0)
        headshots   = stats.get('headshots', 0)
        bodyshots   = stats.get('bodyshots', 0)
        legshots    = stats.get('legshots', 0)
        total_tiros = headshots + bodyshots + legshots
        rounds      = info.get('rounds_played', 1)
        agente      = p.get('character', 'N/A')
        
        icone = agentes_api.get(agente.lower(), p.get('assets', {}).get('agent', {}).get('small', ''))

        return {
            "nome":         p.get('name', 'N/A'),
            "tag":          p.get('tag', ''),
            "team":         p.get('team', '').lower(),
            "agente":       agente,
            "agente_icone": icone,
            "kills":        kills,
            "deaths":       deaths,
            "assists":      assists,
            "kd":           round(kills / max(deaths, 1), 2),
            "acs":          round(score / max(rounds, 1), 1),
            "hs_pct":       round((headshots / total_tiros) * 100, 1) if total_tiros > 0 else 0,
            "adr":          round(p.get('damage_made', 0) / max(rounds, 1), 1),
        }

    todos  = dados.get('players', {}).get('all_players', [])
    # Separação por atacantes vs defensores que iniciaram a partida
    time_a = [tratar_jogador(p) for p in todos if p.get('team', '').lower() == 'red']
    time_b = [tratar_jogador(p) for p in todos if p.get('team', '').lower() == 'blue']

    # O MVP (maior acs) fica sempre no topo da tabela
    time_a.sort(key=lambda p: p['acs'], reverse=True)
    time_b.sort(key=lambda p: p['acs'], reverse=True)

    return {
        "mapa":          info.get('map', 'N/A'),
        "modo":          modo,
        "time_a":        time_a,
        "time_b":        time_b,
        "time_vencedor": time_vencedor,
        "placar_a":      times.get('red',  {}).get('rounds_won', 0),
        "placar_b":      times.get('blue', {}).get('rounds_won', 0),
    }

def obter_streams_twitch():
    """
    Chama a Twitch API filtrando o jogo Valorant (game_id 516575) para o idioma português.
    Retorna os top 6 canais ao vivo.
    """
    if not TWITCH_CLIENT_ID or not TWITCH_TOKEN: return []
    headers = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {TWITCH_TOKEN}'}
    resposta = requests.get("https://api.twitch.tv/helix/streams?game_id=516575&language=pt&first=6", headers=headers, timeout=10)
    
    # Substitui macros {width}/{height} na URL da thumbnail retornada pela Twitch
    if resposta.status_code == 200:
        return [{"streamer": s['user_name'], "titulo": s['title'], "thumbnail": s['thumbnail_url'].replace('{width}', '320').replace('{height}', '180'), "link": f"https://twitch.tv/{s['user_name']}", "viewers_fmt": f"{s.get('viewer_count', 0):,}".replace(',', '.')} for s in resposta.json().get('data', [])]
    return []

def obter_noticias():
    """
    Usa a biblioteca BeautifulSoup para raspar (scrape) a página inicial
    oficial de notícias do Valorant, retornando imagem e titulo das 6 notícias.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'}
    try:
        resposta = requests.get("https://playvalorant.com/pt-br/news/", headers=headers, timeout=10)
        if resposta.status_code != 200: return []
        
        soup = BeautifulSoup(resposta.text, 'html.parser')
        noticias = []
        
        # O site oficial possui os cards de noticia envelopados na div contentList-item
        for card in soup.select('a[data-testid="contentList-item"]')[:6]:
            titulo_el = card.select_one('[class*="title"]') or card.select_one('h2, h3, h4')
            cat_el = card.select_one('[class*="category"]') or card.select_one('[class*="label"]')
            img_el = card.select_one('img')
            href = card.get('href', '')
            
            # Se o href for relativo, completa a url
            link = f"https://playvalorant.com{href}" if href.startswith('/') else href
            
            if titulo_el and link:
                noticias.append({
                    "titulo": titulo_el.get_text(strip=True),
                    "categoria": cat_el.get_text(strip=True) if cat_el else 'Notícia',
                    "thumbnail": img_el.get('src', '') if img_el else '',
                    "link": link,
                })
        return noticias
    except: return []

# =============================================================================
# ENDPOINTS (ROTAS DO FLASK)
# =============================================================================

@app.route('/')
def index():
    """Exibe o formulário inicial para o usuário digitar RIOT_ID e TAGLINE"""
    return render_template('index.html')

@app.route('/dashboard', methods=['POST'])
def dashboard():
    """
    Rota que recebe o formulário via POST. Responsável por orquestrar
    a busca nas APIs e compilar todos os resultados para enviar ao HTML.
    """
    riot_id = request.form.get('riot_id', '').strip()
    tagline = request.form.get('tagline', '').strip()

    # Dispara as requisições em paralelo
    dados_jogador        = obter_dados_valorant(riot_id, tagline)
    streams_recomendadas = obter_streams_twitch()
    noticias             = obter_noticias()

    historico = []
    stats_30 = {}
    stats_all_time = {}
    top_agentes = []
    top_mapas = []

    if dados_jogador:
        regiao = dados_jogador['regiao']
        # by_season é removido de dados_jogador e processado para All-Time stats
        by_season = dados_jogador.pop('by_season', {}) or {}
        
        # 1. Busca Histórico (Últimas 30 Partidas)
        historico, stats_30, top_agentes, top_mapas = obter_historico_partidas(riot_id, tagline, regiao)

        # 2. Compila os Dados Gerais (All-Time) através do histórico de MMR oculto na API
        lifetime_jogos = 0
        lifetime_vitorias = 0
        
        # Itera por todas as temporadas listadas no JSON
        for season, s_data in by_season.items():
            if isinstance(s_data, dict) and not s_data.get('error'):
                lifetime_jogos += s_data.get('number_of_games', 0)
                lifetime_vitorias += s_data.get('wins', 0)
                
        if lifetime_jogos > 0:
            lifetime_wr = round((lifetime_vitorias / lifetime_jogos) * 100, 1)
            
            # K/D e HS% não são fornecidos num contexto de lifetime, então
            # transportamos a amostra das últimas 30 partidas para servir de estimativa global
            kd_geral = stats_30.get('kd_medio', 0)
            hs_geral = stats_30.get('hs_medio', 0)
            stats_all_time = {
                'jogos':    lifetime_jogos,
                'vitorias': lifetime_vitorias,
                'derrotas': lifetime_jogos - lifetime_vitorias,
                'win_rate': lifetime_wr,
                'kd':       kd_geral,
                'hs':       hs_geral,
            }

    # Despeja as variáveis pro Jinja compilar o HTML
    return render_template(
        'dashboard.html',
        jogador=riot_id,
        tagline=tagline,
        status_jogador=dados_jogador,
        streams=streams_recomendadas,
        historico=historico,
        stats=stats_30,
        stats_all_time=stats_all_time,
        noticias=noticias,
        top_agentes=top_agentes,
        top_mapas=top_mapas,
    )

@app.route('/match/<match_id>')
def match(match_id):
    """
    Rota responsável por renderizar os detalhes (placar, combat score de cada um dos 10)
    de uma match id (UUID) específica clicada no histórico.
    """
    jogador = request.args.get('jogador', '')
    tagline = request.args.get('tag', '')
    scoreboard = obter_scoreboard(match_id)

    if not scoreboard:
        return render_template('index.html', erro="Esta partida é um Deathmatch e não possui scoreboard por times.")

    return render_template('match.html', scoreboard=scoreboard, jogador=jogador, tagline=tagline)

if __name__ == '__main__':
    # Inicia o servidor local de desenvolvimento na porta 5000
    app.run(debug=True)