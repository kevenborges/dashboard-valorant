# =============================================================================
# gerar_token_2.py — Utilitário
# Descrição: Script isolado responsável apenas por requerer um novo token
# de acesso na API da Twitch (OAuth2) via Client Credentials.
# O Token gerado aqui deve ser copiado e colado manualmente dentro do arquivo .env.
# =============================================================================

import requests

# Credenciais criadas na dashboard de desenvolvedor da Twitch.
client_id = 'isbtkqx3z958wgqkgrhfu4tu6hjbyj'
client_secret = '3f5651xjw3t8f2sdcca39ie8u991m2'

url = 'https://id.twitch.tv/oauth2/token'

# Monta o corpo da requisição especificando o tipo de autorização
parametros = {
    'client_id': client_id,
    'client_secret': client_secret,
    'grant_type': 'client_credentials'
}

# Faz a requisição POST oficial para a rota Twitch Oauth2
resposta = requests.post(url, data=parametros)

# Tenta exibir apenas a chave de acesso isolada na interface de comando
print(f"O teu TWITCH_TOKEN é: {resposta.json().get('access_token')}")